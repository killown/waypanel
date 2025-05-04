import requests
from gi.repository import Gtk, GLib
from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["calendar"]  # Depends on the calendar plugin

# Hardcoded coordinates for São Paulo
COORDINATES = ("-23.5505", "-46.6333")  # Latitude and Longitude for São Paulo


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    # This plugin doesn't have its own UI; it appends to the calendar plugin.
    return


def initialize_plugin(panel_instance):
    """Initialize the weather plugin."""
    if ENABLE_PLUGIN:
        weather_plugin = WeatherPlugin(panel_instance)
        weather_plugin.setup_weather()
        return weather_plugin


class WeatherPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.weather_label = None

    def setup_weather(self):
        """Set up the weather functionality."""
        # Ensure the calendar plugin is loaded
        if "calendar" not in self.plugins:
            self.log_error("Calendar plugin is not loaded. Cannot initialize weather.")
            return

        # Get the calendar popover from the calendar plugin
        calendar_plugin = self.plugins["calendar"]
        if not calendar_plugin.popover_calendar:
            self.log_error("Calendar popover not found. Cannot attach weather.")
            return

        # Attach weather label to the calendar popover
        self.attach_weather_to_calendar(calendar_plugin)

    def attach_weather_to_calendar(self, calendar_plugin):
        """Attach weather functionality to the calendar popover."""
        # Create a label for weather data
        self.weather_label = Gtk.Label()
        self.weather_label.add_css_class("weather-label")
        self.weather_label.set_label("Loading weather...")

        # Add the weather label to the calendar popover's grid
        grid = calendar_plugin.popover_calendar.get_child()
        if grid:
            grid.attach(self.weather_label, 0, 1, 1, 1)  # Attach below the calendar
            grid.show()

        # Fetch and update weather data periodically
        GLib.timeout_add_seconds(
            1800, self.fetch_and_update_weather
        )  # Update every 30 minutes

        def run_once():
            self.fetch_and_update_weather()
            return False

        GLib.idle_add(run_once)

    def fetch_weather_data(self):
        """Fetch weather data from the API."""
        lat, lon = COORDINATES
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        headers = {"User-Agent": "MyWeatherApp/1.0 youremail@example.com"}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            temperature = data["properties"]["timeseries"][0]["data"]["instant"][
                "details"
            ]["air_temperature"]
            return temperature
        except Exception as e:
            self.log_error(f"Failed to fetch weather data: {e}")
            return None

    def fetch_and_update_weather(self):
        """Fetch weather data and update the UI."""
        temperature = self.fetch_weather_data()
        if temperature is not None:
            GLib.idle_add(self.weather_label.set_label, f"Weather: {temperature}°C")
        else:
            GLib.idle_add(self.weather_label.set_label, "Weather: Error")
        return True  # Continue periodic updates
