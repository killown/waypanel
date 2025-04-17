from gi.repository import Gtk, GLib
from ...core.utils import Utils
from wayfire import WayfireSocket
import os
import orjson as json
from wayfire.extra.ipc_utils import WayfireUtils
from ...core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

# Enable or disable the plugin
ENABLE_PLUGIN = True


def get_plugin_placement():
    """Define the plugin's position and order."""
    position = "left-panel"  # Can be "left", "right", "center", or "systray"
    order = 5  # Lower numbers have higher priority
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the Dockbar plugin."""
    if ENABLE_PLUGIN:
        print("Initializing Dockbar Plugin.")
        dockbar = DockbarPlugin(panel_instance)
        return dockbar


class DockbarPlugin:
    def __init__(self, panel_instance):
        """Initialize the Dockbar plugin."""
        self.logger = panel_instance.logger
        self.obj = panel_instance
        self.utils = Utils()
        self.taskbar_list = []
        self.buttons_id = {}
        self.sock = WayfireSocket()  # Use the shared WayfireSocket instance
        self.wf_utils = WayfireUtils(self.sock)  # Use the shared WayfireUtils instance
        self.dockbar = None
        self.update_widget = self.utils.update_widget

        # Load configuration and set up dockbar
        self.config = panel_instance.config
        self._setup_dockbar()

        # Subscribe to events using the event_manager
        self._subscribe_to_events()

    def _setup_dockbar(self):
        """Set up the dockbar based on the configuration."""
        dockbar_toml = self.config.get("dockbar", {})
        orientation = dockbar_toml.get("orientation", "v")  # Vertical by default
        class_style = dockbar_toml.get("class_style", "dockbar-buttons")

        self.dockbar = self.utils.CreateFromAppList(
            self.obj.waypanel_cfg, orientation, class_style
        )
        self.logger.info("Dockbar setup completed.")

    def _subscribe_to_events(self):
        """Subscribe to relevant events using the event_manager."""

        def is_event_manager_ready():
            if "event_manager" not in self.obj.plugin_loader.plugins:
                self.obj.logger("dockbar is waiting for event manager")
                return True
            else:
                event_manager = self.obj.plugin_loader.plugins["event_manager"]
                self.logger.info("Subscribing to events for Dockbar Plugin.")
                event_manager.subscribe_to_event(
                    "plugin-activation-state-changed", self.handle_plugin_event
                )
                return False

        GLib.timeout_add_seconds(1, is_event_manager_ready)

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
            set_layer_position_exclusive(self.obj.left_panel, 64)

    def on_scale_desactivated(self):
        """Handle scale plugin deactivation."""
        # this will set panels on bottom, hidden it from views
        self.update_widget(unset_layer_position_exclusive, self.obj.left_panel)
        return False

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
