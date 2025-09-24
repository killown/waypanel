import os
import toml
import time
from pathlib import Path
from typing import Dict, Any, List
from wayfire import WayfireSocket

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class ConfigHandler:
    """
    Handles loading, saving, and managing the application's TOML configuration file.
    """

    def __init__(self, panel_instance):
        """
        Initializes the ConfigHandler.
        Args:
            panel_instance: The main application instance, used for logging.
        """
        self.logger = panel_instance.logger
        self._cached_config = None
        self._last_mod_time = 0.0

        self._setup_config_paths()
        self.config_file = Path(self.config_path) / "config.toml"
        self.config_path = self.config_file.parent  # pyright: ignore

        self.default_config = {
            "hardware": {
                "primary_output": {
                    "name": "DP-1",
                },
                "soundcard": {"blacklist": "Navi"},
            },
            "taskbar": {
                "panel": {
                    "name": "bottom-panel",
                    "exclusive_zone": True,
                    "width": 100,
                },
                "layout": {
                    "icon_size": 32,
                    "spacing": 5,
                    "show_label": True,
                    "max_title_lenght": 25,
                },
            },
            "dockbar": {
                "panel": {
                    "name": "left-panel",
                    "orientation": "v",
                    "class_style": "dockbar-buttons",
                },
                "app": {
                    "firefox-developer-edition": {
                        "cmd": "gtk-launch firefox-developer-edition.desktop",
                        "icon": "firefox-developer-edition",
                        "wclass": "firefox-developer-edition",
                        "desktop_file": "firefox-developer-edition.desktop",
                        "name": "Firefox Developer Edition",
                        "initial_title": "Firefox Developer Edition",
                    },
                    "chromium": {
                        "cmd": "gtk-launch chromium.desktop",
                        "icon": "chromium",
                        "wclass": "chromium",
                        "desktop_file": "chromium.desktop",
                        "name": "Chromium",
                        "initial_title": "Chromium",
                    },
                    "org.gnome.Nautilus": {
                        "cmd": "gtk-launch org.gnome.Nautilus.desktop",
                        "icon": "org.gnome.Nautilus",
                        "wclass": "org.gnome.Nautilus",
                        "desktop_file": "org.gnome.Nautilus.desktop",
                        "name": "Arquivos",
                        "initial_title": "Arquivos",
                    },
                    "steam": {
                        "cmd": "gtk-launch steam.desktop",
                        "icon": "steam",
                        "wclass": "steam",
                        "desktop_file": "steam.desktop",
                        "name": "Steam",
                        "initial_title": "Steam",
                    },
                    "cinny": {
                        "cmd": "gtk-launch cinny.desktop",
                        "icon": "cinny",
                        "wclass": "cinny",
                        "desktop_file": "cinny.desktop",
                        "name": "Cinny",
                        "initial_title": "Cinny",
                    },
                    "io.github.Hexchat": {
                        "cmd": "gtk-launch io.github.Hexchat.desktop",
                        "icon": "hexchat",
                        "wclass": "io.github.Hexchat",
                        "desktop_file": "io.github.Hexchat.desktop",
                        "name": "HexChat",
                        "initial_title": "HexChat",
                    },
                    "org.mozilla.Thunderbird": {
                        "cmd": "gtk-launch org.mozilla.Thunderbird.desktop",
                        "icon": "org.mozilla.Thunderbird",
                        "wclass": "org.mozilla.Thunderbird",
                        "desktop_file": "org.mozilla.Thunderbird.desktop",
                        "name": "Thunderbird",
                        "initial_title": "Thunderbird",
                    },
                },
            },
            "clipboard": {
                "server": {
                    "log_enabled": False,
                    "max_items": 100,
                    "monitor_interval": 0.5,
                },
                "client": {
                    "popover_min_width": 500,
                    "popover_max_height": 600,
                    "thumbnail_size": 128,
                    "preview_text_length": 50,
                    "image_row_height": 60,
                    "text_row_height": 38,
                    "item_spacing": 5,
                },
            },
            "notify": {
                "client": {
                    "max_notifications": 5.0,
                    "body_max_width_chars": 80.0,
                    "notification_icon_size": 64.0,
                    "popover_width": 500.0,
                    "popover_height": 600.0,
                },
                "server": {"show_messages": True},
            },
            "notes": {"notes_icon": "stock_notes", "notes_icon_delete": "edit-delete"},
            "panel": {
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
            },
            "menu": {
                "Wayfire": {
                    "icon": "dialog-scripts",
                    "items": [
                        {
                            "name": "Update and install wayfire",
                            "cmd": "sh $HOME/Scripts/wayfire/update-wayfire.sh",
                        },
                        {
                            "name": "Run wayfire benchmark",
                            "cmd": "sh $HOME/Scripts/wayfire/wayfire-headless-bench.sh",
                        },
                        {
                            "name": "Patch wayfire and install",
                            "cmd": 'kitty -e bash -c "cd $HOME/Git/wayfire/; $HOME/Scripts/wayfire/patch.apply; $HOME/Scripts/wayfire/install"',
                        },
                        {
                            "name": "Wayland Color Picker",
                            "cmd": "wl-color-picker",
                        },
                        {
                            "name": "Turn ON/OFF DP-2",
                            "cmd": "python $HOME/Scripts/wayfire/output_dp_2.py",
                        },
                    ],
                }
            },
            "folders": {
                "Imagens": {
                    "name": "Wallpapers",
                    "path": "/home/neo/Imagens/Wallpapers/",
                    "filemanager": "thunar",
                    "icon": "folder-symbolic",
                }
            },
        }

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

    def save_config(self):
        """
        Save the current configuration back to the config.toml file.
        """
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
        Loads and caches the panel configuration from the config.toml file,
        merging it with the default configuration.

        Args:
            force_reload (bool): If True, forces a reload from the file,
                                 ignoring the cached configuration.

        Returns:
            Dict[str, Any]: The loaded and merged configuration data.
        """
        # 1. Return cached config if available and not forced to reload.
        if self._cached_config and not force_reload:
            return self._cached_config

        config_from_file = {}
        file_path = Path(self.config_file)

        # 2. Check if the config file exists; if not, return default settings.
        if not file_path.exists():
            self.logger.info("Config file not found. Returning default config.")
            return self.default_config.copy()

        # 3. Attempt to load the config file with retries to handle temporary issues.
        max_retries = 3
        retry_delay_seconds = 0.1

        for attempt in range(max_retries):
            try:
                # Check for an empty file before trying to parse it.
                if file_path.stat().st_size == 0:
                    self.logger.info(
                        f"Config file is empty. Retrying... (Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay_seconds)
                    continue

                with open(file_path, "r") as f:
                    config_from_file = toml.load(f)
                self.logger.debug("Existing config.toml loaded successfully.")
                break  # Exit the loop on successful load.
            except Exception as e:
                self.logger.error(
                    f"Error loading config file on attempt {attempt + 1}: {e}"
                )
                time.sleep(retry_delay_seconds)

        # 4. Merge the loaded configuration with default values for any missing sections.
        # This ensures the config is always complete.
        for key, default_section in self.default_config.items():
            if key not in config_from_file:
                config_from_file[key] = default_section

        # 5. Cache the final configuration and return it.
        self._cached_config = config_from_file
        self.logger.debug("Configuration loaded and merged with defaults.")
        return config_from_file

    def _setup_config_paths(self) -> None:
        """
        Set up configuration paths based on the XDG Base Directory Specification.
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
        Set up and return configuration paths for the application,
        using XDG environment variables with a fallback to traditional paths.
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
        """Initializes a configuration section with default values if it doesn't exist."""
        if section_name not in self.config_data:
            section_defaults = default_config.get(section_name, {})
            self.config_data[section_name] = section_defaults
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
            self.logger.warning("Config file not found during change check.")
        except Exception as e:
            self.logger.error(f"Error checking for config changes: {e}")

    def _start_watcher(self):
        """Starts a watchdog observer to monitor the config.toml file for changes."""

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
        """
        Safely retrieves a value from the configuration data based on a nested key path.
        Returns the default_value if the path is not found.

        Args:
            key_path (List[str]): A list of strings representing the path to the desired key.
            default_value (Any): The value to return if the key is not found. Defaults to None.

        Returns:
            Any: The value found at the specified path, or the default_value if not found.
        """
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
