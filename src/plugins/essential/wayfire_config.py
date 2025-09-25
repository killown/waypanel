import os
import time
import toml
import asyncio
from gi.repository import GLib  # pyright: ignore
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop

DEPS = ["dockbar", "taskbar", "event_manager"]


def get_plugin_placement(panel_instance):
    """
    Returns the placement of the plugin.

    Args:
        panel_instance: The instance of the panel.

    Returns:
        str: The placement of the plugin, "background".
    """
    return "background"


def initialize_plugin(panel_instance):
    """
    Initializes the Wayfire Config Watcher plugin.

    Args:
        panel_instance: The instance of the panel.

    Returns:
        WayfireConfigWatcherPlugin or None: The initialized plugin instance if
        the required IPC method is available, otherwise None.
    """
    ENABLE_PLUGIN = hasattr(panel_instance.ipc.sock, "list_config_options")
    if ENABLE_PLUGIN:
        return WayfireConfigWatcherPlugin(panel_instance)
    else:
        panel_instance.logger.info(
            "plugin Wayfire_Config disabled, list_config_options method not found"
        )
        return None


class WayfireConfigWatcherPlugin(BasePlugin):
    """
    A plugin that watches the Wayfire configuration file and applies changes dynamically.
    """

    CONFIG_PATH = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
    PLUGIN_NAME = "wayfire_config"

    def __init__(self, panel_instance):
        """
        Initializes the WayfireConfigWatcherPlugin.

        Args:
            panel_instance: The instance of the panel.
        """
        super().__init__(panel_instance)
        self.panel = panel_instance
        self.config = None
        global_loop.create_task(self._initial_setup())
        self.observer = self.start_watching()

    async def _initial_setup(self):
        """
        Performs the initial setup by loading and applying the configuration.
        """
        self.config = await self.load_config_async()
        if self.config:
            await self.apply_config_async(self.config)
            self.logger.info("Initial config applied successfully.")
        else:
            self.logger.error("Error applying initial config.")

    async def load_config_async(self):
        """
        Loads the Wayfire configuration from the TOML file asynchronously.

        Returns:
            dict: The loaded configuration as a dictionary, or an empty dictionary if an error occurs.
        """
        try:
            return await asyncio.to_thread(self.load_config)
        except Exception as e:
            self.panel.logger.error(f"[{self.PLUGIN_NAME}] Failed to load config: {e}")
            return {}

    def load_config(self):
        """
        Loads the Wayfire configuration from the TOML file.

        Returns:
            dict: The loaded configuration as a dictionary, or an empty dictionary if an error occurs.
        """
        try:
            with open(self.CONFIG_PATH, "r") as f:
                return toml.load(f)
        except Exception as e:
            self.panel.logger.error(f"[{self.PLUGIN_NAME}] Failed to load config: {e}")
            return {}

    async def apply_config_async(self, config):
        """
        Applies the new configuration to Wayfire.

        Args:
            config (dict): The new configuration to apply.
        """
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
            """
            Flattens a nested TOML table into a dictionary with concatenated keys.
            """
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
            retry_count = 0
            max_retries = 3
            update_successful = False

            while retry_count < max_retries:
                try:
                    await asyncio.to_thread(self.ipc.set_option_values, batch_updates)
                    update_successful = True
                    break
                except Exception as e:
                    self.logger.warning(
                        f"Attempt {retry_count + 1} of {max_retries} to batch update failed: {e}. Retrying..."
                    )
                    retry_count += 1
                    await asyncio.sleep(0.5)

            if not update_successful:
                self.logger.warning(
                    f"Batch update failed after {max_retries} attempts, falling back to individual updates."
                )
                self.logger.warning(
                    "This update method is slower, try removing any invalid options from wayfire.toml"
                )
                await asyncio.to_thread(
                    self.notifier.notify_send,
                    "Wayfire Config Plugin",
                    f"Batch update failed, falling back to individual updates: {e}",
                    "config",
                )
                for key, value in batch_updates.items():
                    individual_retry_count = 0
                    individual_update_successful = False
                    while individual_retry_count < max_retries:
                        try:
                            await asyncio.to_thread(
                                self.ipc.set_option_values, {key: value}
                            )
                            self.logger.info(
                                f"Updated (individual) '{key}' → '{value}'"
                            )
                            individual_update_successful = True
                            break
                        except Exception as single_e:
                            self.logger.error(
                                f"Attempt {individual_retry_count + 1} of {max_retries} to set option '{key}' failed: {single_e}"
                            )
                            individual_retry_count += 1
                            await asyncio.sleep(0.5)

                    if not individual_update_successful:
                        self.logger.warning(
                            f"Failed to set option '{key}' after {max_retries} attempts. Skipping this option."
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
        """
        Applies the 'command' section of the configuration to Wayfire.

        Args:
            config (dict): The configuration dictionary.
        """
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
            retry_count = 0
            max_retries = 3
            update_successful = False
            while retry_count < max_retries:
                try:
                    await asyncio.to_thread(self.ipc.set_option_values, payload)
                    update_successful = True
                    break
                except Exception as e:
                    self.logger.warning(
                        f"Attempt {retry_count + 1} of {max_retries} to apply command bindings failed: {e}"
                    )
                    retry_count += 1
                    await asyncio.sleep(0.5)
            if update_successful:
                self.logger.info("Command bindings applied successfully.")
            else:
                self.logger.warning(
                    f"Failed to apply command bindings after {max_retries} attempts."
                )

        except Exception as e:
            self.logger.warning(f"Failed to apply command bindings: {e}")

    async def apply_window_rules_section_async(self, config):
        """
        Applies the 'window-rules' section of the configuration to Wayfire.

        Args:
            config (dict): The configuration dictionary.
        """
        window_rules_section = config.get("window-rules", {})
        rules = list(window_rules_section.values())

        if rules:
            payload = {"window-rules": {"rules": rules}}
            retry_count = 0
            max_retries = 3
            update_successful = False
            while retry_count < max_retries:
                try:
                    await asyncio.to_thread(self.ipc.set_option_values, payload)
                    update_successful = True
                    break
                except Exception as e:
                    self.logger.warning(
                        f"Attempt {retry_count + 1} of {max_retries} to apply window rules failed: {e}"
                    )
                    retry_count += 1
                    await asyncio.sleep(0.5)
            if update_successful:
                self.logger.info("Window rules applied successfully.")
            else:
                self.logger.warning(
                    f"Failed to apply window rules after {max_retries} attempts."
                )

    def start_watching(self):
        """
        Starts the file system observer to watch for changes in the configuration file.

        Returns:
            watchdog.observers.Observer: The started observer instance.
        """
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
    """
    A file system event handler that responds to changes in the Wayfire configuration file.
    """

    def __init__(self, plugin):
        """
        Initializes the ConfigFileHandler.

        Args:
            plugin: The WayfireConfigWatcherPlugin instance.
        """
        self.plugin = plugin
        self.watch_path = os.path.abspath(plugin.CONFIG_PATH)
        self.watch_dir = os.path.dirname(self.watch_path)
        self._last_reload = 0
        self._debounce_sec = 0.5
        self._pending_reload = False

    def on_modified(self, event):
        """
        Handles file modification events.
        """
        if event.src_path == self.watch_path:
            self.reload_config()

    def on_created(self, event):
        """
        Handles file creation events.
        """
        if event.src_path == self.watch_path:
            self.reload_config()

    def on_deleted(self, event):
        """
        Handles file deletion events.
        """
        if event.src_path == self.watch_path:
            self._restart_observer()

    def on_moved(self, event):
        """
        Handles file moved events.
        """
        if event.dest_path == self.watch_path:
            self.reload_config()

    def _restart_observer(self):
        """
        Restarts the file system observer.
        """
        self.plugin.observer.stop()
        self.plugin.observer.join()
        self.plugin.observer = self.plugin.start_watching()
        self.plugin.logger.info(f"[{self.plugin.PLUGIN_NAME}] Restarted observer")

    def reload_config(self):
        """
        Debounces and triggers an asynchronous reload of the configuration.
        """
        now = time.time()
        if now - self._last_reload < self._debounce_sec:
            return
        self._last_reload = now

        if self._pending_reload:
            return

        async def apply_coroutine():
            """
            Coroutine to load and apply the configuration.
            """
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
        """
        Watches wayfire.toml configuration file to automatically apply settings
        to the Wayfire compositor on the fly.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin watches a user-defined TOML file to apply Wayfire settings,
        keybinds, and window rules dynamically without requiring a manual reload.

        Its core logic is centered on **file monitoring and dynamic application**:

        1.  **File Watching**: It uses `watchdog` to monitor the `wayfire.toml`
            file for changes (modifications, creations, deletions, or moves).
        2.  **Debouncing**: A debounce mechanism is used to prevent rapid,
            redundant updates when the file is saved multiple times in quick
            succession.
        3.  **Asynchronous Reload**: When a valid, debounced change is detected,
            the plugin asynchronously loads the new TOML configuration.
        4.  **State Synchronization**: It fetches the current runtime configuration
            from Wayfire and compares it with the new file content. It then
            applies only the changed options, including special handling for
            `command` and `window-rules` sections.
        """
        return self.code_explanation.__doc__
