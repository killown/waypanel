import os
import sys
import toml
from gi.repository import Adw, Gio, GLib
from src.core.compositor.ipc import IPC
from typing import Dict, Any
from src.core.create_panel import (
    CreatePanel,
)
from src.core.utils import Utils
from src.plugins.utils._plugin_loader import PluginLoader


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
        self.connect("activate", self.on_activate)
        self.utils = Utils(self)
        self._setup_config_paths()
        self.plugin_loader = PluginLoader(self, logger, self.config_path)
        self.plugins = self.plugin_loader.plugins
        self.ipc = IPC()
        self.ipc_server = ipc_server
        self.display = None
        self.args = sys.argv
        self.css_monitor = None
        self.update_widget = self.utils.update_widget

        outputs = self.ipc.list_outputs()
        if outputs:
            self.first_output = outputs[0]
            if "name" in self.first_output:
                self.first_output_name = self.first_output["name"]
        else:
            self.first_output_name = None

        self.default_config = {
            "panel": {
                "primary_output": {"output_name": self.first_output_name},
                "bottom": {
                    "enabled": 1.0,
                    "position": "BOTTOM",
                    "Exclusive": 0.0,
                    "size": 42.0,
                },
                "left": {
                    "enabled": 1.0,
                    "position": "BOTTOM",
                    "Exclusive": 0.0,
                    "size": 64.0,
                },
                "right": {
                    "enabled": 1.0,
                    "position": "BOTTOM",
                    "Exclusive": 0.0,
                    "size": 42.0,
                },
                "top": {
                    "menu_icon": "archlinux-logo",
                    "folder_icon": "folder",
                    "bookmarks_icon": "internet-web-browser",
                    "clipboard_icon": "edit-paste",
                    "soundcard_icon": "audio-volume-high",
                    "system_icon": "system-shutdown",
                    "bluetooth_icon": "bluetooth",
                    "notes_icon": "stock_notes",
                    "notes_icon_delete": "delete",
                    "position": "TOP",
                    "Exclusive": 1.0,
                    "height": 32.0,
                    "size": 12.0,
                    "max_note_lenght": 100.0,
                },
            }
        }

        self.config = self.load_config()

        self._set_monitor_dimensions()

    def set_panel_instance(self, panel_instance):
        self.panel_instance = panel_instance

    def _set_monitor_dimensions(self):
        """
        Set monitor dimensions (width and height) based on the configuration file or default values.
        """
        self.logger.debug("Setting monitor dimensions...")

        # Default to the first output found
        outputs = self.ipc.list_outputs()
        if not outputs:
            self.logger.error("No monitors found via IPC. Cannot set dimensions.")
            self.monitor_width, self.monitor_height = 0, 0
            self.display = None
            return

        monitor = outputs[0]

        primary_output_name = (
            self.config.get("panel", {}).get("primary_output", {}).get("output_name")
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
            # Wayfire socket
            self.monitor_width, self.monitor_height = (
                monitor["geometry"]["width"],
                monitor["geometry"]["height"],
            )
        else:
            # Sway socket
            self.monitor_width, self.monitor_height = (
                monitor["current_mode"]["width"],
                monitor["current_mode"]["height"],
            )

        # Override dimensions if specified in the configuration
        if "monitor" in self.config:
            config_monitor = self.config["monitor"]
            self.monitor_width = config_monitor.get("width", self.monitor_width)
            self.monitor_height = config_monitor.get("height", self.monitor_height)
            self.monitor_name = config_monitor.get("name", monitor.get("name"))

        self.logger.info(
            f"Monitor dimensions set: {self.monitor_width}x{self.monitor_height}"
        )

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        config_paths = self.utils.setup_config_paths()
        self.home = config_paths["home"]
        self.waypanel_cfg = os.path.join(self.home, ".config/waypanel/config.toml")
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

    def save_config(self):
        """
        Save the current configuration back to the config.toml file.
        """
        try:
            with open(self.waypanel_cfg, "w") as f:
                toml.dump(self.config, f)
            self.logger.info("Configuration saved successfully.")
        except Exception as e:
            self.logger.error(
                error=e,
                message="Failed to save configuration to file.",
                level="error",
            )

    def reload_config(self):
        """
        Reload the configuration from the config.toml file and propagate changes to plugins.
        """
        try:
            # Reload the configuration
            new_config = self.load_config()

            # Update the current configuration
            self.config.update(new_config)

            # Notify all plugins about the configuration change
            for plugin_name, plugin_instance in self.plugins.items():
                if hasattr(plugin_instance, "on_config_reloaded"):
                    try:
                        plugin_instance.on_config_reloaded(new_config)
                    except Exception as e:
                        self.logger.error(
                            f"Error notifying plugin '{plugin_name}' of config reload: {e}"
                        )

            self.logger.info("Configuration reloaded successfully.")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")

    def load_config(self) -> Dict[str, Any]:
        """Load and cache the panel configuration from the config.toml file,
        merging with defaults if needed.

        Returns:
            dict: The combined configuration data.
        """
        config_from_file = {}
        try:
            with open(self.waypanel_cfg, "r") as f:
                config_from_file = toml.load(f)
            self.logger.debug("Existing config.toml loaded.")
        except FileNotFoundError:
            self.logger.info("config.toml not found. Creating with default settings.")
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}. Using defaults.")

        def deep_merge(a: dict, b: dict, path=None) -> dict:
            if path is None:
                path = []
            for key in b:
                if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
                    deep_merge(a[key], b[key], path + [str(key)])
                else:
                    a[key] = b[key]
            return a

        combined_config = deep_merge(self.default_config.copy(), config_from_file)

        os.makedirs(os.path.dirname(self.waypanel_cfg), exist_ok=True)
        with open(self.waypanel_cfg, "w") as f:
            toml.dump(combined_config, f)
        self.logger.info("Merged configuration saved to config.toml.")

        self._cached_config = combined_config
        return self._cached_config

    def do_activate(self):
        self.utils.load_css_from_file()
        self.css_monitor = Gio.File.new_for_path(self.style_css_config).monitor(
            Gio.FileMonitorFlags.NONE, None
        )
        self.css_monitor.connect("changed", self.utils.on_css_file_changed)
        self.setup_panels()

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
        self.logger.info("Panels setup completed.")

    def _setup_top_panel(self, config):
        """
        Configure the top panel based on the provided configuration.
        Args:
            config (dict): Configuration for the top panel.
        """
        self.logger.debug("Setting up top panel...")

        exclusive = config.get("Exclusive")
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
            application's state and appearance. Methods like
            `reload_config()` allow for dynamic updates at runtime,
            notifying individual plugins of changes.

        2.  **Modular Panel Creation**: The `setup_panels()` method
            is a factory for creating the application's UI. It reads
            the configuration to determine which panels to create
            (top, bottom, left, right), their positions, sizes, and
            exclusivity. This modular, configuration-driven approach
            allows users to customize the panel layout without
            modifying the source code.

        3.  **Asynchronous Initialization**: The `on_activate` method
            begins the application's main loop. It uses `GLib.idle_add`
            to load plugins asynchronously, ensuring the UI remains
            responsive and doesn't freeze during startup. This is
            a crucial design choice for a smooth user experience.
        """
        return self.code_explanation.__doc__
