import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from waypanel.src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True

# Load the plugin only after essential plugins are loaded
DEPS = ["clock"]


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    """Initialize the calendar plugin."""
    if ENABLE_PLUGIN:
        calendar_plugin = CalendarPlugin(panel_instance)
        calendar_plugin.setup_calendar()
        return calendar_plugin


class CalendarPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_calendar = None
        self.calendar = None

    def setup_calendar(self):
        """Setup the calendar popover."""
        # Ensure the clock plugin is loaded
        if "clock" not in self.obj.plugins:
            self.log_error("Clock plugin is not loaded. Cannot append calendar.")
            return

        # Get the clock button from the clock plugin
        clock_plugin = self.obj.plugins["clock"]
        clock_button = clock_plugin.clock_button

        # Create the calendar popover
        self.popover_calendar = Gtk.Popover.new()
        self.popover_calendar.set_parent(clock_button)
        self.popover_calendar.set_has_arrow(False)

        # Create a grid to hold the calendar
        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)

        # Create calendar widget
        self.calendar = Gtk.Calendar()
        self.calendar.add_css_class("calendar-widget")

        # Connect calendar events
        self.calendar.connect("day-selected", self.on_day_selected)

        # Add calendar to grid
        grid.attach(self.calendar, 0, 0, 1, 1)

        # Add a label for selected date
        self.selected_date_label = Gtk.Label()
        self.selected_date_label.add_css_class("selected-date-label")
        self.selected_date_label.set_label("Select a date...")
        grid.attach(self.selected_date_label, 0, 1, 1, 1)

        # Set grid as the child of the popover
        self.popover_calendar.set_child(grid)

        # Connect toggle behavior
        clock_button.connect("clicked", self.toggle_calendar)

    def toggle_calendar(self, *_):
        """Toggle the calendar popover."""
        if self.popover_calendar and self.popover_calendar.is_visible():
            self.popover_calendar.popdown()
        else:
            self.popover_calendar.popup()

    def on_day_selected(self, calendar):
        """Handle day selection in calendar."""
        # Get the selected date as a GLib.DateTime object
        date_time = calendar.get_date()
        year = date_time.get_year()
        month = date_time.get_month()  # Note: Months are 1-based (January = 1)
        day = date_time.get_day_of_month()
        selected_date = f"{year}-{month:02d}-{day:02d}"
        self.selected_date_label.set_label(f"Selected: {selected_date}")
