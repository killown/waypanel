import asyncio
import requests
from gi.repository import Gtk, GLib
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop

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
        # Schedule the async setup without blocking
        global_loop.create_task(weather_plugin.setup_weather_async())
        return weather_plugin


class WeatherPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.weather_label = None
        self.update_task = None  # To store the periodic update task

    async def setup_weather_async(self):
        """Asynchronously set up the weather functionality."""
        await asyncio.sleep(0)  # Yield control immediately

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
        await self.attach_weather_to_calendar_async(calendar_plugin)

    async def attach_weather_to_calendar_async(self, calendar_plugin):
        """Asynchronously attach weather functionality to the calendar popover."""
        # Create a label for weather data
        self.weather_label = Gtk.Label()
        self.weather_label.add_css_class("weather-label")
        self.weather_label.set_label("Loading weather...")

        # Add the weather label to the calendar popover's grid
        # This UI update must be done on the main thread
        def update_ui():
            grid = calendar_plugin.popover_calendar.get_child()
            if grid:
                grid.attach(self.weather_label, 0, 1, 1, 1)  # Attach below the calendar
                grid.show()

        GLib.idle_add(update_ui)

        # Start the periodic update task
        self.update_task = global_loop.create_task(self.periodic_weather_update())

        # Fetch and update weather data once immediately
        await self.fetch_and_update_weather_async()

    async def fetch_weather_data_async(self):
        """Asynchronously fetch weather data from the API."""
        lat, lon = COORDINATES
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        headers = {"User-Agent": "MyWeatherApp/1.0 youremail@example.com"}

        try:
            # Run the blocking requests.get in a thread pool to avoid blocking the event loop
            response = await global_loop.run_in_executor(
                None, lambda: requests.get(url, headers=headers, timeout=10)
            )
            response.raise_for_status()
            data = response.json()
            temperature = data["properties"]["timeseries"][0]["data"]["instant"][
                "details"
            ]["air_temperature"]
            return temperature
        except asyncio.TimeoutError:
            self.log_error("Failed to fetch weather data: Request timed out.")
            return None
        except Exception as e:
            self.log_error(f"Failed to fetch weather data: {e}")
            return None

    async def fetch_and_update_weather_async(self):
        """Asynchronously fetch weather data and update the UI."""
        temperature = await self.fetch_weather_data_async()

        # Update the UI on the main GTK thread
        def update_label():
            if temperature is not None:
                self.weather_label.set_label(f"Weather: {temperature}°C")
            else:
                self.weather_label.set_label("Weather: Error")

        GLib.idle_add(update_label)

    async def periodic_weather_update(self):
        """Periodically fetch and update weather data."""
        while True:
            try:
                await asyncio.sleep(1800)  # Update every 30 minutes
                await self.fetch_and_update_weather_async()
            except asyncio.CancelledError:
                self.logger.info("Periodic weather update task was cancelled.")
                break
            except Exception as e:
                self.log_error(f"Error in periodic weather update: {e}")

    def __del__(self):
        """Cleanup method to cancel the periodic task when the plugin is destroyed."""
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
