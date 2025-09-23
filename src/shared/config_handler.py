import os
import toml
from pathlib import Path
from typing import Dict, Any
from wayfire import WayfireSocket

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class ConfigHandler:
    """
    Handles loading, saving, and managing the application's TOML configuration file.
    """

    def __init__(self, config_path, panel_instance, default_config=None):
        """
        Initializes the ConfigHandler.
        Args:
            config_path (str): The path to the directory containing the config file.
            default_config (Dict[str, Any]): The default configuration dictionary.
            logger: A logger instance for logging messages.
        """
        self.logger = panel_instance.logger
        self._cached_config = None
        self._last_mod_time = 0.0

        # Set up the paths first, which ensures the directories exist.
        self._setup_config_paths()
        # Now that the path is absolute and guaranteed to exist, set the config file path.
        self.config_file = Path(self.config_path) / "config.toml"
        self.config_path = (
            self.config_file.parent
        )  # Re-assign to be explicitly the directory

        if default_config is None:
            self.default_config = {}
        else:
            self.default_config = default_config

        sock = WayfireSocket()
        outputs = sock.list_outputs()

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

        self.config_data = self.load_config()

    def save_config(self):
        """
        Save the current configuration back to the config.toml file.
        """
        try:
            with open(self.config_file, "w") as f:
                toml.dump(self.config_data, f)
            # Update the last modification time after saving
            self._last_mod_time = os.path.getmtime(self.config_file)
            self.logger.info("Configuration saved successfully.")
        except Exception as e:
            self.logger.error(
                error=e,
                message="Failed to save configuration to file.",
                level="error",
            )

    def reload_config(self):
        """
        Reload the configuration from the config.toml file.
        """
        try:
            new_config = self.load_config(force_reload=True)
            self.config_data.update(new_config)
            self.logger.info("Configuration reloaded successfully.")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Load and cache the panel configuration from the config.toml file,
        merging with defaults if needed.
        """
        if self._cached_config and not force_reload:
            return self._cached_config

        config_from_file = {}
        try:
            # Check if the file exists and is not empty before trying to load it
            if (
                os.path.exists(self.config_file)
                and os.path.getsize(self.config_file) > 0
            ):
                with open(self.config_file, "r") as f:
                    config_from_file = toml.load(f)
                self.logger.debug("Existing config.toml loaded.")
            else:
                raise FileNotFoundError("Config file is empty or does not exist.")
        except FileNotFoundError:
            self.logger.info(
                "config.toml not found or empty. Creating with default settings."
            )
            os.makedirs(self.config_path, exist_ok=True)
            self.config_data = self.default_config
            self.save_config()
            self._cached_config = self.config_data
            return self._cached_config
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}. Using defaults.")
            self._cached_config = self.default_config
            return self._cached_config

        def deep_merge(a: dict, b: dict) -> dict:
            merged = a.copy()
            for key, value in b.items():
                if (
                    key in merged
                    and isinstance(merged[key], dict)
                    and isinstance(value, dict)
                ):
                    merged[key] = deep_merge(merged[key], value)
                else:
                    merged[key] = value
            return merged

        self.config_data = deep_merge(self.default_config, config_from_file)
        self._cached_config = self.config_data
        # Initialize or update the last modification time
        self._last_mod_time = os.path.getmtime(self.config_file)
        return self._cached_config

    def _setup_config_paths(self) -> None:
        """
        Set up configuration paths based on the user's home directory.
        This initializes instance variables used throughout the application.
        """
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
        Set up and return configuration paths for the application.
        """
        try:
            home = os.path.expanduser("~")
            config_path = os.path.join(home, ".config/waypanel")
            style_css_config = os.path.join(config_path, "styles.css")
            cache_folder = os.path.join(home, ".cache/waypanel")

            try:
                if not os.path.exists(config_path):
                    os.makedirs(config_path)
                    self.logger.info(f"Created config directory: {config_path}")

                if not os.path.exists(cache_folder):
                    os.makedirs(cache_folder)
                    self.logger.info(f"Created cache directory: {cache_folder}")
            except Exception as e:
                self.logger.error(
                    f"Failed to create required directories: {e}", exc_info=True
                )

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
        """Initializes a configuration section with default values if it doesn't exist."""
        if section_name not in self.config_data:
            # Get the defaults for the specific section
            section_defaults = default_config.get(section_name, {})
            # Directly set the section with its defaults
            self.config_data[section_name] = section_defaults
            # Save and reload to apply the changes
            self.save_config()
            self.reload_config()

    def check_for_changes_and_reload(self):
        """
        Checks if the config file has been modified and reloads it if necessary.
        """
        try:
            current_mod_time = os.path.getmtime(self.config_file)
            if current_mod_time > self._last_mod_time:
                self.reload_config()
                self._last_mod_time = current_mod_time
        except FileNotFoundError:
            # Handle cases where the file might be temporarily deleted or moved
            self.logger.warning("Config file not found during change check.")
        except Exception as e:
            self.logger.error(f"Error checking for config changes: {e}")

    def _start_watcher(self):
        """Starts a watchdog observer to monitor the config.toml file for changes."""

        # A nested class to handle events, allowing it to access the parent's methods
        class ConfigFileEventHandler(FileSystemEventHandler):
            def __init__(self, handler_instance):
                self.handler = handler_instance

            def on_modified(self, event):
                # Check if the event is a file modification and the path matches our config file
                if not event.is_directory and os.path.abspath(
                    event.src_path
                ) == os.path.abspath(self.handler.config_file):
                    self.handler.logger.info(
                        "Configuration file modified. Reloading..."
                    )
                    self.handler.reload_config()

        # The observer runs in a separate thread.
        self.config_observer = Observer()
        event_handler = ConfigFileEventHandler(self)

        # Schedule the observer to watch the directory containing the config file
        self.config_observer.schedule(
            event_handler, str(self.config_file.parent), recursive=False
        )
        self.config_observer.start()
        self.logger.info("Configuration file watcher started.")
