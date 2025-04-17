import os
import sys
import toml
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils

from waypanel.src.core.create_panel import (
    CreatePanel,
)
from waypanel.src.core.utils import Utils
from waypanel.src.core.utils import Utils as utils
from waypanel.src.plugins.core.dockbar import Dockbar
from waypanel.src.plugins.core.plugin_loader import PluginLoader


class Panel(Adw.Application):
    def __init__(self, logger, application_id=None):
        super().__init__(application_id=application_id)
        """
        Initializes the application and sets up required configurations and components.

        Args:
            application_id (str): The application ID.
        """
        self.logger = logger
        self.panel_instance = None
        # Initialize utilities and connect to activation event
        self._initialize_utilities()
        self.connect("activate", self.on_activate)

        # Setup panel boxes and configuration paths
        self._setup_panel_boxes()
        self._setup_config_paths()
        self.plugin_loader = PluginLoader(self, logger, self.config_path)

        # Initialize variables and configurations
        self.toggle_mute = {}
        self.volume = 0
        self.args = sys.argv
        self.source_id = None  # Store the source ID for the GLib.timeout

        # Initialize Wayfire components
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.fd = None
        self.utils = utils()
        self.get_icon = self.utils.get_icon

        # Initialize state variables
        self.active_window_changed = None
        self.notifications = []
        self.popover_bookmarks = None
        self.popover_clipboard = None
        self.set_cpu_usage_state = []
        self.clipboard_text_copy = None
        self.waypanel_started_now = True
        self.view_title_top_panel = None
        self.active_window = None
        self.last_toplevel_focused_view = None
        self.last_focused_output = None
        self.is_scale_active = None
        self.focused_output = None
        self.vol_slider = None
        self.dockbar_pending_events = []
        self.icon_vol_slider = None
        self.floating_volume_plugin = None
        self.workspace_empty = None
        self.timeout_ids = {}
        self.turn_off_monitors_timeout = None
        self.signal_view_destroyed = False
        self.previous_workspace = {}
        self.request_switch_keyboard_on_demand_to_none = None
        self.monitor = None
        self.update_widget = self.utils.update_widget
        self.panel_config_loaded = self.load_config()
        config = self.panel_config_loaded

        # Set monitor dimensions
        monitor = next(
            (output for output in self.sock.list_outputs() if "-1" in output["name"]),
            self.sock.list_outputs()[0],
        )
        self.monitor_width, self.monitor_height = (
            monitor["geometry"]["width"],
            monitor["geometry"]["height"],
        )

        if "monitor" in config:
            self.monitor_width, self.monitor_height = (
                config["monitor"]["width"],
                config["monitor"]["height"],
            )

        self.monitor_name = self.sock.list_outputs()[0]["name"]
        if "monitor" in config and "name" in config["monitor"]:
            self.monitor_name = config["monitor"]["name"]
        else:
            self.logger.info("Using the first monitor from the list.")

    def set_panel_instance(self, panel_instance):
        self.panel_instance = panel_instance

    def _initialize_utilities(self):
        """Initialize utility functions and properties."""
        self.utils = Utils(application_id="com.github.utils")

    def _setup_panel_boxes(self):
        """Setup panel boxes and related configurations."""
        self.top_panel_box_left = Gtk.Box()
        self.top_panel_box_systray = Gtk.Box()
        self.top_panel_box_for_buttons = Gtk.Box()
        self.top_panel_box_widgets_left = Gtk.Box()
        self.top_panel_box_left.append(self.top_panel_box_widgets_left)
        self.top_panel_box_right = Gtk.Box()
        self.spacer = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        # will set position of new widgets Gtk.Align.END
        self.spacer.set_hexpand(True)
        self.spacer.add_css_class("right-box-spacer")
        self.top_panel_box_right.append(self.spacer)
        self.top_panel_grid_right = Gtk.Grid()
        self.top_panel_grid_right.attach(self.top_panel_box_right, 1, 0, 1, 2)
        self.top_panel_grid_right.attach_next_to(
            self.top_panel_box_systray,
            self.top_panel_box_right,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )
        self.top_panel_grid_right.attach_next_to(
            self.top_panel_box_for_buttons,
            self.top_panel_box_systray,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )

        self.top_panel_box_center = Gtk.Box()
        self.top_panel_box_full = Gtk.Grid()
        self.top_panel_box_full.set_column_homogeneous(True)
        self.top_panel_box_full.attach(self.top_panel_box_left, 1, 0, 1, 2)
        self.top_panel_box_full.attach_next_to(
            self.top_panel_box_center,
            self.top_panel_box_left,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )
        self.top_panel_box_full.attach_next_to(
            self.top_panel_grid_right,
            self.top_panel_box_center,
            Gtk.PositionType.RIGHT,
            1,
            3,
        )
        # load the Dockbar
        self.dock = Dockbar(application_id="com.github.dockbar", logger=self.logger)
        self.top_panel_box_center.set_halign(Gtk.Align.CENTER)
        self.top_panel_box_center.set_valign(Gtk.Align.CENTER)
        self.top_panel_box_center.set_hexpand(False)

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        config_paths = self.utils.setup_config_paths()
        # Set instance variables from the dictionary
        self.home = config_paths["home"]
        self.waypanel_cfg = os.path.join(self.home, ".config/waypanel/waypanel.toml")
        self.scripts = config_paths["scripts"]
        self.config_path = config_paths["config_path"]
        self.style_css_config = config_paths["style_css_config"]
        self.cache_folder = config_paths["cache_folder"]

    def on_activate(self, app):
        """
        Initializes the shell and sets up all required components.

        Args:
            app: The application instance.
        """
        # Initialize monitor dimensions and UI components
        self.setup_panels()
        self.setup_panel_buttons()

        # Verify required plugins are enabled
        required_plugins = {
            "stipc",
            "ipc",
            "ipc-rules",
            "resize",
            "window-rules",
            "wsets",
            "session-lock",
            "wm-actions",
            "move",
            "vswitch",
            "grid",
            "place",
            "scale",
        }
        enabled_plugins = set(
            self.sock.get_option_value("core/plugins")["value"].split()
        )

        missing_plugins = required_plugins - enabled_plugins
        if missing_plugins:
            self.logger.error(
                f"\n\033[91mERROR:\033[0m The following plugins are required to start the shell: {missing_plugins}"
            )
            self.logger.info(f"Required Plugin List: {required_plugins}")
            sys.exit()

        # ===========LOAD PLUGINS=============
        self.logger.info("Starting panel...")
        GLib.idle_add(self.plugin_loader.load_plugins)

    def load_config(self):
        if not hasattr(self, "_cached_config"):
            with open(self.waypanel_cfg, "r") as f:
                self._cached_config = toml.load(f)
        return self._cached_config

    def check_widgets_ready(self):
        if (
            self.utils.is_widget_ready(self.top_panel_box_left)
            and self.utils.is_widget_ready(self.top_panel_box_widgets_left)
            and self.utils.is_widget_ready(self.top_panel_box_right)
            and self.utils.is_widget_ready(self.top_panel_box_systray)
            and self.utils.is_widget_ready(self.top_panel_box_center)
            and self.utils.is_widget_ready(self.top_panel_box_full)
        ):
            # Apply CSS classes
            self.update_widget(
                self.top_panel_box_left.add_css_class, "top_panel_box_left"
            )
            self.update_widget(
                self.top_panel_box_widgets_left.add_css_class,
                "top_panel_box_widgets_left",
            )
            self.update_widget(
                self.top_panel_box_right.add_css_class, "top_panel_box_right"
            )
            self.update_widget(
                self.top_panel_box_systray.add_css_class, "top_panel_box_systray"
            )
            self.update_widget(
                self.top_panel_box_center.add_css_class, "top_panel_box_center"
            )
            self.update_widget(
                self.top_panel_box_full.add_css_class, "top_panel_box_full"
            )

            return False
        else:
            # Retry after a delay
            GLib.timeout_add(1, self.check_widgets_ready)
            return True

    def do_activate(self):
        # activate auto start apps
        self.load_css_from_file()
        # Start monitoring CSS file for changes
        self.monitor = Gio.File.new_for_path(self.style_css_config).monitor(
            Gio.FileMonitorFlags.NONE, None
        )
        self.monitor.connect("changed", self.on_css_file_changed)
        self.check_widgets_ready()
        self.show_panels()

    def monitor_width_height(self):
        focused_view = self.sock.get_focused_view()
        if focused_view:
            output = self.utils.get_monitor_info()
            output = output[self.monitor_name]
            self.monitor_width = output[0]
            self.monitor_height = output[1]

    def show_panels(self):
        if self.all_panels_enabled:
            self.top_panel.present()
            self.dock.do_start()

    def setup_panel_buttons(self):
        if self.default_panel:
            self.top_panel.set_content(self.top_panel_box_full)
        if [i for i in self.args if "topbar" in i]:
            self.all_panels_enabled = False
            self.top_panel.present()

    def on_css_file_changed(self, monitor, file, other_file, event_type):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            # Reload CSS when changes are done
            def run_once():
                self.load_css_from_file()
                return False

            GLib.idle_add(run_once)

    def load_css_from_file(self):
        # you need to append the widgets to their parent containers first and then add_css_class
        css_provider = Gtk.CssProvider()
        css_provider.load_from_file(Gio.File.new_for_path(self.style_css_config))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def setup_panels(self):
        self.panel_on_top = "TOP"
        self.exclusive = True
        self.all_panels_enabled = True

        self.top_panel_box_right.set_halign(Gtk.Align.FILL)

        if "--custom" in self.args:
            self.default_panel = False

        if "--background" in self.args:
            self.exclusive = False

        self.default_panel = True
        panel_toml = self.panel_config_loaded["panel"]
        for p in panel_toml:
            if "bottom" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False

                position = panel_toml[p]["position"]
                size = panel_toml[p]["size"]
                self.bottom_panel = CreatePanel(
                    self.panel_instance,
                    "BOTTOM",
                    position,
                    self.exclusive,
                    width=size,
                    height=0,
                    class_style="BottomBar",
                )

            if "right" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                self.right_panel = CreatePanel(
                    self.panel_instance,
                    "RIGHT",
                    position,
                    self.exclusive,
                    0,
                    32,
                    "RightBar",
                )
            if "left" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                size = panel_toml[p]["size"]
                self.left_panel = CreatePanel(
                    self.panel_instance,
                    "LEFT",
                    position,
                    self.exclusive,
                    0,
                    size,
                    "LeftBar",
                )

            if "top" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                size = panel_toml[p]["size"]
                self.top_panel = CreatePanel(
                    self.panel_instance,
                    "TOP",
                    position,
                    self.exclusive,
                    self.monitor_width,
                    size,
                    "TopBar",
                )
            if "top_background" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                self.top_panel_background = CreatePanel(
                    self.panel_instance,
                    "TOP",
                    position,
                    self.exclusive,
                    self.monitor_width,
                    24,
                    "TopBarBackground",
                )
