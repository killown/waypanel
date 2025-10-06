import os
import toml
import time
from pathlib import Path
from typing import Dict, Any, List
from wayfire import WayfireSocket
from gi.repository import Gio  # pyright: ignore
from src.shared import config_template


class ConfigHandler:
    def __init__(self, panel_instance):
        self.logger = panel_instance.logger
        self.panel_instance = panel_instance
        self._cached_config = None
        self._last_mod_time = 0.0
        self.default_config = config_template.default_config
        self._setup_config_paths()
        self.config_file = Path(self.config_path) / "config.toml"
        self.gio_config_file = Gio.File.new_for_path(str(self.config_file))
        self.config_monitor = None
        self.config_path = self.config_file.parent  # pyright: ignore
        self._load_successful = False
        sock = WayfireSocket()
        outputs = sock.list_outputs()
        if outputs:
            self.first_output = outputs[0]
            if "name" in self.first_output:
                self.first_output_name = self.first_output["name"]
        else:
            self.first_output_name = None
        self.config_data = self.load_config()
        self._cached_config = self.config_data
        self._start_watcher()

    def __del__(self):
        """Cancels the GIO file monitor when the object is destroyed."""
        if self.config_monitor:
            self.config_monitor.cancel()

    def _on_config_file_changed(
        self,
        monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Gio.File,
        event_type: Gio.FileMonitorEvent,
    ) -> None:
        """
        Callback for Gio.FileMonitor 'changed' signal.
        This method reloads the configuration, using a file modification time
        check to debounce rapid changes (like those from an editor's save).
        """
        if event_type in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.MOVED,
            Gio.FileMonitorEvent.CHANGED,
        ):
            try:
                current_mod_time = os.path.getmtime(self.config_file)
                if current_mod_time > self._last_mod_time:
                    self.reload_config()
                    self._reload_css()
                    self._last_mod_time = current_mod_time
                else:
                    self.logger.debug(
                        "Change event received but ignored due to debounce."
                    )
            except FileNotFoundError:
                self.logger.warning("Config file not found during GIO change check.")
            except Exception as e:
                self.logger.error(f"Error checking mod time in GIO callback: {e}")

    def _reload_css(self):
        if "css_generator" in self.panel_instance.plugins:
            self.panel_instance.plugins["css_generator"].generate_styles_css()

    def _strip_hints(self, data: Dict[str, Any]) -> Dict[str, Any]:
        stripped_data = {}
        for key, value in data.items():
            if key.endswith(("_hint", "_section_hint", "_items_hint")):
                continue
            if isinstance(value, dict):
                stripped_data[key] = self._strip_hints(value)
            elif isinstance(value, list) and all(
                isinstance(item, dict) for item in value
            ):
                stripped_list = [self._strip_hints(item) for item in value]
                stripped_data[key] = stripped_list
            else:
                stripped_data[key] = value
        return stripped_data

    @property
    def default_config_stripped(self) -> Dict[str, Any]:
        return self._strip_hints(self.default_config)

    def _recursive_merge(
        self,
        user_config: Dict[str, Any],
        default_config: Dict[str, Any],
    ) -> bool:
        """Recursively merges missing keys from default_config into user_config."""
        write_back_needed = False
        for key, default_value in default_config.items():
            if key not in user_config:
                user_config[key] = default_value
                write_back_needed = True
            elif isinstance(default_value, dict) and isinstance(
                user_config.get(key), dict
            ):
                if self._recursive_merge(user_config[key], default_value):
                    write_back_needed = True
        return write_back_needed

    def save_config(self):
        if not self._load_successful:
            self.logger.warning(
                "Skipping configuration save: Configuration is in an untrusted state (load failed). Please fix config.toml manually."
            )
            return
        try:
            with open(self.config_file, "w") as f:
                toml.dump(self.config_data, f)  # pyright: ignore
            self._last_mod_time = os.path.getmtime(self.config_file)
            self.logger.info("Configuration saved successfully.")
        except Exception as e:
            self.logger.error(
                error=e,
                message="Failed to save configuration to file.",
                level="error",
            )

    def reload_config(self):
        try:
            new_config = self.load_config(force_reload=True)
            self.config_data.update(new_config)  # pyright: ignore
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._cached_config and not force_reload:
            return self._cached_config
        config_from_file: Dict[str, Any] = {}
        file_path = Path(self.config_file)
        file_must_be_created = not file_path.exists()
        load_succeeded = False
        if file_must_be_created:
            self.logger.info("Config file is missing. Will apply defaults and create.")
            config_from_file = {}
            load_succeeded = True
        else:
            max_retries = 3
            retry_delay_seconds = 0.1
            for attempt in range(max_retries):
                try:
                    with open(file_path, "r") as f:
                        config_from_file = toml.load(f)
                    self.logger.debug("Existing config.toml loaded successfully.")
                    load_succeeded = True
                    self._last_mod_time = os.path.getmtime(self.config_file)
                    break
                except Exception as e:
                    self.logger.error(
                        f"Error loading config file on attempt {attempt + 1}: {e}. Retrying..."
                    )
                    time.sleep(retry_delay_seconds)
            else:
                self.logger.error(
                    "Failed to load config file after all retries. Using default configuration and skipping file save to preserve user data."
                )
                config_from_file = {}
        self._load_successful = load_succeeded
        default_config_for_merge = self.default_config_stripped
        self._recursive_merge(config_from_file, default_config_for_merge)
        needs_write_back = file_must_be_created
        if needs_write_back:
            self.logger.info(
                "Saving default configuration to file because it was missing."
            )
            original_config_data = getattr(self, "config_data", None)
            self.config_data = config_from_file
            self.save_config()
            self.config_data = original_config_data
        self._cached_config = config_from_file
        self.logger.debug("Configuration loaded and merged with defaults.")
        return config_from_file

    def _setup_config_paths(self) -> None:
        config_paths = self.setup_config_paths()
        self.home: str = config_paths.get("home", "")
        self.webapps_applications: str = os.path.join(
            self.home, ".local/share/applications"
        )
        self.config_path: str = config_paths.get("config_path", "")
        self.style_css_config: str = config_paths.get("style_css_config", "")
        self.cache_folder: str = config_paths.get("cache_folder", "")

    def setup_config_paths(self) -> Dict[str, str]:
        try:
            home = os.path.expanduser("~")
            xdg_config_home = os.getenv(
                "XDG_CONFIG_HOME", os.path.join(home, ".config")
            )
            config_path = os.path.join(xdg_config_home, "waypanel")
            style_css_config = os.path.join(config_path, "styles.css")
            xdg_cache_home = os.getenv("XDG_CACHE_HOME", os.path.join(home, ".cache"))
            cache_folder = os.path.join(xdg_cache_home, "waypanel")
            os.makedirs(config_path, exist_ok=True)
            os.makedirs(cache_folder, exist_ok=True)
            return {
                "home": home,
                "config_path": config_path,
                "style_css_config": style_css_config,
                "cache_folder": cache_folder,
            }
        except Exception as e:
            self.logger.error(
                f"Unexpected error while setting up configuration paths: {e}",
                exc_info=True,
            )
            return {}

    def initialize_config_section(self, section_name, default_config={}):
        if section_name not in self.config_data:
            section_defaults = self.default_config_stripped.get(section_name, {})
            self.config_data[section_name] = section_defaults  # pyright: ignore
            self.save_config()
            self.reload_config()

    def _start_watcher(self):
        try:
            self.config_monitor = self.gio_config_file.monitor_file(
                Gio.FileMonitorFlags.NONE, None
            )
            self.config_monitor.connect("changed", self._on_config_file_changed)
        except Exception as e:
            self.logger.error(f"Failed to start Gio.FileMonitor: {e}")

    def check_and_get_config(
        self, key_path: List[str], default_value: Any = None
    ) -> Any:
        current_data = self.config_data
        for i, key in enumerate(key_path):
            if isinstance(current_data, dict) and key in current_data:
                current_data = current_data[key]
            else:
                self.logger.warning(
                    f"Missing configuration key at path: {' -> '.join(key_path[: i + 1])}. Using default value: {default_value}"
                )
                return default_value
        return current_data

    def update_config(self, key_path: List[str], new_value: Any) -> bool:
        """
        Updates a configuration value by traversing nested keys, then safely saves and reloads the config.
        """
        if not key_path:
            self.logger.error("Configuration key path cannot be empty.")
            return False
        current_data = self.config_data
        for i, key in enumerate(key_path[:-1]):
            if (
                isinstance(current_data, dict)
                and key in current_data
                and isinstance(current_data[key], dict)
            ):
                current_data = current_data[key]
            else:
                self.logger.error(
                    f"Cannot update config: Missing or invalid path segment '{key}' at level {i}. Path: {' -> '.join(key_path)}"
                )
                return False
        final_key = key_path[-1]
        if isinstance(current_data, dict):
            if not self._load_successful:
                self.logger.warning(
                    f"Update to key {' -> '.join(key_path)} skipped: Config file failed to load. Please fix config.toml manually."
                )
                return False
            current_data[final_key] = new_value
            self.logger.info(
                f"Updated config key {' -> '.join(key_path)} to {new_value}."
            )
            self.save_config()
            self.reload_config()
            return True
        else:
            self.logger.error(
                f"Cannot set config key '{final_key}'. The parent element is not a dictionary."
            )
            return False
