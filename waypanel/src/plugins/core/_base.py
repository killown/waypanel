from waypanel.src.core import create_panel
from gi.repository import Gtk
from typing import Any


class BasePlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
        self.bottom_panel: Any = self.obj.bottom_panel
        self.top_panel: Any = self.obj.top_panel
        self.left_panel: Any = self.obj.left_panel
        self.right_panel: Any = self.obj.right_panel
        self.main_widget = None
        self.plugin_file = None
        self.logger: Any = panel_instance.logger
        self.plugins: Any = panel_instance.plugin_loader.plugins
        self.plugin_loader: Any = self.obj.plugin_loader
        self.utils: Any = panel_instance.utils
        self.update_widget: Any = self.utils.update_widget
        self.config: Any = panel_instance.config
        self.ipc: Any = panel_instance.ipc
        self.dependencies: Any = getattr(self, "DEPS", [])
        self.layer_shell: Any = create_panel.LayerShell
        self.set_layer_pos_exclusive: Any = create_panel.set_layer_position_exclusive
        self.unset_layer_pos_exclusive: Any = (
            create_panel.unset_layer_position_exclusive
        )

    def check_dependencies(self):
        """Check if all dependencies are loaded"""
        return all(dep in self.obj.plugin_loader.plugins for dep in self.dependencies)

    def enable(self):
        """Enable the plugin"""
        self.on_enable()

    def disable(self):
        """
        Disable the plugin and remove its widget.
        """
        try:
            # Remove the widget from the panel
            if self.main_widget:
                self.utils.remove_widget(
                    self.main_widget[0]
                )  # Extract the widget from the tuple
                self.logger.info("Widget removed successfully.")
            else:
                self.logger.warning("No widget to remove.")

            # Call the on_disable hook if defined
            self.on_disable()

        except Exception as e:
            self.logger.error_handler.handle(
                error=e,
                message="Error disabling plugin.",
                level="error",
            )

    def on_enable(self):
        """Hook for when plugin is enabled"""
        pass

    def on_disable(self):
        """Hook for when plugin is disabled"""
        pass

    def set_widget(self):
        """
        Define the widget to be added to the panel.
        Returns:
            tuple: (widget, action) where action is "append" or "set_content".
        """
        # Log the status of self.main_widget for debugging purposes
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
            return None  # Return None to indicate failure

        # Ensure self.main_widget is a tuple with two elements
        if not isinstance(self.main_widget, tuple) or len(self.main_widget) != 2:
            self.logger.error(
                "Invalid format for self.main_widget. Expected a tuple with two elements."
            )
            return None

        # Validate the widget
        widget = self.main_widget[0]
        if isinstance(widget, list):
            for w in widget:
                if w is None or not isinstance(w, Gtk.Widget):
                    self.logger.error(
                        f"Invalid widget in self.main_widget: {w}."
                        "The widget must be a valid Gtk.Widget instance. Plugin: {self.__class__.__name__}"
                    )
                    return None
        else:
            if widget is None or not isinstance(widget, Gtk.Widget):
                self.logger.error(
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
        if not self.utils.validate_string(
            action, name=f"{action} from action in BasePlugin"
        ):
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

        # Log success if self.main_widget is valid
        self.logger.debug(
            f"Main widget successfully defined: {widget} with action '{action}'. Plugin: {self.__class__.__name__}"
        )
        return self.main_widget

    def on_start(self):
        """
        Called when the plugin is initialized.
        Use this method to set up resources, register callbacks, or initialize UI components.
        """
        pass

    def on_stop(self):
        """
        Called when the plugin is stopped or unloaded.
        Use this method to clean up resources, unregister callbacks, or save state.
        """
        pass

    def on_reload(self):
        """
        Called when the plugin is reloaded dynamically.
        Use this method to refresh data or reset internal state.
        """
        pass

    def on_cleanup(self):
        """
        Called before the plugin is completely removed.
        Use this method for final cleanup tasks.
        """
        pass
