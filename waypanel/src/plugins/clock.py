import datetime
import gi
from gi.repository import Gtk, GLib

gi.require_version("Gtk", "4.0")

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def position():
    """Define the plugin's position and order."""
    position = "center"  # Clock/calendar is usually in the center
    order = 5  # Middle priority
    return position, order


def initialize_plugin(obj, app):
    """Initialize the clock and calendar plugin."""
    if ENABLE_PLUGIN:
        clock_calendar_plugin = ClockCalendarPlugin(obj, app)
        clock_calendar_plugin.create_clock_widget()


class ClockCalendarPlugin:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app
        self.clock_button = None
        self.clock_label = None
        self.popover_calendar = None
        self.update_timeout_id = None

    def create_clock_widget(self):
        """Create and setup the clock widget."""
        # Create clock box container
        self.clock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.clock_box.set_halign(Gtk.Align.CENTER)
        self.clock_box.set_baseline_position(Gtk.BaselinePosition.CENTER)

        # Add CSS class to clock box
        self.clock_box.add_css_class("clock-box")

        # Create clock button (instead of just label)
        self.clock_button = Gtk.Button()
        self.clock_button.add_css_class("clock-button")

        # Create clock label
        self.clock_label = Gtk.Label()
        self.clock_label.add_css_class("clock-label")

        # Add label to button
        self.clock_button.set_child(self.clock_label)

        # Connect clock button to toggle calendar
        self.clock_button.connect("clicked", self.toggle_calendar)

        # Add clock button to box
        self.clock_box.append(self.clock_button)

        # Add clock box to center panel
        self.obj.top_panel_box_center.append(self.clock_box)

        # Apply additional CSS classes to containers
        self.obj.top_panel_box_center.add_css_class("clock-container")

        # Initial time update
        self.update_clock()

        # Schedule periodic updates
        self.schedule_updates()

    def update_clock(self):
        """Update the clock display with current time."""
        try:
            current_time = datetime.datetime.now().strftime("%b %d %H:%M")
            self.clock_label.set_label(current_time)
        except Exception as e:
            self.obj.logger.error(f"Error updating clock: {e}")

        return True  # Continue timeout

    def schedule_updates(self):
        """Schedule clock updates every minute."""
        # Calculate seconds until next minute
        now = datetime.datetime.now()
        seconds_until_next_minute = 60 - now.second

        # First update at the start of next minute
        GLib.timeout_add_seconds(seconds_until_next_minute, self.update_clock)

        # Then update every 60 seconds
        self.update_timeout_id = GLib.timeout_add_seconds(60, self.update_clock)

    def stop_updates(self):
        """Stop clock updates (cleanup)."""
        if self.update_timeout_id:
            GLib.source_remove(self.update_timeout_id)
            self.update_timeout_id = None

    def toggle_calendar(self, *_):
        """Toggle the calendar popover."""
        if self.popover_calendar and self.popover_calendar.is_visible():
            self.popover_calendar.popdown()
        else:
            if not self.popover_calendar:
                self.create_calendar_popover()
            self.popover_calendar.popup()

    def create_calendar_popover(self):
        """Create the calendar popover."""
        # Create popover
        self.popover_calendar = Gtk.Popover.new()
        self.popover_calendar.set_parent(self.clock_button)
        self.popover_calendar.set_has_arrow(False)

        # Create a grid to hold the calendar and additional widgets
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

    def on_day_selected(self, calendar):
        """Handle day selection in calendar."""
        year, month, day = calendar.get_date()
        selected_date = f"{year}-{month + 1:02d}-{day:02d}"
        self.selected_date_label.set_label(f"Selected: {selected_date}")
        print(f"Selected date: {selected_date}")
        # You can add more functionality here, like opening a detailed view
