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
        self.enabled = getattr(self, "ENABLE_PLUGIN", True)
        self.layer_shell = create_panel.LayerShell
        self.set_layer_pos_exclusive = create_panel.set_layer_position_exclusive
        self.unset_layer_pos_exclusive = create_panel.unset_layer_position_exclusive

    def check_dependencies(self):
        """Check if all dependencies are loaded"""
        return all(dep in self.obj.plugin_loader.plugins for dep in self.dependencies)

    def enable(self):
        """Enable the plugin"""
        if not self.enabled:
            self.enabled = True
            self.on_enable()

    def disable(self):
        """Disable the plugin"""
        if self.enabled:
            self.enabled = False
            self.on_disable()

    def on_enable(self):
        """Hook for when plugin is enabled"""
        pass

    def on_disable(self):
        """Hook for when plugin is disabled"""
        pass

    def set_widget(self):
        return self.main_widget
