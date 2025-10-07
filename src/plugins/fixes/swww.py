def get_plugin_metadata(_):
    return {"enabled": True, "deps": ["event_manager"]}


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event

    class SwwwLayoutPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.logger.info("SwwwLayoutPlugin initialized.")

        def restore_wallpaper(self):
            self.run_cmd("swww clear")
            self.run_cmd("swww restore")
            self.logger.info("Executed: swww clear")
            self.logger.info("Executed: swww restore")

        @subscribe_to_event("output-layout-changed")
        def on_output_layout_changed(self, event_message):
            """
            Handle the output-layout-changed event by running swww clear and swww restore.
            """
            try:
                self.run_in_thread(self.restore_wallpaper)
            except Exception as e:
                self.logger.error(f"Unexpected error in on_output_layout_changed: {e}")

    return SwwwLayoutPlugin
