import os
import gc
import sys
import inspect
import lazy_loader as lazy
import gi
from gi.repository import Gtk, GLib, Gdk, Gio, Pango, GdkPixbuf, Adw  # pyright: ignore
import pathlib
from src.core import create_panel
from src.shared.path_handler import PathHandler
from src.shared.notify_send import Notifier
from src.shared.wayfire_helpers import WayfireHelpers
from src.shared.gtk_helpers import GtkHelpers
from src.shared.data_helpers import DataHelpers
from src.shared.config_handler import ConfigHandler
from src.shared.command_runner import CommandRunner
from src.shared.concurrency_helper import ConcurrencyHelper
from typing import Any, List, ClassVar, Optional, Union, Dict, Set, Callable, Tuple
import asyncio

TIME_MODULE = lazy.load("time")
DATETIME_MODULE = lazy.load("datetime")
ASYNCI_MODULE = lazy.load("asyncio")
SUBPROCESS_MODULE = lazy.load("subprocess")
SQLITE3_MODULE = lazy.load("sqlite3")
IMPORTLIB_MODULE = lazy.load("importlib")
CONCURRENCY_FUTURES_MODULE = lazy.load("concurrent.futures")
ORJSON_MODULE = lazy.load("orjson")
REQUESTS_MODULE = lazy.load("requests")
AIOSQLITE_MODULE = lazy.load("aiosqlite")
TOML_MODULE = lazy.load("toml")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")


