import os
import time
import toml
import asyncio
from gi.repository import GLib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop

DEPS = ["dockbar", "taskbar", "event_manager"]


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    ENABLE_PLUGIN = hasattr(panel_instance.ipc.sock, "list_config_options")
    if ENABLE_PLUGIN:
        return WayfireConfigWatcherPlugin(panel_instance)
    else:
        panel_instance.logger.info(
            "plugin Wayfire_Config disabled, list_config_options method not found"
        )
        return None


class WayfireConfigWatcherPlugin(BasePlugin):
    CONFIG_PATH = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
    PLUGIN_NAME = "wayfire_config"

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.panel = panel_instance
        self.config = None
        global_loop.create_task(self._initial_setup())
        self.observer = self.start_watching()

    async def _initial_setup(self):
        self.config = await self.load_config_async()
        if self.config:
            await self.apply_config_async(self.config)
            self.logger.info("Initial config applied successfully.")
        else:
            self.logger.error("Error applying initial config.")

    async def load_config_async(self):
        try:
            return await asyncio.to_thread(self.load_config)
        except Exception as e:
            self.panel.logger.error(f"[{self.PLUGIN_NAME}] Failed to load config: {e}")
            return {}

    def load_config(self):
        try:
            with open(self.CONFIG_PATH, "r") as f:
                return toml.load(f)
        except Exception as e:
            self.panel.logger.error(f"[{self.PLUGIN_NAME}] Failed to load config: {e}")
            return {}

    async def apply_config_async(self, config):
        try:
            response = await asyncio.to_thread(self.ipc.sock.list_config_options)
            if response.get("result") != "ok":
                self.logger.warning("Failed to fetch runtime config")
                return

            runtime = {
                section: {
                    name: option["value"]
                    for name, option in opts.items()
                    if option is not None
                    and isinstance(option, dict)
                    and "value" in option
                }
                for section, opts in response["options"].items()
                if opts is not None
            }

        except Exception as e:
            self.logger.error(f"Failed to get runtime config: {e}")
            return

        updates = {}

        def flatten(table, prefix=""):
            for key, value in table.items():
                if key in ("command", "window-rules"):
                    continue
                full_key = f"{prefix}{key}"
                if isinstance(value, dict):
                    flatten(value, prefix=f"{full_key}/")
                else:
                    if isinstance(value, bool):
                        value = "true" if value else "false"
                    elif isinstance(value, (int, float)):
                        value = str(value)
                    elif isinstance(value, list):
                        value = " ".join(str(v) for v in value)
                    else:
                        value = str(value)
                    updates[full_key] = value

        flatten(config)

        batch_updates = {}
        for key, toml_value in updates.items():
            parts = key.split("/")
            if len(parts) < 2:
                section = parts[0]
                option = None
            else:
                section, option = parts[0], parts[-1]

            section_options = runtime.get(section, {})
            if option is None:
                if isinstance(section_options, dict) and len(section_options) == 1:
                    current_value = next(iter(section_options.values()))
                else:
                    current_value = None
            else:
                current_value = section_options.get(option)

            if current_value != toml_value:
                batch_updates[key] = toml_value

        if batch_updates:
            try:
                await asyncio.to_thread(self.ipc.set_option_values, batch_updates)
                for key in batch_updates:
                    self.logger.info(f"Updated '{key}' → '{batch_updates[key]}'")
            except Exception as batch_e:
                self.logger.warning(
                    f"Batch update failed, falling back to individual updates: {batch_e}"
                )
                self.logger.warning(
                    "This update method is slower, try removing any invalid options from wayfire.toml"
                )
                await asyncio.to_thread(
                    self.utils.notify_send,
                    "Wayfire Config Plugin",
                    f"Batch update failed, falling back to individual updates: {batch_e}",
                )
                for key, value in batch_updates.items():
                    try:
                        await asyncio.to_thread(
                            self.ipc.set_option_values, {key: value}
                        )
                        self.logger.info(f"Updated (individual) '{key}' → '{value}'")
                    except Exception as single_e:
                        self.logger.error(
                            f"Failed to set option '{key}' even individually: {single_e}"
                        )
        try:
            await self.apply_command_section_async(config)
        except Exception as e:
            self.logger.warning(f"apply_command_section failed: {e}")

        try:
            await self.apply_window_rules_section_async(config)
        except Exception as e:
            self.logger.warning(f"apply_window_rules_section failed: {e}")

    async def apply_command_section_async(self, config):
        command_section = config.get("command", {})

        binding_tuples = []
        for name, entry in command_section.items():
            if isinstance(entry, list) and len(entry) >= 2:
                keybind = entry[0]
                command = entry[1]
                binding_tuples.append((command, keybind))

        payload = {"command": {"bindings": binding_tuples}}
        self.logger.info(f"Applying command bindings: {payload}")

        try:
            await asyncio.to_thread(self.ipc.set_option_values, payload)
        except Exception as e:
            self.logger.warning(f"Failed to apply command bindings: {e}")

    async def apply_window_rules_section_async(self, config):
        window_rules_section = config.get("window-rules", {})
        rules = list(window_rules_section.values())

        if rules:
            payload = {"window-rules": {"rules": rules}}
            try:
                await asyncio.to_thread(self.ipc.set_option_values, payload)
            except Exception as e:
                self.logger.warning(f"Failed to apply window rules: {e}")

    def start_watching(self):
        event_handler = ConfigFileHandler(self)
        observer = Observer()
        watch_dir = os.path.dirname(os.path.abspath(self.CONFIG_PATH))
        observer.schedule(event_handler, path=watch_dir, recursive=False)

        def start_observer():
            observer.start()
            return False

        GLib.idle_add(start_observer)
        self.logger.info(f"[{self.PLUGIN_NAME}] Watching config dir: {watch_dir}")
        return observer


class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, plugin):
        self.plugin = plugin
        self.watch_path = os.path.abspath(plugin.CONFIG_PATH)
        self.watch_dir = os.path.dirname(self.watch_path)
        self._last_reload = 0
        self._debounce_sec = 0.5
        self._pending_reload = False

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
        self.plugin.observer.stop()
        self.plugin.observer.join()
        self.plugin.observer = self.plugin.start_watching()
        self.plugin.logger.info(f"[{self.plugin.PLUGIN_NAME}] Restarted observer")

    def reload_config(self):
        now = time.time()
        if now - self._last_reload < self._debounce_sec:
            return
        self._last_reload = now

        if self._pending_reload:
            return

        async def apply_coroutine():
            self._pending_reload = True
            try:
                new_config = await self.plugin.load_config_async()
                if new_config:
                    await self.plugin.apply_config_async(new_config)
                    self.plugin.logger.info("Configuration reloaded and applied.")
            except Exception as e:
                self.plugin.panel.logger.error(
                    f"[{self.plugin.PLUGIN_NAME}] Failed to apply config: {e}"
                )
            finally:
                self._pending_reload = False

        self._pending_reload = True
        global_loop.create_task(apply_coroutine())

    def about(self):
        return self.about.__doc__
