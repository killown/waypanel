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
        self.config = self.load_config()
        self._set_monitor_dimensions()

    def set_panel_instance(self, panel_instance):
        self.panel_instance = panel_instance

    def _set_monitor_dimensions(self):
        """
        Set monitor dimensions (width and height) based on the configuration file or default values.
        """
        self.logger.debug("Setting monitor dimensions...")

        # Retrieve monitor information
        monitor = next(
            (output for output in self.ipc.list_outputs() if "-1" in output["name"]),
            self.ipc.list_outputs()[0],
        )

        self.display = monitor

        # Default dimensions from the monitor geometry
        # FIXME: need a proper way to handle that,
        # better case is format sway ipc data to have a default data pattern as wayfire
        if (
            "current_mode" not in monitor
        ):  # in case current_mode is in monitor, then it's swayIPC
            # wayfire socket here
            self.monitor_width, self.monitor_height = (
                monitor["geometry"]["width"],
                monitor["geometry"]["height"],
            )
        else:
            # sway socket here
            self.monitor_width, self.monitor_height = (
                monitor["current_mode"]["width"],
                monitor["current_mode"]["height"],
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

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        config_paths = self.utils.setup_config_paths()
        self.home = config_paths["home"]
        self.waypanel_cfg = os.path.join(self.home, ".config/waypanel/waypanel.toml")
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
        Save the current configuration back to the waypanel.toml file.
        """
        try:
            with open(self.waypanel_cfg, "w") as f:
                toml.dump(self._cached_config, f)
            self.logger.info("Configuration saved successfully.")
        except Exception as e:
            self.logger.error(
                error=e,
                message="Failed to save configuration to file.",
                level="error",
            )

    def reload_config(self):
        """
        Reload the configuration from the waypanel.toml file and propagate changes to plugins.
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
        """Load and cache the panel configuration from the waypanel.toml file.

        Returns:
            dict: Parsed TOML configuration data. If already loaded, returns the cached version.
        """
        if not hasattr(self, "_cached_config"):
            with open(self.waypanel_cfg, "r") as f:
                self._cached_config = toml.load(f)
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
