from src.core import create_panel
from gi.repository import Gtk
from typing import Any
from src.shared import path_handler
from src.shared import notify_send
from src.shared import wayfire_helpers
from src.shared import gtk_helpers
from src.shared import data_helpers
from src.shared import config_handler
from src.shared import command_runner

import inspect


class BasePlugin:
    """
    Base class for all waypanel plugins.

    This class provides a standardized structure and core resources for creating
    plugins that extend waypanel's functionality. Each plugin can have a UI widget
    and manage events, timers, or run as a background service.

    ## Plugin Lifecycle

    1.  **Initialization**: `__init__(self, panel_instance)` is called to create the plugin instance.
    2.  **Start**: `on_start()` is called after initialization. Use this for setup.
    3.  **Runtime**: The plugin listens for events and updates its state.
    4.  **Stop/Disable**: `on_stop()` is called when the plugin is disabled or reloaded.
    5.  **Cleanup**: `on_cleanup()` is called before full removal.

    ## Placement & Dependencies

    Plugins define their placement and order within the panel by implementing the
    `get_plugin_placement` function.

    **Function Signature:**
        `def get_plugin_placement(panel_instance):`
            `return position, order, priority`

    * `position`: `"top-panel-left"`, `"bottom-panel-right"`, etc.
    * `order`: The rendering order within the same panel section.
    * `priority`: The initialization order (lower numbers load first).

    **Background Services**: Return `"background"` or `None` to mark a plugin as a background service with no UI.

    **Dependencies**: Plugins can declare a list of dependencies (`DEPS`). The `PluginLoader` ensures
    dependent plugins are loaded first.

    Example: `DEPS = ["event_manager", "calendar"]`

    ## Creating a Plugin

    To create a new plugin, inherit from `BasePlugin` and implement the required methods.

    1.  Inherit from `BasePlugin`.
    2.  Call `super().__init__(panel_instance)` in your constructor.
    3.  Implement `get_plugin_placement` to define its position.
    4.  Optionally override lifecycle methods (`on_start`, `on_stop`, etc.).
    5.  Set `self.main_widget` to a `(widget, append_method)` tuple for UI integration.

    Example: `self.main_widget = (self.button, "append")`
    """

    def __init__(self, panel_instance):
        """
        Initializes the BasePlugin and injects core resources.

        This method provides access to shared components from the main panel instance.
        Subclasses must call `super().__init__(panel_instance)` to ensure proper setup.

        ### 📋 Available Attributes (Do not reassign)

        * `self.obj`: Reference to the main Panel instance.
        * `self.logger`: Logger object for logging messages.
        * `self.ipc`: IPC client for Wayfire communication.
        * `self.config`: Plugin-specific configuration from `config.toml`.
        * `self.plugins`: Dictionary of all loaded plugins.
        * `self.plugin_loader`: Reference to the plugin loader.
        * `self.save_config`: Function to save updated config.
        * `self.reload_config`: Function to reload the config at runtime.
        * `self.update_widget_safely`: Safe method to update UI widgets.
        * `self.dependencies`: List of required plugin names.
        * `self.layer_shell`: Reference to LayerShell for setting panel layers.

        **Example Usage:**

        ```python
        class MyPlugin(BasePlugin):
            def __init__(self, panel_instance):
                super().__init__(panel_instance)  # Required!
                self.logger.info("MyPlugin initialized")
                if "event_manager" in self.plugins:
                    event_manager = self.plugins["event_manager"]
                    event_manager.subscribe_to_event("view-focused", self.on_view_focused)
        ```
        """
        self.obj = panel_instance
        self.path_handler: Any = path_handler.PathHandler("waypanel", panel_instance)
        self.notifier: Any = notify_send.Notifier()
        self.wf_helper: Any = wayfire_helpers.WayfireHelpers(
            panel_instance.ipc, panel_instance.logger
        )
        self.gtk_helper: Any = gtk_helpers.GtkHelpers(panel_instance)
        self.data_helper: Any = data_helpers.DataHelpers()
        self.config_handler: Any = config_handler.ConfigHandler(panel_instance)
        self.cmd: Any = command_runner.CommandRunner(panel_instance)
        self.bottom_panel: Any = self.obj.bottom_panel
        self.top_panel: Any = self.obj.top_panel
        self.left_panel: Any = self.obj.left_panel
        self.right_panel: Any = self.obj.right_panel
        self.main_widget = None
        self.plugin_file = None
        self.update_widget_safely: Any = self.gtk_helper.update_widget_safely
        self.logger: Any = panel_instance.logger
        self.plugins: Any = panel_instance.plugin_loader.plugins
        self.plugin_loader: Any = panel_instance.plugin_loader
        self.update_widget: Any = self.gtk_helper.update_widget
        self.ipc: Any = panel_instance.ipc
        self.ipc_client = None
        self.ipc_server = panel_instance.ipc_server
        self.compositor = panel_instance.ipc_server.compositor
        self.dependencies: Any = getattr(self, "DEPS", [])
        self.layer_shell: Any = create_panel.LayerShell
        self.set_layer_pos_exclusive: Any = create_panel.set_layer_position_exclusive
        self.unset_layer_pos_exclusive: Any = (
            create_panel.unset_layer_position_exclusive
        )

    def log_error(self, message) -> None:
        """Log an error message with contextual information about the caller.

        Captures the caller's filename, package, and function name to provide
        detailed context in the log entry. Ensures proper cleanup of internal
        frame references to prevent memory leaks.

        Args:
            message (str): The error message to be logged.
        """
        # Get the caller's frame (two levels up: one for this function, one for the caller)
        frame = inspect.currentframe().f_back  # type: ignore
        try:
            # Extract caller's filename, package, and function name
            caller_file = frame.f_code.co_filename.split("/")[-1]  # type: ignore
            caller_package = frame.f_globals.get("__package__", "unknown")  # type: ignore
            caller_func = frame.f_code.co_name  # type: ignore

            # Log the error with the caller's context
            self.logger.error(
                message,
                extra={
                    "file": caller_file,
                    "package": caller_package,
                    "func": caller_func,
                },
            )
        finally:
            # Ensure the frame is cleared to avoid memory leaks
            del frame

    def check_dependencies(self) -> bool:
        """Check if all dependencies are loaded"""
        return all(dep in self.obj.plugin_loader.plugins for dep in self.dependencies)

    def enable(self) -> None:
        """Enable the plugin"""
        self.on_enable()

    def disable(self) -> None:
        """
        Disable the plugin and remove its widget.
        """
        try:
            # Remove the widget from the panel
            if self.main_widget:
                self.gtk_helper.remove_widget(
                    self.main_widget[0]
                )  # Extract the widget from the tuple
                self.logger.info("Widget removed successfully.")
            else:
                self.logger.warning("No widget to remove.")

            # Call the on_disable hook if defined
            self.on_disable()

        except Exception as e:
            self.log_error(
                message=f"Error disabling plugin: {e}",
            )

    def on_enable(self):
        """Hook for when plugin is enabled"""
        pass

    def on_disable(self):
        """Hook for when plugin is disabled"""
        pass

    def set_widget(self):
        """
        Defines and validates the widget to be added to the panel.

        This method validates `self.main_widget`, ensuring it's a properly formatted
        tuple containing a valid `Gtk.Widget` and an accepted action string (`"append"` or
        `"set_content"`). It logs errors and warnings for improper configuration,
        preventing common UI-related crashes.

        Returns:
            tuple: The `(widget, action)` tuple if valid, or `None` if invalid.
        """
        # Log the status of self.main_widget for debugging purposes
        if self.main_widget is None:
            self.log_error(
                "Critical Error: self.main_widget is still None. "
                "This indicates that the main widget was not properly initialized before calling set_widget()."
            )
            self.logger.debug(
                "Possible causes:\n"
                "1. The main widget container (e.g., Gtk.Box, Gtk.Button) was not created.\n"
                "2. self.main_widget was not assigned after creating the widget container.\n"
                "3. The plugin's initialization logic is incomplete or missing."
            )
            return None  # Return None to indicate failure

        # Ensure self.main_widget is a tuple with two elements
        if not isinstance(self.main_widget, tuple) or len(self.main_widget) != 2:
            self.log_error(
                "Invalid format for self.main_widget. Expected a tuple with two elements."
            )
            return None

        # Validate the widget
        widget = self.main_widget[0]
        if isinstance(widget, list):
            for w in widget:  # pyright: ignore
                if w is None or not isinstance(w, Gtk.Widget):
                    self.log_error(
                        f"Invalid widget in self.main_widget: {w}. "
                        "The widget must be a valid Gtk.Widget instance. Plugin: {self.__class__.__name__}"
                    )
                    return None
        else:
            if widget is None or not isinstance(widget, Gtk.Widget):
                self.log_error(
                    f"Invalid widget in self.main_widget: {widget}. "
                    "The widget must be a valid Gtk.Widget instance. Plugin: {self.__class__.__name__}"
                )
                return None

            # Validate widget parentage
            if widget.get_parent() is not None:
                self.logger.warning(
                    f"Widget {widget} already has a parent. It may not be appended correctly."
                )

        # Validate the action
        action = self.main_widget[1]
        if not self.data_helper.validate_string(
            action, name=f"{action} from action in BasePlugin"
        ):
            self.log_error(
                f"Invalid action in self.main_widget: {action}. Must be a string."
            )
            return None
        if action not in ("append", "set_content"):
            self.log_error(
                f"Invalid action in self.main_widget: {action}. "
                "The action must be either 'append' or 'set_content'."
            )
            return None

        # Log success if self.main_widget is valid
        self.logger.debug(
            f"Main widget successfully defined: {widget} with action '{action}'. Plugin: {self.__class__.__name__}"
        )
        return self.main_widget

    def on_start(self):
        """
        Hook called when the plugin is initialized.

        Use this method to set up resources, register callbacks, or initialize
        UI components after the plugin is loaded.
        """
        pass

    def on_stop(self):
        """
        Hook called when the plugin is stopped or unloaded.

        Use this method to clean up resources, unregister callbacks, or save
        state before the plugin is removed.
        """
        pass

    def on_reload(self):
        """
        Hook called when the plugin is reloaded dynamically.

        Use this method to refresh data or reset the internal state without
        fully stopping and restarting the plugin.
        """
        pass

    def on_cleanup(self):
        """
        Hook called before the plugin is completely removed.

        Use this method for final cleanup tasks that may not be handled by
        `on_stop()`.
        """
        pass

    def about(self):
        """
        This is a foundational class that serves as the blueprint for all
        plugins in the waypanel application, providing core resources, a
        defined lifecycle, and a standardized structure.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The `BasePlugin` class is the foundational component of waypanel's
        plugin architecture, employing the Template Method Design Pattern
        to provide a consistent and extensible structure. Its core logic
        is built around several key principles:

        1.  **Standardized Lifecycle**: The class defines a clear lifecycle
            for every plugin with methods like `on_start()`, `on_stop()`,
            and `on_cleanup()`. This template ensures that all plugins
            handle initialization, runtime, and cleanup in a predictable
            and safe manner, preventing common issues like resource leaks.

        2.  **Shared Resource Injection**: In its constructor, the class
            initializes and provides access to critical shared resources
            from the main panel instance. These resources, such as the
            `logger`, IPC client (`self.ipc`), and configuration (`self.config`),
            are readily available to any subclass, promoting code reuse
            and decoupling plugins from the main application's logic.

        3.  **UI Integration and Validation**: The `set_widget()` method
            serves as a centralized and robust entry point for plugins
            to define and add their UI components to the panel. It includes
            comprehensive checks to validate the widget type and format,
            ensuring that only valid GTK widgets are added. This
            prevents common UI-related crashes and errors.
        """
        return self.code_explanation.__doc__
