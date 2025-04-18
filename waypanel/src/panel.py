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

from waypanel.src.core.plugin_loader import PluginLoader


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
        self.args = sys.argv

        # Initialize Wayfire components
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.utils = utils()

        # Initialize state variables
        self.monitor = None
        self.update_widget = self.utils.update_widget
        self.config = self.load_config()
        self._set_monitor_dimensions()

    def set_panel_instance(self, panel_instance):
        self.panel_instance = panel_instance

    def _initialize_utilities(self):
        """Initialize utility functions and properties."""
        self.utils = Utils(application_id="com.github.utils")

    def _set_monitor_dimensions(self):
        """
        Set monitor dimensions (width and height) based on the configuration file or default values.
        """
        self.logger.debug("Setting monitor dimensions...")

        # Retrieve monitor information
        monitor = next(
            (output for output in self.sock.list_outputs() if "-1" in output["name"]),
            self.sock.list_outputs()[0],
        )

        # Default dimensions from the monitor geometry
        self.monitor_width, self.monitor_height = (
            monitor["geometry"]["width"],
            monitor["geometry"]["height"],
        )

        # Override dimensions if specified in the configuration
        if "monitor" in self.config:
            config_monitor = self.config["monitor"]
            self.monitor_width = config_monitor.get("width", self.monitor_width)
            self.monitor_height = config_monitor.get("height", self.monitor_height)
            self.monitor_name = config_monitor.get("name", self.monitor_name)

        self.logger.info(
            f"Monitor dimensions set: {self.monitor_width}x{self.monitor_height}"
        )

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
        self.top_panel_box_center.set_halign(Gtk.Align.CENTER)
        self.top_panel_box_center.set_valign(Gtk.Align.CENTER)
        self.top_panel_box_center.set_hexpand(False)

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        config_paths = self.utils.setup_config_paths()
        self.home = config_paths["home"]
        self.waypanel_cfg = os.path.join(self.home, ".config/waypanel/waypanel.toml")
        self.scripts = config_paths["scripts"]
        self.config_path = config_paths["config_path"]
        self.style_css_config = config_paths["style_css_config"]
        self.cache_folder = config_paths["cache_folder"]

    def on_activate(self, *__):
        """
        Initializes the shell and sets up all required components.

        Args:
            app: The application instance.
        """
        self.logger.info("Activating application...")

        # Initialize essential components
        self._load_plugins()

        self.logger.info("Application activation completed.")

    def _load_plugins(self):
        """
        Load plugins asynchronously.
        """
        self.logger.debug("Loading plugins...")
        GLib.idle_add(self.plugin_loader.load_plugins)
        self.logger.info("Plugins loading initiated.")

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
        self.setup_panels()
        # self.dock.do_start()

    def monitor_width_height(self):
        focused_view = self.sock.get_focused_view()
        if focused_view:
            output = self.utils.get_monitor_info()
            output = output[self.monitor_name]
            self.monitor_width = output[0]
            self.monitor_height = output[1]

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
        """
        Set up all panels (top, bottom, left, right) based on the configuration.
        Each panel's properties are determined by the TOML configuration file.
        """
        self.logger.info("Setting up panels...")

        # Load panel configuration from the TOML file
        panel_toml = self.config.get("panel", {})

        # Iterate through each panel type and configure it
        for panel_type, config in panel_toml.items():
            try:
                if panel_type == "top":
                    self._setup_top_panel(config)
                elif panel_type == "bottom":
                    self._setup_bottom_panel(config)
                elif panel_type == "left":
                    self._setup_left_panel(config)
                elif panel_type == "right":
                    self._setup_right_panel(config)
                else:
                    self.logger.warning(f"Unknown panel type: {panel_type}")
            except Exception as e:
                self.logger.error(
                    f"Failed to set up {panel_type} panel: {e}", exc_info=True
                )
        self.top_panel.set_content(self.top_panel_box_full)
        self.logger.info("Panels setup completed.")

    def _setup_top_panel(self, config):
        """
        Configure the top panel based on the provided configuration.
        Args:
            config (dict): Configuration for the top panel.
        """
        self.logger.debug("Setting up top panel...")

        exclusive = config.get("Exclusive", "True") == "True"
        position = config.get("position", "top")
        size = config.get("size", 32)

        self.top_panel = CreatePanel(
            self.panel_instance,
            "TOP",
            position,
            exclusive,
            self.monitor_width,
            size,
            "top-panel",
        )

        if config.get("enabled", True):
            self.top_panel.present()

        self.logger.info("Top panel setup completed.")

    def _setup_bottom_panel(self, config):
        """
        Configure the bottom panel based on the provided configuration.
        Args:
            config (dict): Configuration for the bottom panel.
        """
        self.logger.debug("Setting up bottom panel...")

        exclusive = config.get("Exclusive", "True") == "True"
        position = config.get("position", "bottom")
        size = config.get("size", 32)

        self.bottom_panel = CreatePanel(
            self.panel_instance, "BOTTOM", position, exclusive, 0, size, "BottomBar"
        )

        if config.get("enabled", True):
            self.bottom_panel.present()

        self.logger.info("Bottom panel setup completed.")

    def _setup_left_panel(self, config):
        """
        Configure the left panel based on the provided configuration.
        Args:
            config (dict): Configuration for the left panel.
        """
        self.logger.debug("Setting up left panel...")

        exclusive = config.get("Exclusive", "True") == "True"
        position = config.get("position", "left")
        size = config.get("size", 64)

        self.left_panel = CreatePanel(
            self.panel_instance, "LEFT", position, exclusive, 0, size, "left-panel"
        )

        if config.get("enabled", True):
            self.left_panel.present()

        self.logger.info("Left panel setup completed.")

    def _setup_right_panel(self, config):
        """
        Configure the right panel based on the provided configuration.
        Args:
            config (dict): Configuration for the right panel.
        """
        self.logger.debug("Setting up right panel...")

        exclusive = config.get("Exclusive", "True") == "True"
        position = config.get("position", "right")
        size = config.get("size", 64)

        self.right_panel = CreatePanel(
            self.panel_instance, "RIGHT", position, exclusive, size, 0, "right-panel"
        )

        if config.get("enabled", True):
            self.right_panel.present()

        self.logger.info("Right panel setup completed.")
