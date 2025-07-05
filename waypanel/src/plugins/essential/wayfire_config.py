import os
import toml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True
DEPS = []


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
        self.apply_config(self.config)
        self.observer = self.start_watching()

    def load_config(self):
        try:
            with open(self.CONFIG_PATH, "r") as f:
                return toml.load(f)
        except Exception as e:
            self.panel.logger.error(f"[{self.PLUGIN_NAME}] Failed to load config: {e}")
            return {}

    def apply_config(self, config):
        updates = {}

        def flatten(table, prefix=""):
            for key, value in table.items():
                full_key = f"{prefix}{key}"

                if isinstance(value, dict):
                    flatten(value, prefix=f"{full_key}/")
                else:
                    if isinstance(value, bool):
                        value = str(value).lower()
                    elif isinstance(value, (int, float)):
                        value = str(value)
                    elif isinstance(value, list):
                        value = " ".join(str(v) for v in value)

                    updates[full_key] = value

        flatten(config)

        self.ipc.set_option_values(updates)

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
        try:
            new_config = self.plugin.load_config()
            self.plugin.apply_config(new_config)
            print("wayfire.toml was reloaded")
        except Exception as e:
            self.plugin.panel.logger.error(
                f"[{self.plugin.PLUGIN_NAME}] error reloading config: {e}"
            )
