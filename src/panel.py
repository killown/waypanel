from os import name
import sys
import lazy_loader as lazy
from typing import Any
from gi.repository import Adw, Gio, GLib  # pyright: ignore
from src.shared.config_handler import ConfigHandler

IPC_MODULE = lazy.load("src.core.compositor.ipc")
CREATE_PANEL_MODULE = lazy.load("src.core.create_panel")
GTK_HELPERS_MODULE = lazy.load("src.shared.gtk_helpers")
PLUGIN_LOADER_MODULE = lazy.load("src.core.plugin_loader.loader")
DATA_HELPERS_MODULE = lazy.load("src.shared.data_helpers")
PATH_HELPERS_MODULE = lazy.load("src.shared.path_handler")
GLOBAL_LOOP_MODULE = lazy.load("src.plugins.core._event_loop")


class Panel(Adw.Application):
    def __init__(self, logger, ipc_server, application_id=None):
        super().__init__(application_id=application_id)
        """
        Initializes the application and sets up required configurations and components.
        Args:
            application_id (str): The application ID.
        """
        self.logger = logger
        self.panel_instance = None
        self.style_css_config = None
        self.connect("activate", self.on_activate)
        self.config_handler = ConfigHandler(self)
        self.config_path = self.config_handler._setup_config_paths()
        self.config_data = self.config_handler.load_config()
        self.path_handler = PATH_HELPERS_MODULE.PathHandler(self)  # pyright: ignore
        self.ipc = IPC_MODULE.IPC()  # pyright: ignore
        self.data_helper = DATA_HELPERS_MODULE.DataHelpers()  # pyright: ignore
        self.ipc_server = ipc_server
        self.display = None
        self.args = sys.argv
        self.gtk_helpers = GTK_HELPERS_MODULE.GtkHelpers(self)  # pyright: ignore
        self.update_widget = self.gtk_helpers.update_widget
        self._set_monitor_dimensions()
        self.config_handler._start_watcher()
        self.plugins = None
        self.plugin_loader = None
        self.plugin_metadata = None
        GLib.idle_add(self.start_plugin_loader)

    def start_plugin_loader(self):
        self.plugin_loader = PLUGIN_LOADER_MODULE.PluginLoader(self)  # pyright: ignore
        self.plugins = self.plugin_loader.plugins
        self.plugin_metadata = self.plugin_loader.plugin_metadata_map
        return False

    def get_config(self, key_path: list[str] | str, default: Any = None) -> Any:
        """Safely retrieves a configuration value using a list of keys."""
        if isinstance(key_path, str):
            key_path = key_path.split(".")

        data = self.config_data
        for key in key_path:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return default
            if data is None:
                return default
        return data

    def get_setting_add_hint(
        self, key_path: list[str] | str, default_value: Any, hint: str | tuple[str, ...]
    ) -> Any:
        """
        Registers a configuration hint for the Control Center and returns the value.
        """
        plugin_id = "org.waypanel.panel"
        self.config_handler.set_setting_hint(plugin_id, key_path, hint)
        return self.get_config(key_path, default_value)

    def set_panel_instance(self, panel_instance):
        self.panel_instance = panel_instance

    def _set_monitor_dimensions(self):
        """
        Set monitor dimensions (width and height) based on the configuration file or default values.
        """
        self.logger.debug("Setting monitor dimensions...")
        outputs = self.ipc.list_outputs()
        if not outputs:
            self.logger.error("No monitors found via IPC. Cannot set dimensions.")
            self.monitor_width, self.monitor_height = 0, 0
            self.display = None
            return
        monitor = outputs[0]
        primary_output_name = self.get_config(
            ["org.waypanel.panel", "primary_output", "name"]
        )
        if primary_output_name:
            found_monitor = next(
                (
                    output
                    for output in self.ipc.list_outputs()
                    if output["name"] == primary_output_name
                ),
                None,
            )
            if found_monitor:
                monitor = found_monitor
            else:
                self.logger.warning(
                    f"Configured monitor '{primary_output_name}' not found. Falling back to default."
                )
        else:
            found_monitor = next(
                (
                    output
                    for output in self.ipc.list_outputs()
                    if "-1" in output["name"]
                ),
                None,
            )
            if found_monitor:
                monitor = found_monitor
            else:
                self.logger.warning(
                    "No primary monitor configured or found with '-1' in name. Using the first available monitor."
                )
        self.display = monitor
        if "current_mode" not in monitor:
            self.monitor_width, self.monitor_height = (
                monitor["geometry"]["width"],
                monitor["geometry"]["height"],
            )
        else:
            self.monitor_width, self.monitor_height = (
                monitor["current_mode"]["width"],
                monitor["current_mode"]["height"],
            )
        if "monitor" in self.config_data:
            config_monitor = self.config_data["monitor"]
            self.monitor_width = config_monitor.get("width", self.monitor_width)
            self.monitor_height = config_monitor.get("height", self.monitor_height)
            self.monitor_name = config_monitor.get("name", monitor.get("name"))
        self.logger.info(
            f"Monitor dimensions set: {self.monitor_width}x{self.monitor_height}"
        )

    def on_activate(self, *__):
        """
        Initializes the shell and sets up all required components.
        Args:
            app: The application instance.
        """
        self.logger.info("Activating application...")
        GLib.idle_add(self._load_plugins)
        self.logger.info("Application activation completed.")

    def _load_plugins(self):
        """
        Load plugins asynchronously.
        """
        if self.plugin_loader:
            self.logger.debug("Loading plugins...")
            self.plugin_loader.load_plugins()  # pyright: ignore
            self.logger.info("Plugins loading finished.")
            return False
        self.logger.warning("Panel: re-trying load plugins...")
        return True

    def do_activate(self):
        self.setup_panels()
        GLib.idle_add(self.load_css)

    def load_css(self):
        self.gtk_helpers.load_css_from_file()

        # Monitor ONLY the master generated styles.css
        styles_css_path = self.path_handler.get_config_dir() / "styles.css"
        self.css_monitors = []

        gio_file_css = Gio.File.new_for_path(str(styles_css_path))
        # Gio.FileMonitorFlags.NONE is fine; GTK will reload when the generator finishes writing
        monitor_css = gio_file_css.monitor_file(Gio.FileMonitorFlags.NONE, None)
        monitor_css.connect("changed", self.gtk_helpers.on_css_file_changed)
        self.css_monitors.append(monitor_css)

        self.logger.info("Panel CSS watcher attached to master styles.css")
        return False

    def setup_panels(self):
        """
        Set up all panels (top, bottom, left, right) based on the configuration.
        Each panel's properties are determined by the TOML configuration file.
        """
        self.logger.info("Setting up panels...")
        panel_toml = self.config_data.get("org.waypanel.panel", {})
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
                    pass
            except Exception as e:
                self.logger.error(
                    f"Failed to set up {panel_type} panel: {e}", exc_info=True
                )
        self.logger.info("Panels setup completed.")

    def _setup_top_panel(self, config):
        """
        Configure the top panel based on the provided configuration.
        """
        self.logger.debug("Setting up top panel...")
        anchor_edge = "TOP"
        css_class = "top-panel"

        exclusive = self.get_setting_add_hint(
            "org.waypanel.panel.top.Exclusive",
            bool(config.get("Exclusive", 1.0)),
            "Reserve space for the top panel",
        )
        layer_position = self.get_setting_add_hint(
            "org.waypanel.panel.top.layer_position",
            config.get("layer_position", "TOP"),
            "Layer position: BACKGROUND, BOTTOM, TOP, OVERLAY",
        )
        width = self.get_setting_add_hint(
            "org.waypanel.panel.top.width", self.monitor_width, "Width of the top panel"
        )
        height = self.get_setting_add_hint(
            "org.waypanel.panel.top.height", 32.0, "Height of the top panel"
        )

        namespace = "Waypanel-Top"

        self.top_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
            namespace,
        )
        if config.get("enabled", True):
            self.top_panel.present()
        self.logger.info("Top panel setup completed.")

    def _setup_bottom_panel(self, config):
        """
        Configure the bottom panel based on the provided configuration.
        """
        self.logger.debug("Setting up bottom panel...")
        anchor_edge = "BOTTOM"
        css_class = "bottom-panel"

        exclusive = self.get_setting_add_hint(
            "org.waypanel.panel.bottom.Exclusive",
            bool(config.get("Exclusive", 1.0)),
            "Reserve space for the bottom panel",
        )
        layer_position = self.get_setting_add_hint(
            "org.waypanel.panel.bottom.layer_position",
            config.get("layer_position", "BACKGROUND"),
            "Layer position: BACKGROUND, BOTTOM, TOP, OVERLAY",
        )
        width = self.get_setting_add_hint(
            "org.waypanel.panel.bottom.width",
            self.monitor_width,
            "Width of the bottom panel",
        )
        height = self.get_setting_add_hint(
            "org.waypanel.panel.bottom.height", 32.0, "Height of the bottom panel"
        )
        namespace = "Waypanel-Bottom"

        self.bottom_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
            namespace,
        )
        if config.get("enabled", True):
            self.bottom_panel.present()
        self.logger.info("Bottom panel setup completed.")

    def _setup_left_panel(self, config):
        """
        Configure the left panel based on the provided configuration.
        """
        self.logger.debug("Setting up left panel...")
        anchor_edge = "LEFT"
        css_class = "left-panel"

        exclusive = self.get_setting_add_hint(
            "org.waypanel.panel.left.Exclusive",
            bool(config.get("Exclusive", 1.0)),
            "Reserve space for the left panel",
        )
        layer_position = self.get_setting_add_hint(
            "org.waypanel.panel.left.layer_position",
            config.get("layer_position", "BACKGROUND"),
            "Layer position: BACKGROUND, BOTTOM, TOP, OVERLAY",
        )
        width = self.get_setting_add_hint(
            "org.waypanel.panel.left.width", 32.0, "Width of the left panel"
        )
        height = self.get_setting_add_hint(
            "org.waypanel.panel.left.height", 0.0, "Height of the left panel"
        )
        namespace = "Waypanel-Left"

        self.left_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
            namespace,
        )
        if config.get("enabled", True):
            self.left_panel.present()
        self.logger.info("Left panel setup completed.")

    def _setup_right_panel(self, config):
        """
        Configure the right panel based on the provided configuration.
        """
        self.logger.debug("Setting up right panel...")
        anchor_edge = "RIGHT"
        css_class = "right-panel"

        exclusive = self.get_setting_add_hint(
            "org.waypanel.panel.right.Exclusive",
            bool(config.get("Exclusive", 1.0)),
            "Reserve space for the right panel",
        )
        layer_position = self.get_setting_add_hint(
            "org.waypanel.panel.right.layer_position",
            config.get("layer_position", "BACKGROUND"),
            "Layer position: BACKGROUND, BOTTOM, TOP, OVERLAY",
        )
        width = self.get_setting_add_hint(
            "org.waypanel.panel.right.width", 32.0, "Width of the right panel"
        )
        height = self.get_setting_add_hint(
            "org.waypanel.panel.right.height", 0.0, "Height of the right panel"
        )
        namespace = "Waypanel-Right"

        self.right_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
            namespace,
        )
        if config.get("enabled", True):
            self.right_panel.present()
        self.logger.info("Right panel setup completed.")
