from gi.repository import Gtk, GLib

from wayfire import WayfireSocket
import os
import orjson as json
import toml
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.extra.stipc import Stipc
from ...core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

# Enable or disable the plugin
ENABLE_PLUGIN = True
DEPS = ["event_manager", "gestures_setup"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "right-panel"
    # priority position is from waypanel.toml [dockbar_panel.position] = "left"
    # the dockbar will be on left ignoring hardcoded position
    dockbar_config = panel_instance.config.get("dockbar_panel", {})
    if dockbar_config:
        if "panel" in dockbar_config:
            position = dockbar_config["panel"]
            position = f"{position}-panel"
    order = 5
    priority = 1
    return position, order, priority


def initialize_plugin(panel_instance):
    """Initialize the Dockbar plugin."""
    if ENABLE_PLUGIN:
        dockbar = DockbarPlugin(panel_instance)
        return dockbar


class DockbarPlugin:
    def __init__(self, panel_instance):
        """Initialize the Dockbar plugin."""
        self.logger = panel_instance.logger
        self.obj = panel_instance
        # Subscribe to events using the event_manager
        self.plugins = self.obj.plugin_loader.plugins
        self.create_gesture = self.obj.plugins["gestures_setup"].create_gesture
        self._subscribe_to_events()
        self.utils = self.obj.utils
        self.layer_state = False
        self.taskbar_list = []
        self.dockbar_panel = None
        self.buttons_id = {}
        self.sock = WayfireSocket()  # Use the shared WayfireSocket instance
        self.wf_utils = WayfireUtils(self.sock)
        self.stipc = Stipc(self.sock)
        self.dockbar = None
        self.update_widget = self.utils.update_widget

        # Load configuration and set up dockbar
        self.config = panel_instance.config
        self._setup_dockbar()

    def is_scale_enabled(self):
        sock = WayfireSocket()
        plugins = sock.get_option_value("core/plugins")["value"].split()
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
            self.logger.error_handler.handle(f"Invalid panel value: {panel}")

    def choose_and_set_dockbar(self):
        panel = get_plugin_placement(self.obj)[0]

        dockbar_config = self.config.get("dockbar_panel", {})
        if dockbar_config:
            if "panel" in dockbar_config:
                position = dockbar_config["panel"]
                panel = f"{position}-panel"

        # Validate panel value
        valid_panels = {"left-panel", "right-panel", "bottom-panel", "top-panel"}
        if panel not in valid_panels:
            self.logger.error_handler.handle(
                f"Invalid panel value: {panel}. Using default 'left-panel'."
            )
            panel = "left-panel"

        self.dockbar_panel = self.get_dockbar_position(panel)

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
            app_id = None
            initial_title = None
            try:
                app_id = config_data[app]["wclass"]
            except KeyError:
                pass

            # Retrieve the command for this app
            app_cmd = config_data[app]["cmd"]

            # Create the button
            button = self.utils.create_button(
                self.utils.get_nearest_icon_name(config_data[app]["icon"]),
                app_cmd,
                class_style,
                app_id,
                initial_title,
                use_label,
            )

            # Add middle-click gesture
            self.create_gesture(
                button, 2, lambda _, cmd=app_cmd: self.on_middle_click(cmd)
            )

            # Add right-click gesture
            self.create_gesture(
                button, 3, lambda _, cmd=app_cmd: self.on_right_click(cmd)
            )

            # Append the button to the box
            self.update_widget(box.append, button)

        return box

    def on_right_click(self, cmd):
        """
        Handle right-click action: Move the cursor to the next available output
        and open the app there.

        Args:
            cmd (str): The command to execute for the app.
        """
        try:
            # Get the list of outputs and the currently focused output
            outputs = self.sock.list_outputs()
            focused_output = self.sock.get_focused_output()

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
            self.stipc.move_cursor(cursor_x, cursor_y)
            self.stipc.click_button("S-BTN_LEFT", "full")

            # Open the app
            self.utils.run_cmd(cmd)

        except Exception as e:
            self.logger.error_handler.handle(
                error=e, message="Error while handling right-click action."
            )

    def on_middle_click(self, cmd):
        # Check for empty workspace
        coordinates = self.utils.find_empty_workspace()
        if coordinates:
            ws_x, ws_y = coordinates
            self.sock.scale_toggle()
            self.sock.set_workspace(ws_x, ws_y)
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
        self.choose_and_set_dockbar()
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
            box.append(icon)

        label = Gtk.Label(label=title[:30])
        box.append(label)

        button.set_child(box)
        button.add_css_class("dockbar-button")

        # Handle button click
        button.connect("clicked", lambda *_: self.utils.focus_view_when_ready(view))

        return button

    def on_scale_activated(self):
        """Handle scale wayfire plugin activation."""
        # set layer exclusive so the panels becomes clickable
        output_info = os.getenv("waypanel")
        layer_set_on_output_name = None
        if output_info:
            layer_set_on_output_name = json.loads(output_info).get("output_name")
        focused_output_name = self.sock.get_focused_output()["name"]
        # only set layer if the focused output is the same as the defined in panel creation
        if layer_set_on_output_name == focused_output_name:
            self.update_widget(set_layer_position_exclusive, self.dockbar_panel, 64)
            self.layer_state = True

    def on_scale_desactivated(self):
        """Handle scale plugin deactivation."""
        # this will set panels on bottom, hidden it from views
        self.update_widget(unset_layer_position_exclusive, self.dockbar_panel)
        self.layer_state = False

    def panel_set_content(self):
        """Return the dockbar widget to be added to the panel."""
        return self.dockbar

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
