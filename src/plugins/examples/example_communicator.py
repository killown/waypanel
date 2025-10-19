def get_plugin_metadata(panel):
    """
    Define where the plugin should be placed in the panel and its properties.
    plugin_loader will use this metadata to append the widget to the panel instance.
    Valid Positions:
        - Top Panel:
            "top-panel-left"
            "top-panel-center"
            "top-panel-right"
            "top-panel-systray"
            "top-panel-after-systray"
        - Bottom Panel:
            "bottom-panel-left"
            "bottom-panel-center"
            "bottom-panel-right"
        - Left Panel:
            "left-panel-top"
            "left-panel-center"
            "left-panel-bottom"
        - Right Panel:
            "right-panel-top"
            "right-panel-center"
            "right-panel-bottom"
        - Background:
            "background"
    Returns:
        dict: Plugin configuration metadata.
    """

    id = "org.waypanel.plugin.example_communicator_plugin"
    default_container = "top-panel-center"

    # check for user config containers, this is not necessary for background plugins
    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Example Communicator Plugin",
        "version": "1.0.0",
        "enabled": True,
        "container": container,
        "index": 5,
        "deps": ["top_panel"],
    }


def get_plugin_class():
    """
    Returns the main plugin class. All external imports are deferred here for lazy loading.
    """
    from src.plugins.core._base import BasePlugin

    class PluginCommunicator(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.clock_button = None
            self.volume_button = None

        def on_start(self):
            """
            Asynchronous entry point, called when the plugin is loaded and enabled.
            This replaces the obsolete initialize_plugin() function.
            """
            self.logger.info("Starting Plugin Communicator.")
            self._create_ui_elements()
            self.logger.info("Plugin Communicator started.")

        def _create_ui_elements(self):
            """Create UI elements for the Plugin Communicator using self.gtk helper."""
            self.clock_button = self.gtk.Button(label="Get Time")
            self.clock_button.connect("clicked", self.get_current_time)
            self.volume_button = self.gtk.Button(label="Get Volume")
            self.volume_button.connect("clicked", self.get_current_volume)
            if hasattr(self.obj, "top_panel_box_for_buttons"):
                self.obj.top_panel_box_for_buttons.append(self.clock_button)
                self.obj.top_panel_box_for_buttons.append(self.volume_button)

        def get_current_time(self, widget):
            """Get current time from clock_calendar_plugin."""
            if "clock" in self.obj.plugins:
                clock_plugin = self.obj.plugins["clock"]
                try:
                    current_time = clock_plugin.clock_label.get_text()
                    self.logger.info(f"Current Time: {current_time}")
                except Exception as e:
                    self.logger.error(e)  # pyright: ignore
            else:
                self.logger.info("clock plugin is not loaded")

        def get_current_volume(self, widget):
            """Get current volume from volume_scroll_plugin."""
            if "volume_scroll" in self.obj.plugins:
                volume_plugin = self.obj.plugins["volume_scroll"]
                try:
                    max_volume = volume_plugin.max_volume
                    self.logger.info(f"Max Volume: {max_volume}")
                except AttributeError:
                    self.logger.error(
                        "volume_scroll plugin does not have current_volume property"
                    )
                except Exception as e:
                    self.logger.error(e)  # pyright: ignore
            else:
                self.logger.info("volume scroll plugin is not loaded")

        def about(self):
            """Demonstrates inter-plugin communication by calling methods of other loaded plugins."""
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin serves as an example of how to access and interact with
            other loaded plugins within the panel.
            Its core logic is centered on **accessing and using other plugin instances**:
            1.  **UI Elements**: It creates two buttons in the panel's UI.
            2.  **Plugin Access**: When a button is clicked, its handler checks for the
                presence of a target plugin (e.g., "clock" or "volume_scroll") in the
                `self.obj.plugins` dictionary.
            3.  **Method Invocation**: If the target plugin exists, it directly
                accesses its methods or attributes (e.g., `clock_plugin.clock_label.get_text()`)
                to retrieve information.
            4.  **Logging**: It then logs the retrieved information, demonstrating that
                the communication was successful.
            """
            return self.code_explanation.__doc__

    return PluginCommunicator
