import os
import toml
from gi.repository import GLib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True
DEPS = ["dockbar", "taskbar", "top_panel", "left_panel", "bottom_panel"]


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return WayfireConfigWatcherPlugin(panel_instance)


class WayfireConfigWatcherPlugin(BasePlugin):
    CONFIG_PATH = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
    PLUGIN_NAME = "wayfire_config"

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.panel = panel_instance
        self.config = self.load_config()
        GLib.idle_add(self._apply_config_idle)
        self.observer = self.start_watching()

    def _apply_config_idle(self):
        """Apply config in a non-blocking way via GLib idle loop."""
        try:
            self.apply_config(self.config)
            self.logger.info("Initial config applied successfully.")
        except Exception as e:
            self.logger.error(f"Error applying initial config: {e}")
        return False  # Run only once

    def load_config(self):
        try:
            with open(self.CONFIG_PATH, "r") as f:
                return toml.load(f)
        except Exception as e:
            self.panel.logger.error(f"[{self.PLUGIN_NAME}] Failed to load config: {e}")
            return {}

    def safe_set_option_values(self, options):
        """
        Apply config options one by one, skipping any that fail.

        Args:
            options (dict): Dictionary of config options to apply.

        Returns:
            dict: A subset of `options` that were successfully applied.
        """
        successful = {}

        for key, value in options.items():
            try:
                self.ipc.set_option_values({key: value})
                successful[key] = value
            except Exception as e:
                self.logger.warning(f"Skipping invalid config option: {key}")
                continue

        return successful

    def apply_config(self, config):
        updates = {}

        def apply(table, prefix=""):
            for key, value in table.items():
                if key in ("window-rules", "command"):
                    continue

                full_key = f"{prefix}{key}"

                if isinstance(value, dict):
                    apply(value, prefix=f"{full_key}/")
                else:
                    if isinstance(value, bool):
                        value = str(value).lower()
                    elif isinstance(value, (int, float)):
                        value = str(value)
                    elif isinstance(value, list):
                        value = " ".join(str(v) for v in value)
                    updates[full_key] = value

        apply(config)

        # Only apply if value differs from current
        for key, new_value in updates.items():
            try:
                current_value = self.ipc.get_option_value(key)
                if current_value != new_value:
                    self.safe_set_option_values({key: new_value})
                    self.logger.info(
                        f"Updated '{key}' from '{current_value}' to '{new_value}'"
                    )
                else:
                    self.logger.debug(f"Skipped '{key}' - value unchanged.")
            except Exception as e:
                self.logger.warning(f"Failed to apply '{key}': {e}")

        self.apply_command_section(config)
        self.apply_window_rules_section(config)

    def apply_command_section(self, config):
        command_section = config.get("command", {})

        # Format for set_option_values
        binding_tuples = []

        for name, entry in command_section.items():
            if isinstance(entry, list) and len(entry) >= 2:
                keybind = entry[0]
                command = entry[1]
                binding_tuples.append((command, keybind))

        payload = {"command": {"bindings": binding_tuples}}

        self.logger.info(f"Applying command bindings: {payload}")
        self.safe_set_option_values(payload)

    def apply_window_rules_section(self, config):
        window_rules_section = config.get("window-rules", {})

        rules = []
        for value in window_rules_section.values():
            rules.append(value)

        if rules:
            self.safe_set_option_values({"window-rules": {"rules": rules}})

    def start_watching(self):
        event_handler = ConfigFileHandler(self)
        observer = Observer()
        watch_dir = os.path.dirname(os.path.abspath(self.CONFIG_PATH))
        observer.schedule(event_handler, path=watch_dir, recursive=False)
        observer.start()
        self.logger.info(f"[{self.PLUGIN_NAME}] Watching config dir: {watch_dir}")
        return observer


class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, plugin):
        self.plugin = plugin
        self.watch_path = os.path.abspath(plugin.CONFIG_PATH)
        self.watch_dir = os.path.dirname(self.watch_path)

    def on_modified(self, event):
        if event.src_path == self.watch_path:
            self.reload_config()

    def on_created(self, event):
        if event.src_path == self.watch_path:
            self.reload_config()

    def on_deleted(self, event):
        if event.src_path == self.watch_path:
            self._restart_observer()

    def on_moved(self, event):
        if event.dest_path == self.watch_path:
            self.reload_config()

    def _restart_observer(self):
        """Restart observer when the file is deleted."""
        self.plugin.observer.stop()
        self.plugin.observer.join()
        self.plugin.observer = self.plugin.start_watching()
        self.plugin.logger.info(f"[{self.plugin.PLUGIN_NAME}] Restarted observer")

    def reload_config(self):
        """Schedule config reload in the main thread, once, without blocking."""
        # Avoid duplicate pending reloads
        if getattr(self, "_pending_reload", False):
            return

        try:
            new_config = self.plugin.load_config()

            def apply_in_main_thread():
                self._pending_reload = False
                try:
                    self.plugin.apply_config(new_config)
                    self.plugin.logger.info("Configuration reloaded and applied.")
                except Exception as e:
                    self.plugin.panel.logger.error(
                        f"[{self.plugin.PLUGIN_NAME}] Failed to apply config: {e}"
                    )
                return False  # Run only once

            self._pending_reload = True
            GLib.idle_add(apply_in_main_thread)
            print("Scheduled non-blocking config reload...")

        except Exception as e:
            self.plugin.panel.logger.error(
                f"[{self.plugin.PLUGIN_NAME}] Failed to load config: {e}"
            )
            self._pending_reload = False
