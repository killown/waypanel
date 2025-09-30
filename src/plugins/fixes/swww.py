from src.plugins.core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event
import subprocess
import gi
from gi.repository import GLib

# Enable or disable the plugin
ENABLE_PLUGIN = True

# This plugin depends on the event_manager to receive events
DEPS = ["event_manager"]


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    """Initialize the plugin if enabled."""
    if ENABLE_PLUGIN:
        return SwwwLayoutPlugin(panel_instance)
    return None


class SwwwLayoutPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger.info("SwwwLayoutPlugin initialized.")

    def restore_wallpaper(self):
        subprocess.run(["swww", "clear"], check=True)
        subprocess.run(["swww", "restore"], check=True)
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
