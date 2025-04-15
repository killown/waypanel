import os
import psutil
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib

ENABLE_PLUGIN = False  # Set to True to enable this plugin

# NOTE: If the code hangs, it will delay the execution of all plugins. Always use GLib.idle_add for non-blocking code.


class BackgroundCPUMonitor:
    def __init__(self):
        self.cpu_usage_update_interval = 5  # Update interval in seconds
        self.source_id = None  # To store the GLib timeout source ID

    def initialize_plugin(self, obj, app):
        """Initialize the background CPU monitor plugin."""
        if not ENABLE_PLUGIN:
            print("Background CPU Monitor plugin is disabled.")
            return

        print("Background CPU Monitor plugin initialized.")
        self.start_cpu_monitor()

    def start_cpu_monitor(self):
        """Start monitoring CPU usage periodically."""
        self.source_id = GLib.timeout_add_seconds(
            self.cpu_usage_update_interval, self.log_cpu_usage
        )

    def log_cpu_usage(self):
        """Log the current CPU usage."""
        cpu_percent = psutil.cpu_percent(interval=None)
        print(f"Current CPU Usage: {cpu_percent}%")
        return True  # Return True to keep the timeout active

    def stop_cpu_monitor(self):
        """Stop monitoring CPU usage."""
        if self.source_id:
            GLib.source_remove(self.source_id)
            self.source_id = None
            print("Background CPU Monitor stopped.")


def initialize_plugin(obj, app):
    if ENABLE_PLUGIN:
        cpu_monitor = BackgroundCPUMonitor()
        cpu_monitor.initialize_plugin(obj, app)


def position():
    # Return False to indicate this is a background-only plugin
    return False
