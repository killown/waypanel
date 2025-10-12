import os
import toml
import time
from pathlib import Path
from typing import Any, List, Optional, Dict, Tuple, Union
from wayfire import WayfireSocket
from gi.repository import Gio  # pyright: ignore
from src.shared import config_template

_MISSING_SETTING_SENTINEL = object()


class ConfigHandler:
    """
    Manages the application's configuration file (config.toml) and provides
    a layered access interface.
    Handles file I/O, config merging with defaults, file change monitoring
    (via GIO), and dual injection of settings/hints.
    """

    def __init__(self, panel_instance: Any, plugin_id: Optional[str] = None):
        """
        Initializes the configuration handler, sets up paths, loads the initial
        configuration, and starts the file change monitor.
        Args:
            panel_instance: The main panel instance, used for logger and plugin access.
            plugin_id: The unique identifier for the calling plugin, used for
                         plugin-specific setting access.
        """
        self.logger = panel_instance.logger
        self.plugin_id = plugin_id
        self.panel_instance = panel_instance
        self._cached_config: Optional[Dict[str, Any]] = None
        self._last_mod_time: float = 0.0
        self.default_config = config_template.default_config
        self._setup_config_paths()
        self.config_file = Path(self.config_path) / "config.toml"
        self.gio_config_file = Gio.File.new_for_path(str(self.config_file))
        self.config_monitor: Optional[Gio.FileMonitor] = None
        self.config_path: str = self.config_file.parent.as_posix()
        self._load_successful: bool = False
        sock = WayfireSocket()
        outputs = sock.list_outputs()
        if outputs:
            self.first_output = outputs[0]
            self.first_output_name: Optional[str] = self.first_output.get("name")
        else:
            self.first_output_name = None
        self.config_data = self.load_config()
        self._cached_config = self.config_data
        self._start_watcher()

    def __del__(self) -> None:
        """Clean up the GIO file monitor when the handler is destroyed."""
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
        Callback triggered by the GIO file monitor when config.toml changes.
        Debounces changes using file modification time before triggering reload.
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

    def _reload_css(self) -> None:
        """Triggers a CSS regeneration if the CSS Generator plugin is loaded."""
        if "css_generator" in self.panel_instance.plugins:
            self.panel_instance.plugins["css_generator"].generate_styles_css()

    def _strip_hints(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively removes only keys ending with '_hint' from the
        configuration dictionary destined for TOML. Section hints are preserved.
        Args:
            data: The configuration dictionary, typically self.default_config.
        Returns:
            A dictionary containing only configuration values, no simple setting metadata.
        """
        stripped_data = {}
        for key, value in data.items():
            if key.endswith(("_hint",)):
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
        """Returns the default config without any standard setting metadata hints."""
        return self._strip_hints(self.default_config)

    def _recursive_merge(
        self,
        user_config: Dict[str, Any],
        default_config: Dict[str, Any],
    ) -> bool:
        """
        Recursively merges missing keys from `default_config` into `user_config`.
        Args:
            user_config: The dictionary loaded from the user's config file.
            default_config: The stripped default configuration.
        Returns:
            True if any key was added, indicating a write-back is needed.
        """
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

    def save_config(self) -> None:
        """Writes the current state of self.config_data to the TOML file."""
        if not self._load_successful:
            self.logger.warning(
                "Skipping configuration save: Configuration is in an untrusted state (load failed). Please fix config.toml manually."
            )
            return
        try:
            with open(self.config_file, "w") as f:
                toml.dump(self.config_data, f)
            self._last_mod_time = os.path.getmtime(self.config_file)
            self.logger.info("Configuration saved successfully.")
        except Exception as e:
            self.logger.error(
                error=e,
                message="Failed to save configuration to file.",
                level="error",
            )

    def reload_config(self) -> None:
        """Loads the configuration from the file, overwriting the current data."""
        try:
            new_config = self.load_config(force_reload=True)
            self.config_data.update(new_config)
            self.logger.info("Configuration reloaded from file.")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Loads the configuration from file, or uses defaults if missing/corrupt.
        Args:
            force_reload: If True, bypasses the internal cache.
        Returns:
            The loaded and merged configuration dictionary.
        """
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
        """Sets up and assigns the various system paths (XDG compliant)."""
        config_paths = self.setup_config_paths()
        self.home: str = config_paths.get("home", "")
        self.webapps_applications: str = os.path.join(
            self.home, ".local/share/applications"
        )
        self.config_path: str = config_paths.get("config_path", "")
        self.style_css_config: str = config_paths.get("style_css_config", "")
        self.cache_folder: str = config_paths.get("cache_folder", "")

    def setup_config_paths(self) -> Dict[str, str]:
        """
        Determines configuration paths based on XDG standards and creates
        necessary directories.
        """
        try:
            home = os.path.expanduser("~")
            xdg_config_home = os.getenv(
                "XDG_CONFIG_HOME", os.path.join(home, ".config")
            )
            config_path = os.path.join(xdg_config_home, "waypanel")
            style_css_config = os.path.join(config_path, "styles.css")
            xdg_cache_home = os.getenv("XDG_CACHE_HOME", os.path.join(home, ".cache"))
            cache_folder = os.path.join(xdg_cache_home, "waypanel")
            Path(config_path).mkdir(parents=True, exist_ok=True)
            Path(cache_folder).mkdir(parents=True, exist_ok=True)
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

    def initialize_config_section(
        self, section_name: str, default_config: Dict[str, Any] = {}
    ) -> None:
        """
        Ensures a top-level section exists in the live configuration.
        """
        if section_name not in self.config_data:
            section_defaults = self.default_config_stripped.get(section_name, {})
            self.config_data[section_name] = section_defaults
            self.save_config()
            self.reload_config()

    def _start_watcher(self) -> None:
        """Starts the GIO file monitor for real-time config updates."""
        try:
            self.config_monitor = self.gio_config_file.monitor_file(
                Gio.FileMonitorFlags.NONE, None
            )
            self.config_monitor.connect("changed", self._on_config_file_changed)
        except Exception as e:
            self.logger.error(f"Failed to start Gio.FileMonitor: {e}")

    def set_root_setting(
        self,
        key_path: List[str],
        new_value: Any,
    ) -> bool:
        """
        Sets a configuration value, saves to file, but **does not** set the hint.
        """
        if not key_path:
            self.logger.error("Configuration key path cannot be empty.")
            return False
        if not self._load_successful:
            self.logger.warning(
                f"Update to key {' -> '.join(key_path)} skipped: Config file failed to load. Please fix config.toml manually."
            )
            return False
        current_data = self.config_data
        for i, key in enumerate(key_path[:-1]):
            if not isinstance(current_data, dict):
                self.logger.error(
                    f"Configuration data corrupted: Expected dictionary at path {' -> '.join(key_path[:i])}, found {type(current_data)}."
                )
                return False
            if key not in current_data or not isinstance(current_data[key], dict):
                current_data[key] = {}
            current_data = current_data[key]
        final_key = key_path[-1]
        if not isinstance(current_data, dict):
            self.logger.error(
                f"Cannot set config key '{final_key}'. The parent element is not a dictionary. Path: {' -> '.join(key_path)}"
            )
            return False
        current_data[final_key] = new_value
        self.logger.info(
            f"Set and saved config key {' -> '.join(key_path)} to {new_value}."
        )
        self.save_config()
        self.reload_config()
        return True

    def get_root_setting(self, key_path: List[str], default_value: Any = None) -> Any:
        """
        Traverses the configuration dict (self.config_data) to retrieve a value.
        Args:
            key_path: List of strings representing the path (e.g., ['panel', 'top', 'height']).
            default_value: Value to return if the path is not found.
        Returns:
            The configuration value or the default value.
        """
        current_data = self.config_data
        for i, key in enumerate(key_path):
            if key.endswith(("_hint", "_section_hint", "_items_hint")):
                self.logger.debug(f"Ignoring hint key during lookup: {key}.")
                continue
            if isinstance(current_data, dict) and key in current_data:
                current_data = current_data[key]
            else:
                self.logger.debug(
                    f"Missing configuration key at path: {' -> '.join(key_path[: i + 1])}. Using default value: {default_value}"
                )
                return default_value
        return current_data

    def update_config(self, key_path: List[str], new_value: Any) -> bool:
        """
        Updates an *existing* setting without creating new sections.
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

    def remove_root_setting(self, key: Union[str, List[str]]) -> None:
        """Removes a key from the live configuration and saves the file."""
        if not key:
            self.logger.error("Cannot remove setting: key path cannot be empty.")
            return
        key_path = [key] if isinstance(key, str) else key
        current_level = self.config_data
        for i, part in enumerate(key_path[:-1]):
            if isinstance(current_level, dict) and part in current_level:
                current_level = current_level[part]
            else:
                self.logger.warning(
                    f"Attempted to remove non-existent config path: {key_path}"
                )
                return
        final_key = key_path[-1]
        if isinstance(current_level, dict) and final_key in current_level:
            del current_level[final_key]
            hint_key = f"{final_key}_hint"
            if hint_key in current_level:
                del current_level[hint_key]
            self.save_config()
            self.logger.info(
                f"Removed setting '{'.'.join(key_path)}' from configuration."
            )
        else:
            self.logger.warning(
                f"Attempted to remove non-existent config key: '{final_key}'"
            )

    def remove_plugin_setting(self) -> None:
        """Removes the entire configuration section for the current plugin."""
        if not self.plugin_id:
            self.logger.error("Plugin ID is not set, cannot remove settings.")
            return
        self.remove_root_setting(self.plugin_id)

    def set_section_hint(
        self,
        section_path: Union[str, List[str]],
        hint: Union[str, Tuple[str, ...]],
    ) -> bool:
        """
        Sets the section hint ('_section_hint') for a configuration path by writing to the
        authoritative source: self.default_config.
        Args:
            section_path: The path to the section (e.g., 'panel' or ['panel', 'theme']).
            hint: The hint string or tuple of strings to set as the metadata.
        Returns:
            True if the hint was successfully injected, False otherwise.
        """
        path_list = [section_path] if isinstance(section_path, str) else section_path
        hint_path = path_list + ["_section_hint"]
        return self._inject_to_dict(
            target_dict=self.default_config,
            key_path=hint_path,
            new_value=hint,
        )

    def _inject_to_dict(
        self, target_dict: Dict[str, Any], key_path: List[str], new_value: Any
    ) -> bool:
        """
        Generic, non-saving, iterative function to inject a value into a specific
        key path of an arbitrary dictionary, creating intermediate dictionaries
        if necessary.
        Args:
            target_dict: The dictionary to modify (e.g., self.config_data or self.default_config).
            key_path: List of keys representing the path (e.g., ['panel', 'top', 'height']).
            new_value: The value to set at the final key.
        Returns:
            True if the injection was successful, False otherwise.
        """
        if not key_path:
            return False
        current_data = target_dict
        for key in key_path[:-1]:
            if not isinstance(current_data, dict):
                return False
            if not isinstance(current_data.get(key), dict):
                current_data[key] = {}
            current_data = current_data[key]
        final_key = key_path[-1]
        if not isinstance(current_data, dict):
            return False
        current_data[final_key] = new_value
        return True

    def set_setting_hint(
        self,
        key_path,
        section,
        hint,
    ):
        """
        Sets the individual setting hint ('_hint') for a given configuration key
        by writing to the authoritative source: self.default_config.
        Args:
            key_path: The full path to the setting key (e.g., ['section', 'setting']).
            hint: The hint string or tuple of strings to set as the metadata.
        Returns:
            True if the hint was successfully injected, False otherwise.
        """
        if section:
            self.default_config[key_path][f"{section}_hint"] = hint
        else:
            if key_path not in self.default_config:
                self.default_config[key_path] = {}
            if "_section_hint" not in hint:
                section_hint = self.default_config[key_path]
                self.default_config[key_path] = {"_section_hint": section_hint}
            self.default_config[key_path]["_section_hint"] = hint

    def get_plugin_setting(
        self, key: Optional[Union[str, List[str]]] = None, default_value: Any = None
    ) -> Any:
        """
        Retrieves a configuration value for this specific plugin's section.
        If 'key' is not provided, the configuration for the entire plugin section
        (self.plugin_id) is returned.
        If default_value is provided and the setting is not found, the setting
        is added to the configuration.
        """
        _MISSING_SETTING_SENTINEL = object()
        if not self.plugin_id:
            return default_value
        key_path = [self.plugin_id]
        if key is not None:
            if isinstance(key, str):
                key_path.append(key)
            elif isinstance(key, list):
                key_path.extend(key)
        result = self.get_root_setting(key_path, _MISSING_SETTING_SENTINEL)
        if result is _MISSING_SETTING_SENTINEL:
            if default_value is not None:
                self.set_root_setting(key_path, default_value)
            return default_value
        return result

    def set_plugin_setting(
        self,
        key: Union[str, List[str]],
        value: Any,
    ) -> None:
        """
        Sets and saves a plugin-specific setting to self.config_data. **Does not**
        handle hint injection.
        """
        if not self.plugin_id:
            self.logger.error("Plugin ID is not set, cannot save setting.")
            return
        key_path: List[str] = [self.plugin_id]
        if isinstance(key, str):
            key_path.append(key)
        elif isinstance(key, list):
            key_path.extend(key)
        self.set_root_setting(key_path, value)

    def get_settings(self) -> Dict[str, Any]:
        """Returns the current live configuration dictionary (self.config_data)."""
        return self.config_data
