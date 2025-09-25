import os
import toml
import time
from pathlib import Path
from typing import Dict, Any, List
from wayfire import WayfireSocket
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.shared import config_template


class ConfigHandler:
    def __init__(self, panel_instance):
        self.logger = panel_instance.logger
        self._cached_config = None
        self._last_mod_time = 0.0
        self.default_config = config_template.default_config
        self._setup_config_paths()
        self.config_file = Path(self.config_path) / "config.toml"
        self.config_path = self.config_file.parent  # pyright: ignore
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

    def _strip_hints(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return data
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

    def save_config(self):
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

    def reload_config(self):
        try:
            new_config = self.load_config(force_reload=True)
            self.config_data.update(new_config)
            self.logger.info("Configuration reloaded successfully.")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._cached_config and not force_reload:
            return self._cached_config
        config_from_file = {}
        file_path = Path(self.config_file)
        if not file_path.exists():
            self.logger.info("Config file not found. Returning default config.")
            return self.default_config_stripped.copy()
        max_retries = 3
        retry_delay_seconds = 0.1
        for attempt in range(max_retries):
            try:
                if file_path.stat().st_size == 0:
                    self.logger.info(
                        f"Config file is empty. Retrying... (Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay_seconds)
                    continue
                with open(file_path, "r") as f:
                    config_from_file = toml.load(f)
                self.logger.debug("Existing config.toml loaded successfully.")
                break
            except Exception as e:
                self.logger.error(
                    f"Error loading config file on attempt {attempt + 1}: {e}"
                )
                time.sleep(retry_delay_seconds)
        default_config_for_merge = self.default_config_stripped
        for key, default_section in default_config_for_merge.items():
            if key not in config_from_file:
                config_from_file[key] = default_section
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
            self.config_data[section_name] = section_defaults
            self.save_config()
            self.reload_config()

    def check_for_changes_and_reload(self):
        try:
            current_mod_time = os.path.getmtime(self.config_file)
            if current_mod_time > self._last_mod_time:
                self.reload_config()
                self._last_mod_time = current_mod_time
        except FileNotFoundError:
            self.logger.warning("Config file not found during change check.")
        except Exception as e:
            self.logger.error(f"Error checking for config changes: {e}")

    def _start_watcher(self):
        class ConfigFileEventHandler(FileSystemEventHandler):
            def __init__(self, handler_instance):
                self.handler = handler_instance

            def on_modified(self, event):
                if not event.is_directory and os.path.abspath(
                    event.src_path
                ) == os.path.abspath(self.handler.config_file):
                    self.handler.logger.info(
                        "Configuration file modified. Reloading..."
                    )
                    self.handler.reload_config()

        self.config_observer = Observer()
        event_handler = ConfigFileEventHandler(self)
        self.config_observer.schedule(
            event_handler, str(self.config_file.parent), recursive=False
        )
        self.config_observer.start()
        self.logger.info("Configuration file watcher started.")

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
