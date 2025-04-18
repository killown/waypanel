import os
import orjson as json
from gi.repository import Gtk, GLib
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.ipc import WayfireSocket
from gi.repository import Gtk4LayerShell as LayerShell

from waypanel.src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)
from waypanel.src.core.utils import Utils

# Enable or disable the plugin
ENABLE_PLUGIN = True


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


class TaskbarPlugin(Gtk.Application):
    def __init__(self, panel_instance):
        """
        Initialize the Taskbar plugin. This depends on the event_manager.
        If the event takes time to start,
        the button panel set_layer top/bottom may also take time to be ready.
        """
        self.logger = panel_instance.logger
        self.obj = panel_instance
        # will hide until scale plugin is toggled if False
        self.layer_always_exclusive = False
        self.utils = Utils()
        self.taskbar_list = []
        self.buttons_id = {}
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.bottom_panel = self.obj.bottom_panel
        self.update_widget = self.utils.update_widget
        # Load configuration and set up taskbar
        self.config = panel_instance.config
        self._setup_taskbar()
        self._subscribe_to_events()

    def set_layer_exclusive(self, exclusive):
        if exclusive:
            self.update_widget(set_layer_position_exclusive, self.bottom_panel, 48)
        else:
            self.update_widget(unset_layer_position_exclusive, self.bottom_panel)

    def _setup_taskbar(self):
        """Create and configure the bottom panel."""
        self.logger.debug("Setting up bottom panel.")
        if self.layer_always_exclusive:
            LayerShell.set_layer(self.bottom_panel, LayerShell.Layer.TOP)
            LayerShell.auto_exclusive_zone_enable(self.bottom_panel)
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
            output_id = self.wf_utils.get_output_id_by_name(output_name)
            if output_id:
                geometry = self.wf_utils.get_output_geometry(output_id)

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
        self.Taskbar("h", "taskbar")

        self.logger.info("Bottom panel setup completed.")

        # Unset layer position for other panels

    def _subscribe_to_events(self):
        """Subscribe to relevant events using the event_manager."""

        def is_event_manager_ready():
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

                return False

        GLib.timeout_add_seconds(1, is_event_manager_ready)

    def create_taskbar_button(self, view, orientation, class_style):
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
        title = self.utils.filter_utf_for_gtk(view["title"])
        wm_class = view["app-id"]
        initial_title = title.split(" ")[0].lower()

        button = self.utils.create_taskbar_launcher(
            wm_class, title, initial_title, orientation, class_style, id
        )

        if not button:
            self.logger.error(f"Failed to create taskbar button for view ID: {id}")
            return False

        # Append the button to the taskbar
        self.utils.append_widget_if_ready(self.taskbar, button)

        # Store button information in dictionaries for easy access
        self.buttons_id[id] = [button, initial_title, id]
        self.taskbar_list.append(id)
        button.add_css_class("taskbar-button")
        return True

    def Taskbar(self, orientation, class_style, update_button=False, callback=None):
        """Initialize or update the taskbar."""
        self.logger.debug("Initializing or updating taskbar.")
        list_views = self.sock.list_views()
        if not list_views:
            return
        for i in list_views:
            self.new_taskbar_view(orientation, class_style, i["id"])
        return True

    def new_taskbar_view(self, orientation, class_style, view_id, callback=None):
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
        self.logger.debug(f"Initializing new taskbar view for ID: {view_id}")

        # Validate the view
        view = self.validate_view_for_taskbar(view_id)
        if not view:
            self.logger.debug(f"Validation failed for view ID: {view_id}")
            return False

        # Create the taskbar button
        success = self.create_taskbar_button(view, orientation, class_style)
        if not success:
            self.logger.error(f"Failed to create taskbar button for view ID: {view_id}")
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

        if view_id not in self.wf_utils.list_ids():
            self.logger.debug(f"View ID not in active IDs: {view_id}")
            return {}

        view = self.sock.get_view(view_id)
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
                    self.on_scale_activated()
            if msg["state"] is False:
                if msg["plugin"] == "scale":
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

    def update_taskbar_on_scale(self) -> None:
        """Update all taskbar buttons during scale plugin activation."""
        self.logger.debug("Updating taskbar buttons during scale plugin activation.")
        for view in self.sock.list_views():
            self.update_taskbar_list(view)

    def on_scale_activated(self):
        """Handle scale wayfire plugin activation."""
        # set layer exclusive so the panels becomes clickable
        output_info = os.getenv("waypanel")
        layer_set_on_output_name = None
        if output_info:
            layer_set_on_output_name = json.loads(output_info).get("output_name")
        focused_output_name = self.sock.get_focused_output()["name"]
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
        if button_id in self.buttons_id:
            button = self.buttons_id[button_id][0]
            if self.utils.widget_exists(button):
                return button
        self.logger.debug(f"Invalid or missing button for ID: {button_id}")
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
            self.logger.debug(f"No valid button found for ID: {view_id}")
            return

        # Remove the button from the taskbar and clean up
        self.update_widget(self.taskbar.remove, button)
        self.taskbar_list.remove(view_id)
        self.utils.remove_gesture(button)
        del self.buttons_id[view_id]

    def update_taskbar_list(self, view):
        """Update the taskbar list based on the current views."""
        self.logger.debug(f"Updating taskbar list for view: {view}")
        # Update the taskbar layout
        self.Taskbar("h", "taskbar")
        # Remove invalid buttons
        self._remove_invalid_buttons()

    def _remove_invalid_buttons(self):
        """Remove buttons for views that no longer exist."""
        current_views = {v["id"] for v in self.sock.list_views()}
        for view_id in list(self.buttons_id.keys()):
            if view_id not in current_views:
                self.remove_button(view_id)

    def view_exist(self, view_id):
        """Check if a view exists and meets criteria to be displayed in the taskbar."""
        try:
            view_id_list = [view["id"] for view in self.sock.list_views()]
            if view_id not in view_id_list:
                return False

            view = self.sock.get_view(view_id)
            if not self.is_valid_view(view):
                return False

            return True
        except Exception as e:
            self.logger.error(f"Error checking view existence: {e}")
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

    def panel_set_content(self):
        """Return the taskbar widget to be added to the panel."""
        return self.scrolled_window
