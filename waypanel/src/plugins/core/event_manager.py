from gi.repository import GLib

from wayfire.core.template import get_msg_template
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire import WayfireSocket as OriginalWayfireSocket

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    """Initialize the Event Manager plugin."""
    if ENABLE_PLUGIN:
        event_manager = EventManagerPlugin(panel_instance)
        return event_manager


class WayfireSocket(OriginalWayfireSocket):
    def hide_view(self, view_id):
        message = get_msg_template("hide-view/hide")
        message["data"]["view-id"] = view_id
        self.send_json(message)

    def unhide_view(self, view_id):
        message = get_msg_template("hide-view/unhide")
        message["data"]["view-id"] = view_id
        self.send_json(message)


class EventManagerPlugin:
    def __init__(self, panel_instance):
        """Initialize the plugin."""
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.utils = self.obj.utils

        # Initialize the IPC client
        from waypanel.src.ipc.ipc_client import WayfireClientIPC

        self.ipc_client = WayfireClientIPC(self.handle_event, self.obj)
        self.ipc_client.wayfire_events_setup("/tmp/waypanel.sock")
        self.event_subscribers = {}  # Dictionary to store event subscribers

    def handle_event(self, msg):
        """
        Handle incoming IPC events and notify subscribers.

        Args:
            msg (dict): The event message containing details about the event.
        """
        event_type = msg.get("event")

        # Notify subscribers
        if event_type in self.event_subscribers:
            for callback, plugin_name in self.event_subscribers[event_type]:
                try:
                    # Execute the callback function
                    GLib.idle_add(callback, msg)
                    if plugin_name:
                        self.logger.debug(
                            f"Event '{event_type}' triggered for plugin '{plugin_name}'"
                        )
                except Exception as e:
                    self.logger.error_handler(
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

    def _validate_event(self, msg, required_keys=None):
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
                    self.logger.warning(f"Missing required key in event message: {key}")
                    return False

        return True

    def handle_view_event(self, msg):
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

    def handle_plugin_event(self, msg):
        """Handle plugin-related events."""
        if not self._validate_event(msg, required_keys=["event", "plugin", "state"]):
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

    def handle_output_event(self, msg):
        """Handle output-related events."""
        if not self._validate_event(msg, required_keys=["event"]):
            return

        event = msg["event"]

        if event == "output-gain-focus":
            self.on_output_gain_focus()

    def handle_workspace_event(self, msg):
        """Handle workspace-related events."""
        if "event" not in msg:
            return
        # Add workspace-specific logic here

    def subscribe_to_event(self, event_type, callback, plugin_name=None):
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

    def unsubscribe_from_event(self, event_type, callback):
        """Allow plugins to unsubscribe from specific events."""
        if event_type in self.event_subscribers:
            self.event_subscribers[event_type].remove(callback)
            self.logger.info(f"Unsubscribed from event: {event_type}")

    # Event callbacks
    def on_view_focused(self, view):
        """Handle when any view gains focus."""
        self.logger.debug("View focused.")

    def on_view_created(self, view):
        """Handle when a view is created."""
        self.logger.debug(f"View created: {view}")

    def on_view_destroyed(self, view):
        """Handle when a view is destroyed."""
        self.logger.debug(f"View destroyed: {view}")

    def on_title_changed(self, view):
        """Handle title changes for views."""
        self.logger.debug(f"Title changed for view: {view}")

    def on_app_id_changed(self, view):
        """Handle changes in app-id of a view."""
        self.logger.debug(f"App ID changed for view: {view}")

    def on_expo_activated(self):
        """Handle expo plugin activation."""
        self.logger.debug("Expo plugin activated.")

    def on_expo_desactivated(self):
        """Handle expo plugin deactivation."""
        self.logger.debug("Expo plugin deactivated.")

    def on_scale_activated(self):
        """Handle scale plugin activation."""
        self.logger.debug("Scale plugin activated.")

    def on_scale_desactivated(self):
        """Handle scale plugin deactivation."""
        self.logger.debug("Scale plugin deactivated.")

    def on_moving_view(self):
        """Handle moving view events."""
        self.logger.debug("Moving view event triggered.")

    def on_output_gain_focus(self):
        """Handle output gain focus events."""
        self.logger.debug("Output gained focus.")

    def on_view_role_toplevel_focused(self, view_id):
        # last view focus only for top level Windows
        # means that views like layer shell won't have focus set in this var
        # this is necessary for example, if you click in the maximize buttons
        # in the top bar then you need a toplevel window to maximize_last_view
        # if not, it will try to maximize the LayerShell
        # big comment because I am sure I will forget why I did this
        self.last_toplevel_focused_view = view_id

    def on_hidden_view(self, widget, view):
        id = view["id"]
        if id in self.wf_utils.list_ids():
            self.sock.unhide_view(id)
            # ***Warning*** this was freezing the panel
            # set focus will return an Exception in case the view is not toplevel
            GLib.idle_add(lambda *_: self.utils.focus_view_when_ready(view))
            if self.utils.widget_exists(widget):
                self.obj.top_panel_box_center.remove(widget)
