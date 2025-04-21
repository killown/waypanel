from waypanel.src.core import create_panel


class BasePlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
        self.bottom_panel = self.obj.bottom_panel
        self.top_panel = self.obj.top_panel
        self.left_panel = self.obj.left_panel
        self.right_panel = self.obj.right_panel
        self.main_widget = None
        self.logger = panel_instance.logger
        self.utils = panel_instance.utils
        self.plugins = panel_instance.plugin_loader.plugins
        self.plugin_loader = self.obj.plugin_loader
        self.utils = self.obj.utils
        self.update_widget = self.utils.update_widget
        self.config = panel_instance.config
        self.ipc = panel_instance.ipc
        self.dependencies = getattr(self, "DEPS", [])
        self.layer_shell = create_panel.LayerShell
        self.set_layer_pos_exclusive = create_panel.set_layer_position_exclusive
        self.unset_layer_pos_exclusive = create_panel.unset_layer_position_exclusive

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