class PluginLogAdapter:
    """
    A wrapper around the structlog logger that automatically injects the caller's
    file, package, function name, AND line number into the log event's 'extra' dictionary.
    """

    def __init__(self, logger):
        self._logger = logger
        try:
            self._base_plugin_filename = os.path.basename(inspect.getfile(BasePlugin))
        except (TypeError, ImportError):
            self._base_plugin_filename = os.path.basename(__file__)

    def _get_caller_context(self):
        frame = inspect.currentframe()
        if not frame:
            return {}
        f = frame.f_back
        while f:
            caller_file = os.path.basename(f.f_code.co_filename)
            if caller_file != self._base_plugin_filename:
                try:
                    caller_package = f.f_globals.get("__package__", "unknown")
                    caller_func = f.f_code.co_name
                    caller_line = f.f_lineno
                    del f
                    del frame
                    return {
                        "file": caller_file,
                        "package": caller_package,
                        "func": caller_func,
                        "line": caller_line,
                    }
                except Exception:
                    break
            f = f.f_back
        del frame
        return {}

    def _log_with_context(self, level: str, message: str, **kwargs):
        context = self._get_caller_context()
        if context:
            if "extra" in kwargs and isinstance(kwargs["extra"], dict):
                kwargs["extra"].update(context)
            else:
                kwargs["extra"] = context
        log_method = getattr(self._logger, level)
        log_method(message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log_with_context("info", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log_with_context("warning", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log_with_context("error", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._log_with_context("debug", message, **kwargs)

    def exception(self, message: str, **kwargs):
        self._log_with_context("exception", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log_with_context("critical", message, **kwargs)

    def __getattr__(self, name):
        return getattr(self._logger, name)


class BasePlugin:
    """
    Base class for all waypanel plugins, now including integrated
    asynchronous and threading utilities with automatic cleanup.
    """

    DEPS: ClassVar[List[str]] = []
    _panel_instance: Any
    _plugin_loader: Any
    _ipc: Any
    _ipc_server: Any
    _logger_adapter: PluginLogAdapter
    _path_handler: PathHandler
    _notifier: Notifier
    _wf_helper: WayfireHelpers
    _gtk_helper: GtkHelpers
    _data_helper: DataHelpers
    _config_handler: ConfigHandler
    _cmd: CommandRunner
    global_loop: asyncio.AbstractEventLoop
    global_executor: Any
    _running_futures: Set[Any]
    _running_tasks: Set[asyncio.Task]
    ConfigKeys = list[str]
    PluginName = str

    def __init__(self, panel_instance: Any):
        """
        Initializes the BasePlugin and injects core resources, including the
        global ThreadPoolExecutor and asyncio event loop.
        """
        self._panel_instance = panel_instance
        self._plugin_loader = panel_instance.plugin_loader
        self._ipc = panel_instance.ipc
        self._ipc_server = panel_instance.ipc_server
        self._logger_adapter = PluginLogAdapter(panel_instance.logger)
        self._path_handler = PathHandler(panel_instance)
        self._notifier = Notifier()
        self._wf_helper = WayfireHelpers(panel_instance)
        self._gtk_helper = GtkHelpers(panel_instance)
        self._data_helper = DataHelpers()
        self._cmd = CommandRunner(panel_instance)
        self._concurrency_helper = ConcurrencyHelper(panel_instance)
        self.global_loop = self._concurrency_helper.global_loop
        self.global_executor = self._concurrency_helper.global_executor
        self.main_widget: Optional[Union[tuple, list]] = None
        self.plugin_file = None
        self.ipc_client = None
        self.dependencies: List[str] = list(getattr(self, "DEPS", []))
        self._layer_shell: Any = create_panel.LayerShell
        self._set_layer_pos_exclusive: Any = create_panel.set_layer_position_exclusive
        self._unset_layer_pos_exclusive: Any = (
            create_panel.unset_layer_position_exclusive
        )
        self.gtk = Gtk
        self.gdk = Gdk
        self.gdkpixbuf = GdkPixbuf
        self.adw = Adw
        self.glib = GLib
        self.gio = Gio
        self.pango = Pango
        self.pathlib = pathlib
        self._loaded_modules: Dict[str, Any] = {}
        metadata = self.get_plugin_metadata()
        self.plugin_id = None
        if metadata is not None:
            if "id" in metadata:
                self.plugin_id = metadata["id"]
        GLib.timeout_add_seconds(60, self.run_gc_cleanup)
        self._config_handler = ConfigHandler(panel_instance, self.plugin_id)

    def get_plugin_metadata(self):
        module_name = self.__module__
        try:
            module_object = sys.modules[module_name]
        except KeyError:
            return None
        if hasattr(module_object, "get_plugin_metadata"):
            metadata = module_object.get_plugin_metadata(self._panel_instance)
            return metadata

    def set_hint(self, hint: str = "", section: list = [], plugin_id: str = ""):
        return self.config_handler.set_setting_hint(plugin_id, section, hint)

    def add_hint(self, hint, section=None):
        metadata = self.get_plugin_metadata()
        if metadata:
            plugin_id = metadata["id"]
            if plugin_id:
                if "description" in metadata:
                    self.config_handler.set_section_hint(
                        plugin_id, metadata["description"]
                    )
                return self.config_handler.set_setting_hint(plugin_id, section, hint)

    def _periodic_gc(self):
        """
        Manually forces Python's garbage collector (GC) to run.
        Crucial for GObject/GTK applications, this reclaims memory
        stuck in uncollectable reference cycles that frequently form
        between Python objects and the C-level library bindings.
        Returns:
            bool: True, signaling GLib to repeat the timer.
        """
        gc.collect()
        return True

    def run_gc_cleanup(self):
        """
        Initializes the entire memory cleanup lifecycle.
        1. Runs `_periodic_gc` immediately to clear memory leaks
           accumulated during startup initialization.
        2. Sets up the long-running timer (5 minutes) for continuous
           memory maintenance throughout the application's lifespan.
        Returns:
            bool: False, to ensure this setup function runs only once.
        """
        self._periodic_gc()
        GLib.timeout_add_seconds(300, self._periodic_gc)
        return False

    def set_keyboard_on_demand(self, mode=True):
        """Set the keyboard mode to ON_DEMAND."""
        if mode is True:
            self._layer_shell.set_keyboard_mode(
                self._panel_instance.top_panel, self._layer_shell.KeyboardMode.ON_DEMAND
            )
        if mode is False:
            self._layer_shell.set_keyboard_mode(
                self.obj.top_panel, self._layer_shell.KeyboardMode.NONE
            )
            self.obj.top_panel.grab_focus()
            toplevel = self.obj.top_panel.get_root()
            if isinstance(toplevel, self.gtk.Window):
                toplevel.set_focus(None)

    def lazy_load_module(self, module_name: str) -> Optional[Any]:
        """
        Lazily and dynamically imports a module by name.
        It caches the imported module in the instance to prevent re-importing
        on subsequent calls, which is faster and avoids potential side effects.
        Args:
            module_name (str): The full path of the module to import (e.g., 'gi.repository.Notify').
        Returns:
            Optional[Any]: The imported module object if successful, None otherwise.
        """
        if module_name in self._loaded_modules:
            self.logger.debug(f"Module '{module_name}' retrieved from cache.")
            return self._loaded_modules[module_name]
        try:
            module = IMPORTLIB_MODULE.import_module(module_name)  # pyright: ignore
            self._loaded_modules[module_name] = module
            self.logger.debug(
                f"Module '{module_name}' imported and cached successfully."
            )
            return module
        except ImportError as e:
            self.logger.error(
                f"Failed to lazy-load module '{module_name}'. Check if it is installed. Error: {e}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred while loading module '{module_name}': {e}"
            )
            return None

    def update_config(self, key_path: List[str], new_value: Any):
        """
        Updates a configuration value by path, saves the config file, and reloads the configuration.
        This method delegates the operation to the main ConfigHandler.
        Args:
            key_path: A list of strings representing the path to the config value
                      (e.g., ["section", "subsection", "key"]).
            new_value: The new value to set.
        Returns:
            True if the configuration was successfully updated and saved, False otherwise.
        """
        try:
            return self.run_in_thread(
                self.config_handler.update_config, key_path, new_value
            )
        except AttributeError as e:
            self.logger.error(f"Failed to call update_config on config_handler: {e}")
            return False

    def run_cmd(self, cmd: str) -> Any:
        return self.run_in_thread(self.cmd.run, cmd)

    def _cleanup_future(self, future: Any):
        """Internal callback to remove a Future from the tracking set once it's done."""
        try:
            if future in self._running_futures:
                self._running_futures.remove(future)
        except Exception as e:
            self.logger.error(f"Error cleaning up Future tracking: {e}")

    @property
    def set_section_hint(
        self,
    ) -> Callable[[Union[str, List[str]], str | Tuple[str, ...]], bool]:
        """
        Provides direct access to the underlying ConfigHandler's set_section_hint method.

        This property allows a plugin to set the documentation hint for its
        configuration section using an idiomatic plugin API:
        'self.set_section_hint(path, hint_text)'.

        Returns:
            Callable: The bound set_section_hint method of the ConfigHandler.
        """
        return self.config_handler.set_section_hint

    @property
    def set_plugin_setting(self) -> Callable[[ConfigKeys, Any], None]:
        """
        Provides access to the ConfigHandler's method for setting a plugin-specific value.

        The returned callable has the signature:
        (list[str], new_value: Any) -> None

        This method updates the configuration in memory and persists the change to disk.

        Returns
        -------
        Callable
            The underlying `ConfigHandler.set_plugin_setting` method.
        """
        return self.config_handler.set_plugin_setting  # pyright: ignore

    @property
    def get_plugin_setting(self) -> Callable[[ConfigKeys, Any]]:
        """Provides access to the ConfigHandler's method for retrieving a value.

        This property returns the underlying `ConfigHandler.get_plugin_setting`
        method, which can be used to query the configuration system directly.

        Returns
        -------
        Callable[[list[str], Any | None], Any]
        """
        return self.config_handler.get_plugin_setting

    @property
    def get_root_setting(self) -> Callable[[List[str], Any]]:
        """
        Provides access to the ConfigHandler's method for retrieving a root-level (global) value.

        The returned callable has the signature:
        (keys: list[str], default: Any) -> Any

        Used for core application settings, supporting deep key traversal and
        safe fallback using a default value.

        Returns
        -------
        Callable
            The underlying `ConfigHandler.get_root_setting` method.
        """
        return self.config_handler.get_root_setting

    @property
    def remove_plugin_setting(self):
        """
        Provides access to the ConfigHandler's method for removing a plugin-specific setting.

        The returned callable has the signature:
        (keys: list[str]) -> None

        This method handles the atomic deletion of the key from the in-memory
        configuration and persists the change to the configuration file.

        Returns
        -------
        Callable
            The underlying `ConfigHandler.remove_plugin_setting` method.
        """
        return self.config_handler.remove_plugin_setting  # pyright: ignore

    @property
    def run_in_async_task(self):
        """Read-only access to the imported self._concurrency_helper.run_in_async_task."""
        return self._concurrency_helper.run_in_async_task

    @property
    def run_in_thread(self):
        """Read-only access to the imported self._concurrency_helper.run_in_thread."""
        return self._concurrency_helper.run_in_thread

    @property
    def schedule_in_gtk_thread(self):
        """Read-only access to the imported self._concurrency_helper.schedule_in_gtk_thread."""
        return self._concurrency_helper.schedule_in_gtk_thread

    @property
    def os(self) -> Any:
        """Read-only access to the imported 'os' standard library module."""
        return os

    @property
    def json(self) -> Any:
        """Read-only access to the imported 'orjson' standard library module."""
        return ORJSON_MODULE

    @property
    def time(self) -> Any:
        """Read-only access to the time module."""
        return TIME_MODULE

    @property
    def asyncio(self) -> Any:
        """Read-only access to the asyncio module."""
        return ASYNCI_MODULE

    @property
    def subprocess(self) -> Any:
        """Read-only access to the subprocess module."""
        return SUBPROCESS_MODULE

    @property
    def requests(self) -> Any:
        """Read-only access to the requests module."""
        return REQUESTS_MODULE

    @property
    def datetime(self) -> Any:
        """Read-only access to the datetime module."""
        return DATETIME_MODULE

    @property
    def thread_pool_executor(self) -> Any:
        """Read-only access to the ThreadPoolExecutor class."""
        return CONCURRENCY_FUTURES_MODULE.ThreadPoolExecutor  # pyright: ignore

    @property
    def future(self) -> Any:
        """Read-only access to the Future class."""
        return CONCURRENCY_FUTURES_MODULE.Future  # pyright: ignore

    @property
    def sqlite3(self) -> Any:
        """Read-only access to the sqlite3 module."""
        return SQLITE3_MODULE

    @property
    def aiosqlite(self) -> Any:
        """Read-only access to the aiosqlite module."""
        return AIOSQLITE_MODULE

    @property
    def toml(self) -> Any:
        """Read-only access to the toml module."""
        return TOML_MODULE

    @property
    def obj(self) -> Any:
        """Reference to the main Panel instance."""
        return self._panel_instance

    @property
    def logger(self) -> PluginLogAdapter:
        """Logger object for logging messages (now read-only)."""
        return self._logger_adapter

    @property
    def ipc(self) -> Any:
        """IPC client for Wayfire communication."""
        return self._ipc

    @property
    def ipc_server(self) -> Any:
        """Reference to the main IPC Server."""
        return self._ipc_server

    @property
    def compositor(self) -> Any:
        """Reference to the compositor interface via the IPC server."""
        return self.ipc_server.compositor

    @property
    def plugins(self) -> dict:
        """Dictionary of all loaded plugins."""
        return self._plugin_loader.plugins

    @property
    def plugin_loader(self) -> Any:
        """Reference to the plugin loader."""
        return self._plugin_loader

    @property
    def default_config(self) -> Dict:
        """
        Provides the LIVE, authoritative copy of the default configuration
        (metadata source) from the ConfigHandler.
        This ensures ControlCenterHelpers always sees hints dynamically
        injected by other plugins (e.g., get_plugin_setting).
        """
        return self.config_handler.default_config

    @property
    def config_data(self):
        """All configuration data from config.toml."""
        return self._config_handler.config_data  # pyright: ignore

    @property
    def bottom_panel(self) -> Any:
        return self.obj.bottom_panel

    @property
    def top_panel(self) -> Any:
        return self.obj.top_panel

    @property
    def left_panel(self) -> Any:
        return self.obj.left_panel

    @property
    def right_panel(self) -> Any:
        return self.obj.right_panel

    @property
    def path_handler(self) -> PathHandler:
        """Read-only access to the PathHandler instance."""
        return self._path_handler

    @property
    def notifier(self) -> Notifier:
        """Read-only access to the Notifier instance."""
        return self._notifier

    @property
    def wf_helper(self) -> WayfireHelpers:
        """Read-only access to the WayfireHelpers instance."""
        return self._wf_helper

    @property
    def gtk_helper(self) -> GtkHelpers:
        """Read-only access to the GtkHelpers instance."""
        return self._gtk_helper

    @property
    def data_helper(self) -> DataHelpers:
        """Read-only access to the DataHelpers instance."""
        return self._data_helper

    @property
    def config_handler(self) -> ConfigHandler:
        """Read-only access to the ConfigHandler instance."""
        return self._config_handler

    @property
    def cmd(self) -> CommandRunner:
        """Read-only access to the CommandRunner instance."""
        return self._cmd

    @property
    def layer_shell(self) -> Any:
        """Read-only reference to create_panel.LayerShell."""
        return self._layer_shell

    @property
    def icon_exist(self) -> Any:
        """Read-only access to the GtkHelpers instance."""
        return self._gtk_helper.icon_exist

    @property
    def create_dashboard_popover(self):
        """Read-only access to the self._gtk_helper.create_dashboard_popover"""
        return self._gtk_helper.create_dashboard_popover

    @property
    def set_layer_pos_exclusive(self) -> Any:
        """Read-only reference to create_panel.set_layer_position_exclusive."""
        return self._set_layer_pos_exclusive

    @property
    def unset_layer_pos_exclusive(self) -> Any:
        """Read-only reference to create_panel.unset_layer_position_exclusive."""
        return self._unset_layer_pos_exclusive

    @property
    def get_data_path(self):
        """Read-only alias for self._path_handler.get_data_path."""
        return self._path_handler.get_data_path

    @property
    def get_cache_path(self):
        """Read-only alias for self._path_handler.get_cache_path."""
        return self._path_handler.get_cache_path

    @property
    def notify_send(self):
        """Read-only alias for self._notifier.notify_send."""
        return self._notifier.notify_send

    @property
    def get_icon(self):
        """Read-only alias for self._gtk_helper.get_icon."""
        return self._gtk_helper.get_icon

    @property
    def add_cursor_effect(self):
        """Read-only alias for self._gtk_helper.add_cursor_effect."""
        return self._gtk_helper.add_cursor_effect

    @property
    def remove_widget(self):
        """Read-only alias for self._gtk_helper.remove_widget."""
        return self._gtk_helper.remove_widget

    @property
    def safe_remove_css_class(self):
        """Read-only alias for self._gtk_helper.safe_remove_css_class."""
        return self._gtk_helper.safe_remove_css_class

    @property
    def validate_iterable(self):
        """Read-only alias for self._data_helper.validate_iterable."""
        return self._data_helper.validate_iterable

    @property
    def validate_method(self):
        """Read-only alias for self._data_helper.validate_method."""
        return self._data_helper.validate_method

    @property
    def validate_widget(self):
        """Read-only alias for self._data_helper.validate_widget."""
        return self._data_helper.validate_widget

    @property
    def validate_string(self):
        """Read-only alias for self._data_helper.validate_string."""
        return self._data_helper.validate_string

    @property
    def validate_integer(self):
        """Read-only alias for self._data_helper.validate_integer."""
        return self._data_helper.validate_integer

    @property
    def validate_tuple(self):
        """Read-only alias for self._data_helper.validate_tuple."""
        return self._data_helper.validate_tuple

    @property
    def validate_bytes(self):
        """Read-only alias for self._data_helper.validate_bytes."""
        return self._data_helper.validate_bytes

    @property
    def validate_list(self):
        """Read-only alias for self._data_helper.validate_list."""
        return self._data_helper.validate_list

    @property
    def update_widget_safely(self):
        """Read-only alias for self._gtk_helper.update_widget_safely."""
        return self._gtk_helper.update_widget_safely

    @property
    def update_widget(self):
        """Read-only alias for self._gtk_helper.update_widget."""
        return self._gtk_helper.update_widget

    @property
    def is_widget_ready(self):
        """Read-only alias for self._gtk_helper.is_widget_ready."""
        return self._gtk_helper.is_widget_ready

    @property
    def widget_exists(self):
        """Read-only alias for self._gtk_helper.widget_exists."""
        return self._gtk_helper.widget_exists

    @property
    def create_popover(self):
        """Read-only alias for self._gtk_helper.create_popover."""
        return self._gtk_helper.create_popover

    @property
    def create_menu_with_actions(self):
        """Read-only alias for self._gtk_helper.create_menu_model."""
        return self._gtk_helper.create_menu_with_actions

    @property
    def create_async_button(self):
        """Read-only alias for self._gtk_helper.create_async_button."""
        return self._gtk_helper.create_async_button

    @property
    def is_view_valid(self):
        """Read-only alias for self._wf_helper.is_view_valid"""
        return self.wf_helper.is_view_valid

    def check_dependencies(self) -> bool:
        """Check if all dependencies are loaded"""
        return all(dep in self.obj.plugin_loader.plugins for dep in self.dependencies)

    def enable(self) -> None:
        """Enable the plugin"""
        self.on_enable()

    def disable(self) -> None:
        """
        Disable the plugin, remove its widget, and safely cancel all active
        background tasks and threads started by the plugin.
        """
        try:
            if self.main_widget:
                self.remove_widget(self.main_widget[0])
                self.logger.info("Widget removed successfully.")
            else:
                self.logger.warning("No widget to remove.")
            self._concurrency_helper.cleanup_tasks_and_futures()
            self.on_disable()
        except Exception as e:
            self.logger.error(message=f"Error disabling plugin: {e}", exc_info=True)

    def on_enable(self):
        """Hook for when plugin is enabled"""
        pass

    def on_disable(self):
        """Hook for when plugin is disabled. Plugin authors should add any necessary cleanup here."""
        pass

    def set_widget(self):
        """
        Defines and validates the widget to be added to the panel.
        """
        if self.main_widget is None:
            self.logger.error(
                "Critical Error: self.main_widget is still None. "
                "This indicates that the main widget was not properly initialized before calling set_widget()."
            )
            self.logger.debug(
                "Possible causes:\n"
                "1. The main widget container (e.g., Gtk.Box, Gtk.Button) was not created.\n"
                "2. self.main_widget was not assigned after creating the widget container.\n"
                "3. The plugin's initialization logic is incomplete or missing."
            )
            return None
        if not isinstance(self.main_widget, tuple) or len(self.main_widget) != 2:
            self.logger.error(
                "Invalid format for self.main_widget. Expected a tuple with two elements."
            )
            return None
        widget = self.main_widget[0]
        if isinstance(widget, list):
            for w in widget:  # pyright: ignore
                if w is None or not isinstance(w, Gtk.Widget):
                    self.logger.error(
                        f"Invalid widget in self.main_widget: {w}. "
                        f"The widget must be a valid Gtk.Widget instance. Plugin: {self.__class__.__name__}"
                    )
                    return None
        else:
            if widget is None or not isinstance(widget, Gtk.Widget):
                self.logger.error(
                    f"Invalid widget in self.main_widget: {widget}. "
                    f"The widget must be a valid Gtk.Widget instance. Plugin: {self.__class__.__name__}"
                )
                return None
            if widget.get_parent() is not None:
                self.logger.warning(
                    f"Widget {widget} already has a parent. It may not be appended correctly."
                )
        action = self.main_widget[1]
        if not self.validate_string(action, name=f"{action} from action in BasePlugin"):
            self.logger.error(
                f"Invalid action in self.main_widget: {action}. Must be a string."
            )
            return None
        if action not in ("append", "set_content"):
            self.logger.error(
                f"Invalid action in self.main_widget: {action}. "
                "The action must be either 'append' or 'set_content'."
            )
            return None
        self.logger.debug(
            f"Main widget successfully defined: {widget} with action '{action}'. Plugin: {self.__class__.__name__}"
        )
        return self.main_widget

    def about(self):
        """
        This is a foundational class that serves as the blueprint for all
        plugins in the waypanel application, providing core resources, a
        defined lifecycle, and standardized utilities for GTK, IPC, and now,
        non-blocking asynchronous and concurrent operations.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The `BasePlugin` class is the foundational component of waypanel's
        plugin architecture. Key logic includes:
        1.  **Concurrency Integration**: The constructor injects the global
            `asyncio` event loop and `ThreadPoolExecutor`, providing access
            via `self.global_loop` and `self.global_executor`. Helper methods
            (`run_in_thread`, `run_in_async_task`) simplify safe, non-blocking
            operations and now **automatically track** their running state.
        2.  **Safe Cleanup (`disable`)**: The improved `disable()` method now automatically
            iterates over `self._running_tasks` and `self._running_futures` to call
            `.cancel()` on any active asynchronous or background thread work,
            ensuring graceful termination before calling the custom `on_disable()` hook.
            The type hint for `self._running_futures` was updated to `Set[Future[Any]]`
            to resolve type-checking errors.
        3.  **GTK Synchronization**: The critical `schedule_in_gtk_thread` method
            uses `GLib.idle_add` to ensure any UI updates originating from a
            background thread or async task are safely executed on the main
            GTK thread, preventing crashes.
        4.  **Resource Injection & Safety**: Provides core resources (logger, IPC,
            config) and helper instances (`cmd`, `gtk_helper`) via read-only
            `@property` access, ensuring type safety and preventing accidental
            modification of shared components.
        """
        return self.code_explanation.__doc__
