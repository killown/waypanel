import os
import orjson as json
import gi
from gi.repository import Gtk
from waypanel.src.plugins.core._base import BasePlugin


# Enable or disable the plugin
ENABLE_PLUGIN = True
DEPS = ["event_manager", "gestures_setup"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "bottom-panel"
    order = 5
    priority = 10
    return position, order, priority


def initialize_plugin(panel_instance):
    """Initialize the Taskbar plugin."""
    if ENABLE_PLUGIN:
        return TaskbarPlugin(panel_instance)


class TaskbarPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """
        Initialize the Taskbar plugin. This depends on the event_manager.
        If the event takes time to start,
        the button panel set_layer top/bottom may also take time to be ready.
        """

        self._subscribe_to_events()
        # will hide until scale plugin is toggled if False
        self.layer_always_exclusive = False
        self.taskbar_list = []
        self.buttons_id = {}
        self.update_widget = self.utils.update_widget
        self.is_scale_active = {}
        self.create_gesture = self.plugins["gestures_setup"].create_gesture
        self.remove_gesture = self.plugins["gestures_setup"].remove_gesture
        # Load configuration and set up taskbar
        self._setup_taskbar()

    def set_main_widget(self):
        self.main_widget = (self.scrolled_window, "set_content")

    def set_layer_exclusive(self, exclusive):
        if exclusive:
            self.update_widget(self.set_layer_pos_exclusive, self.bottom_panel, 48)
        else:
            self.update_widget(self.unset_layer_pos_exclusive, self.bottom_panel)

    def _setup_taskbar(self):
        """Create and configure the bottom panel."""
        self.logger.debug("Setting up bottom panel.")
        if self.layer_always_exclusive:
            self.layer_shell.set_layer(self.bottom_panel, self.layer_shell.Layer.TOP)
            self.layer_shell.auto_exclusive_zone_enable(self.bottom_panel)
            self.bottom_panel.set_size_request(10, 10)

        # Add launcher button
        self.add_launcher = Gtk.Button()
        icon = self.utils.get_nearest_icon_name("tab-new")
        self.update_widget(self.add_launcher.set_icon_name, icon)

        # Scrolled window setup
        self.scrolled_window = Gtk.ScrolledWindow()
        output = os.getenv("waypanel")
        output_name = None
        geometry = None

        if output:
            output_name = json.loads(output).get("output_name")
        if output_name:
            output_id = self.ipc.get_output_id_by_name(output_name)
            if output_id:
                geometry = self.ipc.get_output_geometry(output_id)

        if geometry:
            monitor_width = geometry["width"]
            self.update_widget(
                self.scrolled_window.set_size_request, monitor_width / 1.2, 64
            )

        # Set content for the bottom panel
        self.update_widget(self.bottom_panel.set_content, self.scrolled_window)

        # Taskbar setup
        self.taskbar = Gtk.FlowBox()
        self.update_widget(
            self.taskbar.set_halign, Gtk.Align.CENTER
        )  # Center horizontally
        self.update_widget(
            self.taskbar.set_valign, Gtk.Align.CENTER
        )  # Center vertically
        self.update_widget(self.scrolled_window.set_child, self.taskbar)
        self.taskbar.add_css_class("taskbar")

        # Present the panel if enabled

        # Start the taskbar list for the bottom panel
        self.Taskbar()

        self.logger.info("Bottom panel setup completed.")

        # Unset layer position for other panels

    def _subscribe_to_events(self):
        """Subscribe to relevant events using the event_manager."""
        if "event_manager" not in self.obj.plugin_loader.plugins:
            self.logger.debug("Taskbar is waiting for EventManagerPlugin.")
            return True
        else:
            event_manager = self.obj.plugin_loader.plugins["event_manager"]
            self.logger.info("Subscribing to events for Taskbar Plugin.")

            # Subscribe to necessary events
            event_manager.subscribe_to_event(
                "view-focused",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-mapped",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-unmapped",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-title-changed",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "plugin-activation-state-changed",
                self.handle_plugin_event,
                plugin_name="taskbar",
            )

    def create_taskbar_button(self, view):
        app_id = view["app-id"]
        title = view["title"]
        initial_title = title.split()[0]
        icon_name = self.utils.get_icon(app_id, initial_title, title)
        if icon_name is None:
            return None

        button = Gtk.Button()

        # Filter title for UTF-8 compatibility
        title = self.utils.filter_utf_for_gtk(view["title"])
        view_id = view["id"]
        if not title:
            return None

        # Determine title to use based on its length
        use_this_title = title[:30]
        first_word_length = len(title.split()[0])
        if first_word_length > 13:
            use_this_title = title.split()[0]

        # Create a box to hold icon and label
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Add icon if available
        if icon_name:
            icon = Gtk.Image()
            self.update_widget(icon.set_from_icon_name, icon_name)
            self.update_widget(box.append, icon)

        # Add label
        label = Gtk.Label()
        self.update_widget(label.set_label, use_this_title)
        self.update_widget(box.append, label)

        # Set the box as the button's child
        self.update_widget(button.set_child, box)

        # Create gesture handlers for the button
        button.connect("clicked", lambda *_: self.set_view_focus(view))
        self.create_gesture(box, 1, lambda *_: self.set_view_focus(view))
        self.create_gesture(box, 2, lambda *_: self.ipc.close_view(view_id))
        self.create_gesture(box, 3, lambda *_: self.send_view_to_empity_workspace(view))

        return button

    def send_view_to_empity_workspace(self, view):
        empty_workspace = self.utils.find_empty_workspace()
        view_id = view["id"]
        wset_index_focused = self.ipc.get_focused_output()["wset-index"]
        wset_index_view = view["wset-index"]
        # this will prevent from trying to move the view from another output to an empity workspace
        # because it's necessary to bring the view to the current output and then move it to a empity ws
        if wset_index_focused != wset_index_view:
            self.set_view_focus(view)
        else:
            self.ipc.scale_toggle()
            if empty_workspace:
                x, y = empty_workspace
                # if set_workspace from an empity workspace before the view is focused
                # the view may disappear from the workspaces layout and will not be able to get focus
                self.set_view_focus(view)
                # now move the view to an empity workspace
                self.ipc.set_workspace(x, y, view_id)

    def new_taskbar_button(self, view):
        """
        Create a taskbar button for a given view.

        Args:
            view (dict): The view object containing details like ID, title, and app-id.
            orientation (str): The orientation of the taskbar ("h" or "v").
            class_style (str): The CSS class style for the button.

        Returns:
            bool: True if the button was successfully created, False otherwise.
        """
        self.logger.debug(f"Creating taskbar button for view: {view['id']}")
        id = view["id"]
        title = view["title"]
        title = self.utils.filter_utf_for_gtk(title)
        initial_title = title.split(" ")[0].lower()

        button = self.create_taskbar_button(view)

        if not button:
            self.logger.info(f"Failed to create taskbar button for view ID: {id}")
            return False

        # Append the button to the taskbar
        self.update_widget(self.taskbar.append, button)

        # Store button information in dictionaries for easy access
        self.buttons_id[id] = [button, initial_title, id]
        self.taskbar_list.append(id)
        button.add_css_class("taskbar-button")
        return True

    def Taskbar(self):
        """Initialize or update the taskbar."""
        self.logger.debug("Initializing or updating taskbar.")
        list_views = self.ipc.list_views()
        if not list_views:
            return
        for view in list_views:
            self.new_view(view)
        return True

    def new_view(self, view, callback=None):
        """
        Initialize or update the taskbar with a new view.

        Args:
            orientation (str): The orientation of the taskbar ("h" or "v").
            class_style (str): The CSS class style for the button.
            view_id (int): The ID of the view to add.
            callback (function, optional): A callback function to execute after creation.

        Returns:
            bool: True if the taskbar button was successfully created, False otherwise.
        """
        view_id = view["id"]
        self.logger.debug(f"Initializing new taskbar view for ID: {view_id}")
        # Validate the view
        if not self.validate_view_for_taskbar(view_id):
            self.logger.debug(f"Validation failed for view ID: {view_id}")
            return False

        # Create the taskbar button
        success = self.new_taskbar_button(view)
        if not success:
            self.logger.error_handler.handle(
                f"Failed to create taskbar button for view ID: {view_id}"
            )
            return False

        if callback:
            callback(view_id)

        return True

    def validate_view_for_taskbar(self, view_id):
        """
        Validate if a view exists and meets the criteria to be added to the taskbar.
        Args:
            view_id (int): The ID of the view to validate.
        Returns:
            dict or None: The view object if valid, otherwise None.
        """
        self.logger.debug(f"Validating view for taskbar: {view_id}")
        if not self.view_exist(view_id):
            self.logger.debug(f"View does not exist: {view_id}")
            return {}

        if view_id in self.taskbar_list:
            self.logger.debug(f"View already in taskbar list: {view_id}")
            return {}

        if view_id not in self.ipc.list_ids():
            self.logger.debug(f"View ID not in active IDs: {view_id}")
            return {}

        view = self.ipc.get_view(view_id)
        if not view:
            self.logger.debug(f"Failed to fetch view details for ID: {view_id}")
            return {}

        return view

    def on_view_focused(self, view):
        """Handle when a view gains focus."""
        self.update_taskbar_list(view)

    def on_view_created(self, view):
        """Handle creation of new views."""
        self.update_taskbar_list(view)

    def on_view_destroyed(self, view):
        """Handle destruction of views."""
        self.remove_button(view["id"])
        self.update_taskbar_list(view)

    def on_title_changed(self, view):
        """Handle title changes for views."""
        self.logger.debug(f"Title changed for view: {view}")
        self.update_taskbar_button(view)

    def handle_plugin_event(self, msg):
        """Handle plugin-related IPC events."""
        prevent_infinite_loop_from_event_manager_idle_add = False
        if msg["event"] == "plugin-activation-state-changed":
            if msg["state"] is True:
                if msg["plugin"] == "scale":
                    self.is_scale_active[msg["output"]] = True
                    self.on_scale_activated()
            if msg["state"] is False:
                if msg["plugin"] == "scale":
                    self.is_scale_active[msg["output"]] = False
                    self.on_scale_desactivated()
        return prevent_infinite_loop_from_event_manager_idle_add

    def update_taskbar_button(self, view):
        """
        remove the old button from taskbar and add a new one updated
        this function is only intended to use along with event: title_changed
        """
        button = None
        id = view["id"]
        if id in self.buttons_id:
            button = self.buttons_id[id][0]

        if not button:
            return

        if not self.utils.widget_exists(button):
            return

        if button:
            self.remove_button(id)
            self.update_taskbar_list(view)

    def set_view_focus(self, view_id):
        """
        Focus a view based on its ID, resizing it if necessary and handling scaling activation.

        Args:
            view_id (int): The ID of the view to focus.

        Returns:
            bool: True if an error occurs, otherwise None.
        """
        try:
            view = self.utils.is_view_valid(view_id)
            if not view:
                self.logger.debug(f"Invalid or non-existent view ID: {view_id}")
                return

            view_id = view["id"]
            output_id = view["output-id"]

            # Resize the view if it's too small
            try:
                viewgeo = self.ipc.get_view_geometry(view_id)
                if viewgeo and (viewgeo["width"] < 100 or viewgeo["height"] < 100):
                    self.ipc.configure_view(
                        view_id, viewgeo["x"], viewgeo["y"], 400, 400
                    )
                    self.logger.debug(f"Resized view ID {view_id} to 400x400.")
            except Exception as e:
                self.logger.error_handler.handle(
                    error=e,
                    message=f"Failed to retrieve or resize geometry for view ID: {view_id}",
                )

            # Handle scale activation
            if output_id in self.is_scale_active and self.is_scale_active[output_id]:
                try:
                    self.ipc.scale_toggle()
                    self.logger.debug("Scale toggled off.")
                except Exception as e:
                    self.logger.error_handler.handle(
                        error=e, message="Failed to toggle scale."
                    )
                finally:
                    # Ensure workspace focus and cursor centering even if scale toggle fails
                    self._focus_and_center_cursor(view_id)
            else:
                # Focus workspace and center cursor without scale handling
                self._focus_and_center_cursor(view_id)

            # Apply focus indicator effect
            self.utils.view_focus_indicator_effect(view)

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error_handler.handle(
                error=e,
                message=f"Unexpected error while setting focus for view ID: {view_id}",
            )
            return True

    def _focus_and_center_cursor(self, view_id):
        """
        Focus the workspace and center the cursor on the specified view.

        Args:
            view_id (int): The ID of the view to focus and center.
        """
        try:
            self.ipc.go_workspace_set_focus(view_id)
            self.ipc.center_cursor_on_view(view_id)
        except Exception as e:
            self.logger.error_handler.handle(
                error=e,
                message=f"Failed to focus workspace or center cursor for view ID: {view_id}",
            )

    def update_taskbar_on_scale(self) -> None:
        """Update all taskbar buttons during scale plugin activation."""
        self.logger.debug("Updating taskbar buttons during scale plugin activation.")
        for view in self.ipc.list_views():
            self.update_taskbar_list(view)

    def on_scale_activated(self):
        """Handle scale wayfire plugin activation."""
        # set layer exclusive so the panels becomes clickable
        output_info = os.getenv("waypanel")
        layer_set_on_output_name = None
        if output_info:
            layer_set_on_output_name = json.loads(output_info).get("output_name")
        focused_output_name = self.ipc.get_focused_output()["name"]
        # only set layer if the focused output is the same as the defined in panel creation
        if (
            layer_set_on_output_name == focused_output_name
            and not self.layer_always_exclusive
        ):
            self.set_layer_exclusive(True)
        self.update_taskbar_on_scale()

    def on_scale_desactivated(self):
        """Handle scale plugin deactivation."""
        if not self.layer_always_exclusive:
            self.set_layer_exclusive(False)

    def get_valid_button(self, button_id):
        try:
            if button_id in self.buttons_id:
                button = self.buttons_id[button_id][0]
                if self.utils.widget_exists(button):
                    return button
        except Exception as e:
            self.logger.error_handler.handle(
                error=e,
                message="Invalid or missing button for ID",
                context={"plugin": "taskbar", "ID": button_id},
            )
        return None

    def remove_button(self, view_id):
        """
        Remove a taskbar button associated with a view.

        Args:
            id (int): The ID of the view whose button should be removed.
        """

        # Get the valid button using the helper function
        button = self.get_valid_button(view_id)
        if not button:
            return

        # Remove the button from the taskbar and clean up
        self.update_widget(self.taskbar.remove, button)
        self.taskbar_list.remove(view_id)
        self.remove_gesture(button)
        del self.buttons_id[view_id]

    def update_taskbar_list(self, view):
        """Update the taskbar list based on the current views."""
        self.logger.debug(f"Updating taskbar list for view: {view}")
        # Update the taskbar layout
        self.Taskbar()
        # Remove invalid buttons
        self._remove_invalid_buttons()

    def _remove_invalid_buttons(self):
        """Remove buttons for views that no longer exist."""
        current_views = {v["id"] for v in self.ipc.list_views()}
        for view_id in list(self.buttons_id.keys()):
            if view_id not in current_views:
                self.remove_button(view_id)

    def view_exist(self, view_id):
        """Check if a view exists and meets criteria to be displayed in the taskbar."""
        try:
            view_id_list = [view["id"] for view in self.ipc.list_views()]
            if view_id not in view_id_list:
                return False
            view = self.ipc.get_view(view_id)
            if not self.is_valid_view(view):
                return False

            return True
        except Exception as e:
            self.logger.error_handler.handle(
                error=e,
                message="Error checking view existence",
                context={"plugin": "taskbar", "view_id": view_id},
            )
            return False

    def is_valid_view(self, view):
        """Check if a view meets the criteria to be displayed in the taskbar."""
        return (
            view["layer"] == "workspace"
            and view["role"] == "toplevel"
            and view["mapped"] is True
            and view["app-id"] != "nil"
            and view["pid"] != -1
        )

    def handle_view_event(self, msg):
        """Handle view-related IPC events."""
        view = msg.get("view")

        # This event match must be here because if not, role != toplevel will make it never match.
        if msg["event"] == "view-wset-changed":
            # self.update_taskbar_for_hidden_views(view)
            return
        # This must be here; an unmapped view is view None, must be above if view is None.
        if msg["event"] == "view-unmapped":
            self.on_view_destroyed(view)
        if view is None:
            return
        if view["pid"] == -1:
            return
        if "role" not in view:
            return
        if view["role"] != "toplevel":
            return
        if view["app-id"] == "":
            return
        if view["app-id"] == "nil":
            return
        if msg["event"] == "output-gain-focus":
            # self.on_output_gain_focus()
            return
        if msg["event"] == "view-title-changed":
            self.on_title_changed(view)
        if msg["event"] == "view-tiled" and view:
            pass
        if msg["event"] == "app-id-changed":
            # self.on_app_id_changed(msg["view"])
            return
        if msg["event"] == "view-focused":
            # self.on_view_role_toplevel_focused(view)
            # self.on_view_focused()
            # self.last_focused_output = view["output-id"]
            return
        if msg["event"] == "view-mapped":
            self.on_view_created(view)
        if msg["event"] == "view-unmapped":
            self.on_view_destroyed(view)
        return
