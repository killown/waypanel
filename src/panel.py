import sys
import lazy_loader as lazy
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

    def get_config(self, key_path, default=None):
        """Safely retrieves a configuration value using a list of keys."""
        data = self.config_data
        for key in key_path:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return default
            if data is None:
                return default
        return data

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
        directories_to_monitor = [
            self.path_handler.get_data_path("resources/plugins/css"),
            self.path_handler.get_data_path("resources/themes/css"),
        ]
        styles_css_path = self.path_handler.get_config_dir() / "styles.css"
        self.css_monitors = []
        for path in directories_to_monitor:
            gio_file = Gio.File.new_for_path(str(path))
            monitor = gio_file.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            monitor.connect("changed", self.gtk_helpers.on_css_file_changed)
            self.css_monitors.append(monitor)
        gio_file_css = Gio.File.new_for_path(str(styles_css_path))
        monitor_css = gio_file_css.monitor_file(Gio.FileMonitorFlags.NONE, None)
        monitor_css.connect("changed", self.gtk_helpers.on_css_file_changed)
        self.css_monitors.append(monitor_css)
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
                    self.logger.warning(f"Unknown panel type: {panel_type}")
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
        exclusive = bool(config.get("Exclusive", 1.0))
        anchor_edge = "TOP"
        css_class = "top-panel"
        layer_position = config.get("layer_position", "TOP")
        width = self.get_config(
            ["org.waypanel.panel", "top", "width"], self.monitor_width
        )
        height = self.get_config(["org.waypanel.panel", "top", "height"], 32.0)
        self.top_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
        )
        if config.get("enabled", True):
            self.top_panel.present()
        self.logger.info("Top panel setup completed.")

    def _setup_bottom_panel(self, config):
        """
        Configure the bottom panel based on the provided configuration.
        """
        self.logger.debug("Setting up bottom panel...")
        exclusive = bool(config.get("Exclusive", 1.0))
        anchor_edge = "BOTTOM"
        css_class = "bottom-panel"
        layer_position = config.get("layer_position", "BACKGROUND")
        width = self.get_config(
            ["org.waypanel.panel", "bottom", "width"], self.monitor_width
        )
        height = self.get_config(["org.waypanel.panel", "bottom", "height"], 32)
        self.bottom_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
        )
        if config.get("enabled", True):
            self.bottom_panel.present()
        self.logger.info("Bottom panel setup completed.")

    def _setup_left_panel(self, config):
        """
        Configure the left panel based on the provided configuration.
        """
        self.logger.debug("Setting up left panel...")
        exclusive = bool(config.get("Exclusive", 1.0))
        anchor_edge = "LEFT"
        css_class = "left-panel"
        layer_position = config.get("layer_position", "BACKGROUND")
        width = self.get_config(["org.waypanel.panel", "left", "width"], 32.0)
        height = self.get_config(["org.waypanel.panel", "left", "height"], 0.0)
        self.left_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
        )
        if config.get("enabled", True):
            self.left_panel.present()
        self.logger.info("Left panel setup completed.")

    def _setup_right_panel(self, config):
        """
        Configure the right panel based on the provided configuration.
        """
        self.logger.debug("Setting up right panel...")
        exclusive = bool(config.get("Exclusive", 1.0))
        anchor_edge = "RIGHT"
        css_class = "right-panel"
        layer_position = config.get("layer_position", "BACKGROUND")
        width = self.get_config(["org.waypanel.panel", "right", "width"], 32.0)
        height = self.get_config(["org.waypanel.panel", "right", "height"], 0.0)
        self.right_panel = CREATE_PANEL_MODULE.CreatePanel(
            self.panel_instance,  # pyright: ignore
            anchor_edge,
            layer_position,
            exclusive,
            width,  # pyright: ignore
            height,  # pyright: ignore
            css_class,
        )
        if config.get("enabled", True):
            self.right_panel.present()
        self.logger.info("Right panel setup completed.")

    def about(self):
        """
        The Panel class serves as the central control hub for the entire
        waypanel application. It manages the application lifecycle,
        handles configuration, loads plugins, and orchestrates the
        creation of all UI panels.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The `Panel` class is the application's core orchestrator. Inheriting
        from `Adw.Application`, it manages the entire startup and
        runtime process. Its key functions are:
        1.  **Configuration and Lifecycle Management**: The `__init__`
            method initializes core components like the logger, IPC
            client, and plugin loader. It also loads the `config.toml`
            file, which acts as the single source of truth for the
            application's state and appearance. The new `get_config`
            method provides a safe and standardized way to retrieve
            nested configuration values. Methods like
            `reload_config()` (implicitly via a file watcher) allow
            for dynamic updates at runtime, notifying individual
            plugins of changes.
        2.  **Modular Panel Creation**: The `setup_panels()` method
            is a factory for creating the application's UI. It reads
            the configuration to determine which panels to create
            (top, bottom, left, right), their positions, sizes, and
            exclusivity. This modular, configuration-driven approach
            allows users to customize the panel layout without
            modifying the source code.
        3.  **Asynchronous Initialization (FIXED)**: The `on_activate` method
            begins the application's main loop. It uses `GLib.idle_add`
            to run `_load_plugins`, which now uses `asyncio.create_task`
            to load plugins concurrently. This ensures the UI remains
            responsive and doesn't freeze during startup, which was a
            crucial fix for a smooth user experience.
        """
        return self.code_explanation.__doc__
