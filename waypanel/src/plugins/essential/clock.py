import datetime
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
from waypanel.src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True

# Load the plugin only after essential plugins are loaded
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-center"  # Clock is usually in the center
    order = 5  # Middle priority
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the clock plugin."""
    if ENABLE_PLUGIN:
        clock_plugin = ClockPlugin(panel_instance)
        clock_plugin.create_clock_widget()
        return clock_plugin


class ClockPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.clock_button = None
        self.clock_box = None
        self.clock_label = None
        self.update_timeout_id = None

    def create_clock_widget(self):
        """Create and setup the clock widget."""
        # Create clock box container
        self.clock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_widget = (self.clock_box, "append")
        self.clock_box.set_halign(Gtk.Align.CENTER)
        self.clock_box.set_baseline_position(Gtk.BaselinePosition.CENTER)
        self.clock_box.add_css_class("clock-box")

        # Create clock button (instead of just label)
        self.clock_button = Gtk.Button()
        self.clock_button.add_css_class("clock-button")
        self.clock_label = Gtk.Label()
        self.clock_label.add_css_class("clock-label")
        self.clock_button.set_child(self.clock_label)

        # Append clock button to the clock box
        self.update_widget_safely(self.clock_box.append, self.clock_button)

        # Start updating the clock
        self.update_clock()
        self.schedule_updates()

    def update_clock(self):
        """Update the clock display with current time and date."""
        try:
            current_time = datetime.datetime.now().strftime(
                "%b %d %H:%M"
            )  # Includes date and time
            self.clock_label.set_label(current_time)
        except Exception as e:
            self.log_error(f"Error updating clock: {e}")
            return True  # Continue timeout

    def schedule_updates(self):
        """Schedule clock updates every minute."""
        # Calculate seconds until next minute
        now = datetime.datetime.now()
        seconds_until_next_minute = 60 - now.second

        # First update at the start of the next minute
        GLib.timeout_add_seconds(seconds_until_next_minute, self.update_clock)

        # Then update every 60 seconds
        self.update_timeout_id = GLib.timeout_add_seconds(60, self.update_clock)

    def stop_updates(self):
        """Stop clock updates (cleanup)."""
        if self.update_timeout_id:
            GLib.source_remove(self.update_timeout_id)
            self.update_timeout_id = None
