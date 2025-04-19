import datetime
import gi
from gi.repository import Gtk, GLib
import requests
import asyncio

gi.require_version("Gtk", "4.0")

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
COORDINATES = -23.5505, -46.6333  # Example coordinates (São Paulo)
# load the plugin only after essential plugins is loaded
DEPS = ["dockbar", "taskbar"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "center"  # Clock/calendar is usually in the center
    order = 5  # Middle priority
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the clock and calendar plugin."""
    if ENABLE_PLUGIN:
        clock_calendar_plugin = ClockCalendarPlugin(panel_instance)
        clock_calendar_plugin.create_clock_widget()
        return clock_calendar_plugin


class ClockCalendarPlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
        self.clock_button = None
        self.clock_box = None
        self.clock_label = None
        self.popover_calendar = None
        self.update_timeout_id = None
        self.weather_label = None  # Label for displaying weather data
        self.loop = asyncio.new_event_loop()  # Create a new asyncio event loop

    def append_widget(self):
        return self.clock_box

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

        # Apply additional CSS classes to containers
        # self.obj.top_panel_box_center.add_css_class("clock-container")

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

        # Create a grid to hold the calendar, weather, and additional widgets
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

        # Add a label for weather data
        self.weather_label = Gtk.Label()
        self.weather_label.add_css_class("weather-label")
        self.weather_label.set_label("Loading weather...")
        grid.attach(self.weather_label, 0, 2, 1, 1)

        # Fetch weather data asynchronously when the popover is opened
        GLib.idle_add(self.fetch_and_update_weather)

        # Set grid as the child of the popover
        self.popover_calendar.set_child(grid)

    def fetch_weather_data(self):
        """Fetch weather data from the API."""
        lat, lon = COORDINATES
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        headers = {"User-Agent": "MyWeatherApp/1.0 youremail@example.com"}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = response.json()
            temperature = data["properties"]["timeseries"][0]["data"]["instant"][
                "details"
            ]["air_temperature"]
            return temperature
        except Exception as e:
            print(f"Failed to fetch weather data: {e}")
            return None

    def fetch_and_update_weather(self):
        """Fetch weather data and update the UI."""
        try:
            temperature = self.fetch_weather_data()
            if temperature is not None:
                GLib.idle_add(self.weather_label.set_label, f"Weather: {temperature}°C")
            else:
                GLib.idle_add(self.weather_label.set_label, "Weather: Error")
        except Exception as e:
            print(f"Unexpected error fetching weather: {e}")
            GLib.idle_add(self.weather_label.set_label, "Weather: Error")

    def on_day_selected(self, calendar):
        """Handle day selection in calendar."""
        # Get the selected date as a GLib.DateTime object
        date_time = calendar.get_date()

        # Extract year, month, and day from the GLib.DateTime object
        year = date_time.get_year()
        month = date_time.get_month()  # Note: Months are 1-based (January = 1)
        day = date_time.get_day_of_month()

        # Format the selected date as a string
        selected_date = f"{year}-{month:02d}-{day:02d}"

        # Update the label with the selected date
        self.selected_date_label.set_label(f"Selected: {selected_date}")
