import psutil
import gi

from src.plugins.core._base import BasePlugin

gi.require_version("Gtk", "4.0")
from gi.repository import GLib

ENABLE_PLUGIN = False  # Set to True to enable this plugin

# NOTE: If the code hangs, it will delay the execution of all plugins. Always use GLib.idle_add for non-blocking code.


def get_plugin_placement(panel_instance):
    """
    Background plugin with no UI.

    Returning 'background' or None tells the plugin loader to treat this plugin
    as a background service with no widget to display.
    """
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        cpu_monitor = BackgroundCPUMonitor(panel_instance)
        cpu_monitor.start_cpu_monitor()
        return cpu_monitor


class BackgroundCPUMonitor(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.cpu_usage_update_interval = 5  # Update interval in seconds
        self.source_id = None  # To store the GLib timeout source ID

    def start_cpu_monitor(self):
        """Start monitoring CPU usage periodically."""
        self.source_id = GLib.timeout_add_seconds(
            self.cpu_usage_update_interval, self.log_cpu_usage
        )

    def log_cpu_usage(self):
        """Log the current CPU usage."""
        cpu_percent = psutil.cpu_percent(interval=None)
        self.logger.info(f"Current CPU Usage: {cpu_percent}%")
        return True  # Return True to keep the timeout active

    def stop_cpu_monitor(self):
        """Stop monitoring CPU usage."""
        if self.source_id:
            GLib.source_remove(self.source_id)
            self.source_id = None
            self.logger.info("Background CPU Monitor stopped.")

    def about(self):
        """Monitors and logs the current CPU usage in the background."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin acts as a background service to periodically monitor and
        log the system's CPU usage.

        Its core logic is centered on **non-blocking, timed execution**:

        1.  **Initialization**: The `start_cpu_monitor` method schedules a recurring
            task using `GLib.timeout_add_seconds`. This ensures the monitoring
            is non-blocking and doesn't freeze the main application.
        2.  **CPU Data Retrieval**: The `log_cpu_usage` method uses the `psutil`
            library to get the current CPU percentage.
        3.  **Logging**: It then logs the retrieved CPU usage to the panel's logger.
        4.  **Continuous Operation**: The method returns `True`, instructing `GLib`
            to continue the timed execution, effectively creating a continuous
            monitoring loop at the specified interval.
        """
        return self.code_explanation.__doc__
