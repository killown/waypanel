from gi.repository import Gtk
import os
import toml
from core._base import BasePlugin
from src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

# Enable or disable the plugin
ENABLE_PLUGIN = True

# disabled for sway compositor
if not os.getenv("WAYFIRE_SOCKET"):
    ENABLE_PLUGIN = False

DEPS = ["event_manager", "gestures_setup"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "left-panel-center"
    # priority position is from config.toml [dockbar_panel.position] = "left"
    # the dockbar will be on left ignoring hardcoded position
    dockbar_config = panel_instance.config.get("dockbar_panel", {})
    if dockbar_config:
        if "panel" in dockbar_config:
            position = dockbar_config["panel"]
            position = f"{position}"
    order = 5
    priority = 1
    return position, order, priority


def initialize_plugin(panel_instance):
    """Initialize the Dockbar plugin."""
    if ENABLE_PLUGIN:
        dockbar = DockbarPlugin(panel_instance)
        return dockbar


class DockbarPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """Initialize the Dockbar plugin."""
        # Subscribe to events using the event_manager
        self.create_gesture = self.plugins["gestures_setup"].create_gesture
        self._subscribe_to_events()
        self.layer_state = False
        self.taskbar_list = []
        self.dockbar_panel = self.get_panel()
        self.buttons_id = {}
        self.dockbar = None
        # Load configuration and set up dockbar
        self._setup_dockbar()

    def get_panel(self):
        """
        Returns the appropriate panel object (e.g., self.obj.left_panel)
        based on the dockbar configuration.
        """
        dockbar_config = self.obj.config.get("dockbar_panel", {})
        if not dockbar_config or "panel" not in dockbar_config:
            self.logger.warning(
                "Dockbar panel config is missing or invalid. Using default: left-panel."
            )
            return self.obj.left_panel

        position = dockbar_config["panel"].lower()  # e.g., 'left-panel'
        valid_panels = {
            "left": self.obj.left_panel,
            "right": self.obj.right_panel,
            "top": self.obj.top_panel,
            "bottom": self.obj.bottom_panel,
        }

        # Extract base panel name (e.g., 'left' from 'left-panel')
        panel_key = position.split("-")[0]

        if panel_key in valid_panels:
            return valid_panels[panel_key]
        else:
            self.logger.error(
                f"Invalid panel value: {position}. Defaulting to left-panel."
            )
            return self.obj.left_panel

    def is_scale_enabled(self):
        plugins = self.ipc.get_option_value("core/plugins")["value"].split()
        return "scale" in plugins

    def get_dockbar_position(self, panel):
        if panel == "left-panel":
            return self.obj.left_panel
        if panel == "right-panel":
            return self.obj.right_panel
        elif panel == "bottom-panel":
            return self.obj.bottom_panel
        elif panel == "top-panel":
            return self.obj.top_panel
        else:
            self.log_error(f"Invalid panel value: {panel}")

    def CreateFromAppList(
        self, config, orientation, class_style, callback=None, use_label=False
    ):
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        box = Gtk.Box(spacing=10, orientation=orientation)

        with open(config, "r") as f:
            config_data = toml.load(f)["dockbar"]

        for app in config_data:
            # Retrieve the command for this app
            app_cmd = config_data[app]["cmd"]

            # Create the button
            button = self.utils.create_button(
                self.utils.get_nearest_icon_name(config_data[app]["icon"]),
                app_cmd,
                class_style,
                use_label,
                self.on_left_click,
                app_cmd,
            )

            self.utils.add_cursor_effect(button)

            # Add middle-click gesture
            self.create_gesture(
                button, 2, lambda _, cmd=app_cmd: self.on_middle_click(cmd)
            )

            # Add right-click gesture
            self.create_gesture(
                button, 3, lambda _, cmd=app_cmd: self.on_right_click(cmd)
            )

            # Append the button to the box
            self.update_widget_safely(box.append, button)

        return box

    def on_left_click(self, cmd):
        self.utils.run_cmd(cmd)
        self.ipc.scale_toggle()

    def on_right_click(self, cmd):
        """
        Handle right-click action: Move the cursor to the next available output
        and open the app there.

        Args:
            cmd (str): The command to execute for the app.
        """
        try:
            # Get the list of outputs and the currently focused output
            outputs = self.ipc.list_outputs()
            focused_output = self.ipc.get_focused_output()

            # Find the index of the currently focused output
            current_index = next(
                (
                    i
                    for i, output in enumerate(outputs)
                    if output["id"] == focused_output["id"]
                ),
                -1,
            )

            # Determine the next output (wrap around if necessary)
            next_index = (current_index + 1) % len(outputs)
            next_output = outputs[next_index]

            # Calculate the center of the next output's geometry
            output_geometry = next_output["geometry"]
            cursor_x = output_geometry["x"] + output_geometry["width"] // 2
            cursor_y = output_geometry["y"] + output_geometry["height"] // 2

            # Move the cursor to the center of the next output
            self.ipc.move_cursor(cursor_x, cursor_y)
            self.ipc.click_button("S-BTN_LEFT", "full")

            # Open the app
            self.utils.run_cmd(cmd)

        except Exception as e:
            self.log_error(f"Error while handling right-click action: {e}")

    def on_middle_click(self, cmd):
        # Check for empty workspace
        coordinates = self.utils.find_empty_workspace()
        if coordinates:
            ws_x, ws_y = coordinates
            self.ipc.scale_toggle()
            self.ipc.set_workspace(ws_x, ws_y)
            self.utils.run_cmd(cmd)
        else:
            # If no empty workspace, just open the app
            self.utils.run_cmd(cmd)

    def _setup_dockbar(self):
        """Set up the dockbar based on the configuration."""
        dockbar_toml = self.config.get("dockbar", {})
        orientation = dockbar_toml.get("orientation", "v")
        class_style = dockbar_toml.get("class_style", "dockbar-buttons")

        self.dockbar = self.CreateFromAppList(
            self.obj.waypanel_cfg, orientation, class_style
        )
        self.main_widget = (self.dockbar, "append")

        # FIXME: remove this motion_controller later to use in a example
        # motion_controller = Gtk.EventControllerMotion()
        # motion_controller.connect("enter", self.on_mouse_enter)
        # self.dockbar.add_controller(motion_controller)

        # set exclusive by default if scale plugin is disabled
        # FIXME: find the right way to set exclusive zone as the top
        # probably only possible in panel creation, so check if scale is enabled
        # before the panel creation, if not, then create the panels with exclusive spacing
        # if not self.is_scale_enabled():
        #    LayerShell.set_layer(self.dockbar_panel, LayerShell.Layer.TOP)
        #    LayerShell.set_exclusive_zone(self.dockbar_panel, 64)

        self.logger.info("Dockbar setup completed.")

    def on_mouse_enter(self, controller, x, y):
        if self.layer_state is False:
            set_layer_position_exclusive(self.dockbar_panel, 64)
            self.layer_state = True

    def _subscribe_to_events(self):
        """Subscribe to relevant events using the event_manager."""
        if "event_manager" not in self.plugins:
            self.logger.info("dockbar is waiting for event manager")
            return True
        else:
            event_manager = self.plugins["event_manager"]
            self.logger.info("Subscribing to events for Dockbar Plugin.")
            event_manager.subscribe_to_event(
                "plugin-activation-state-changed",
                self.handle_plugin_event,
                plugin_name="dockbar",
            )

    def create_dockbar_button(self, view):
        """Create a dockbar button for a given view."""
        title = self.utils.filter_utf_for_gtk(view.get("title", ""))
        wm_class = view.get("app-id", "")
        initial_title = title.split(" ")[0].lower()
        icon_name = self.utils.get_icon(wm_class, initial_title, title)

        button = Gtk.Button()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            self.update_widget_safely(box.append, icon)

        label = Gtk.Label(label=title[:30])
        self.update_widget_safely(box.append, label)

        button.set_child(box)
        button.add_css_class("dockbar-button")

        # Handle button click
        button.connect("clicked", lambda *_: self.utils.focus_view_when_ready(view))

        return button

    def on_scale_desactivated(self):
        """Handle scale plugin deactivation."""
        # this will set panels on bottom, hidden it from views
        self.update_widget_safely(unset_layer_position_exclusive, self.dockbar_panel)
        self.layer_state = False

    def handle_plugin_event(self, msg):
        """Handle plugin-related IPC events."""
        prevent_infinite_loop_from_event_manager_idle_add = False
        if msg["event"] == "plugin-activation-state-changed":
            if msg["state"] is True:
                if msg["plugin"] == "scale":
                    pass
                    # self.on_scale_activated()
            if msg["state"] is False:
                if msg["plugin"] == "scale":
                    pass
                    # self.on_scale_desactivated()
        return prevent_infinite_loop_from_event_manager_idle_add
