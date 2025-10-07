def get_plugin_metadata(_):
    return {
        "enabled": True,
        "priority": 1,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    import collections

    class EventManagerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            """Initialize the Event Manager Plugin.

            Sets up the IPC client for receiving compositor events and initializes
            the event subscription system to allow other plugins to register handlers.

            Args:
                panel_instance: The main panel object providing access to shared resources
                                such as configuration, logger, and plugin loader.
            """
            super().__init__(panel_instance)
            """Initialize the plugin."""

            # Initialize the IPC client
            from src.ipc.ipc_client import WayfireClientIPC

            self.ipc_client = WayfireClientIPC(self.handle_event, self.obj)
            self.get_socket_path = self.ipc_server.get_socket_path
            self.ipc_client.wayfire_events_setup(self.get_socket_path())
            self.event_subscribers = {}  # Dictionary to store event subscribers

            # New: Initialize event queue and processing state
            self.event_queue = collections.deque()
            self.is_processing_events = False

        def on_start(self):
            # New: Start the periodic event processing loop
            # The timeout will call _process_queued_events every 50ms
            self.glib.timeout_add(50, self._process_queued_events)

        def handle_event(self, msg) -> None:
            """
            Handle incoming IPC events by adding them to a queue.

            Args:
                msg (dict): The event message containing details about the event.
            """
            # skip the event if no connection
            if not self.ipc.is_connected():
                return

            # New: Add the incoming message to the event queue instead of processing it directly
            self.event_queue.append(msg)
            self.logger.debug(
                f"Event queued. Current queue size: {len(self.event_queue)}"
            )

        def _process_queued_events(self):
            """
            Periodically processes all events currently in the queue.

            This method acts as a throttle, ensuring that events are handled in batches
            at a controlled rate, preventing the UI from freezing.
            """
            if self.is_processing_events:
                return True  # Prevents re-entry if the function is still running

            self.is_processing_events = True

            while self.event_queue:
                msg = self.event_queue.popleft()
                try:
                    event_type = msg.get("event")

                    # Notify subscribers
                    if event_type in self.event_subscribers:
                        for callback, plugin_name in self.event_subscribers[event_type]:
                            try:
                                # Use self.glib.idle_add to push callback to the main loop
                                self.glib.idle_add(callback, msg)
                                if plugin_name:
                                    self.logger.debug(
                                        f"Event '{event_type}' triggered for plugin '{plugin_name}'"
                                    )
                            except Exception as e:
                                self.logger.error(
                                    f"Error executing callback for event '{event_type}': {e}"
                                )

                    # Handle specific event types
                    if event_type.startswith("view-"):
                        self.handle_view_event(msg)
                    elif event_type.startswith("plugin-"):
                        self.handle_plugin_event(msg)
                    elif event_type.startswith("output-"):
                        self.handle_output_event(msg)
                    elif event_type.startswith("workspace-"):
                        self.handle_workspace_event(msg)

                except Exception as e:
                    self.logger.error(f"Error processing queued event: {e}")

            self.is_processing_events = False
            return True  # Return True to keep the timeout running

        def _validate_event(self, msg, required_keys=None) -> bool:
            """
            Validate the incoming event message.

            Args:
                msg (dict): The event message.
                required_keys (list): List of keys that must be present in the message.

            Returns:
                bool: True if the checks pass, False otherwise.
            """
            if not isinstance(msg, dict):
                self.logger.warning("Invalid event message: Not a dictionary.")
                return False

            # Check for the presence of required keys
            if required_keys:
                for key in required_keys:
                    if key not in msg:
                        self.logger.warning(
                            f"Missing required key in event message: {key}"
                        )
                        return False

            return True

        def handle_view_event(self, msg) -> None:
            """Handle view-related events."""
            view = msg.get("view")
            event = msg.get("event")

            # Common checks for view-related events
            if view is None:
                return
            if view["pid"] == -1 or view.get("role") != "toplevel":
                return
            if view.get("app-id") in ["", "nil"]:
                return

            # Handle specific view events
            if event == "view-unmapped":
                self.on_view_destroyed(view)
            elif event == "view-title-changed":
                self.on_title_changed(view)
            elif event == "view-tiled":
                pass  # No action needed
            elif event == "app-id-changed":
                self.on_app_id_changed(view)
            elif event == "view-focused":
                self.on_view_focused(view)
            elif event == "view-mapped":
                self.on_view_created(view)

        def handle_plugin_event(self, msg) -> None:
            """Handle plugin-related events."""
            if not self._validate_event(
                msg, required_keys=["event", "plugin", "state"]
            ):
                return

            plugin = msg["plugin"]
            state = msg["state"]

            if plugin == "expo":
                if state:
                    self.on_expo_activated()
                else:
                    self.on_expo_desactivated()
            elif plugin == "scale":
                if state:
                    self.on_scale_activated()
                else:
                    self.on_scale_desactivated()
            elif plugin == "move":
                self.on_moving_view()

        def handle_output_event(self, msg) -> None:
            """Handle output-related events."""
            if not self._validate_event(msg, required_keys=["event"]):
                return

            event = msg["event"]

            if event == "output-gain-focus":
                self.on_output_gain_focus()

        def handle_workspace_event(self, msg) -> None:
            """Handle workspace-related events."""
            if "event" not in msg:
                return

        def subscribe_to_event(self, event_type, callback, plugin_name=None) -> None:
            """
            Allow plugins to subscribe to specific events.

            Args:
                event_type (str): The type of event to subscribe to.
                callback (function): The callback function to execute when the event occurs.
                plugin_name (str, optional): The name of the plugin subscribing to the event.
            """
            if event_type not in self.event_subscribers:
                self.event_subscribers[event_type] = []

            # Add the callback and plugin name to the list of subscribers
            self.event_subscribers[event_type].append((callback, plugin_name))

            # Log the subscription with the plugin name
            if plugin_name:
                self.logger.info(
                    f"Plugin '{plugin_name}' subscribed to event: {event_type}"
                )
            else:
                self.logger.info(f"Anonymous plugin subscribed to event: {event_type}")

        def unsubscribe_from_event(self, event_type, callback) -> None:
            """Allow plugins to unsubscribe from specific events."""
            if event_type in self.event_subscribers:
                self.event_subscribers[event_type].remove(callback)
                self.logger.info(f"Unsubscribed from event: {event_type}")

        # Event callbacks
        def on_view_focused(self, view) -> None:
            """Handle when any view gains focus."""
            self.logger.debug("View focused.")

        def on_view_created(self, view) -> None:
            """Handle when a view is created."""
            self.logger.debug(f"View created: {view}")

        def on_view_destroyed(self, view) -> None:
            """Handle when a view is destroyed."""
            self.logger.debug(f"View destroyed: {view}")

        def on_title_changed(self, view) -> None:
            """Handle title changes for views."""
            self.logger.debug(f"Title changed for view: {view}")

        def on_app_id_changed(self, view) -> None:
            """Handle changes in app-id of a view."""
            self.logger.debug(f"App ID changed for view: {view}")

        def on_expo_activated(self) -> None:
            """Handle expo plugin activation."""
            self.logger.debug("Expo plugin activated.")

        def on_expo_desactivated(self) -> None:
            """Handle expo plugin deactivation."""
            self.logger.debug("Expo plugin deactivated.")

        def on_scale_activated(self) -> None:
            """Handle scale plugin activation."""
            self.logger.debug("Scale plugin activated.")

        def on_scale_desactivated(self) -> None:
            """Handle scale plugin deactivation."""
            self.logger.debug("Scale plugin deactivated.")

        def on_moving_view(self) -> None:
            """Handle moving view events."""
            self.logger.debug("Moving view event triggered.")

        def on_output_gain_focus(self) -> None:
            """Handle output gain focus events."""
            self.logger.debug("Output gained focus.")

        def on_view_role_toplevel_focused(self, view_id) -> None:
            # last view focus only for top level Windows
            # means that views like layer shell won't have focus set in this var
            # this is necessary for example, if you click in the maximize buttons
            # in the top bar then you need a toplevel window to maximize_last_view
            # if not, it will try to maximize the LayerShell
            # big comment because I am sure I will forget why I did this
            self.last_toplevel_focused_view = view_id

        def on_hidden_view(self, widget, view) -> None:
            id = view.get("id")
            if id in self.ipc.list_ids():
                self.ipc.unhide_view(id)
                # ***Warning*** this was freezing the panel
                # set focus will return an Exception in case the view is not toplevel
                # self.glib.idle_add(lambda *_: self.utils.focus_view_when_ready(view))
                # if self.utils.widget_exists(widget):
                # self.obj.top_panel_box_center.remove(widget)
                #

        def get_socket_path(self) -> str:
            runtime_dir = self.os.environ.get("XDG_RUNTIME_DIR", "/tmp")
            socket_name = "waypanel.sock"
            return self.os.path.join(runtime_dir, socket_name)

        def about(self):
            """
            This is a core background plugin that acts as a central event
            bus, receiving events from the compositor and dispatching them
            to other plugins in a thread-safe manner.
            """
            return self.about.__doc__

        def code_explanation(self):
            """
            The core logic of this plugin is a resilient event-driven
            architecture based on the publish-subscribe pattern. Its
            key principles are:

            1.  **Event Queue and Throttling**: Instead of immediately
                processing every incoming event from the IPC, the plugin
                queues them in a `collections.deque`. A periodic timer,
                set by `self.glib.timeout_add`, processes the queue in batches.
                This throttling mechanism prevents a sudden burst of events
                from overwhelming the main event loop and freezing the UI.

            2.  **Publish-Subscribe System**: The plugin acts as a central
                event hub. It provides a `subscribe_to_event` method that
                allows other plugins to register callbacks for specific
                event types. It then publishes events by iterating through
                all registered callbacks and executing them.

            3.  **Thread-Safe Dispatching**: To ensure stability, the
                plugin uses `self.glib.idle_add` to dispatch all callbacks.
                This guarantees that any plugin-specific logic, especially
                UI updates, is executed on the main GTK thread, preventing
                race conditions and application crashes.
            """
            return self.code_explanation.__doc__

    return EventManagerPlugin
