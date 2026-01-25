def get_plugin_metadata(panel):
    """
    Define the plugin's properties and dependencies.
    """
    id = "org.waypanel.plugin.css_example"
    default_container = "top-panel-right"

    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "CSS Injector Example",
        "version": "1.0.0",
        "enabled": True,
        "container": container,
        "deps": ["css_generator"],
    }


def get_plugin_class():
    """
    Returns the main plugin class with deferred imports.
    """
    from src.plugins.core._base import BasePlugin

    class CSSInjectorExample(BasePlugin):
        def on_enable(self):
            """
            Asynchronous entry point for the plugin.
            """
            self._setup_ui()
            self._apply_custom_styles()

        def _setup_ui(self):
            """
            Creates a simple widget to demonstrate the applied CSS.
            """
            label = self.gtk.Label(label="CSS Styling Applied")
            label.add_css_class("example-custom-style")
            self.main_widget = (label, "append")

        def _apply_custom_styles(self):
            """
            Uses the css_generator plugin to install a specific CSS file.
            """
            self.plugins["css_generator"].install_css("example.css")

        def on_disable(self):
            """
            Lifecycle hook called when the plugin is disabled.
            """
            pass

    return CSSInjectorExample
