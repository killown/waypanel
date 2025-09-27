import asyncio
import requests
from gi.repository import Gtk, GLib  # pyright: ignore
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop

ENABLE_PLUGIN = True
DEPS = ["calendar"]
COORDINATES = ("-23.5505", "-46.6333")


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    return


def initialize_plugin(panel_instance):
    """Initialize the weather plugin."""
    if ENABLE_PLUGIN:
        weather_plugin = WeatherPlugin(panel_instance)
        global_loop.create_task(weather_plugin.setup_weather_async())
        return weather_plugin


class WeatherPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.weather_label = None
        self.update_task = None

    async def setup_weather_async(self):
        """Asynchronously set up the weather functionality."""
        await asyncio.sleep(0)
        if "calendar" not in self.plugins:
            self.logger.error(
                "Calendar plugin is not loaded. Cannot initialize weather."
            )
            return
        calendar_plugin = self.plugins["calendar"]
        if not calendar_plugin.popover_calendar:
            self.logger.error("Calendar popover not found. Cannot attach weather.")
            return
        await self.attach_weather_to_calendar_async(calendar_plugin)

    async def attach_weather_to_calendar_async(self, calendar_plugin):
        """Asynchronously attach weather functionality to the calendar popover."""
        self.weather_label = Gtk.Label()
        self.weather_label.add_css_class("weather-label")
        self.weather_label.set_label("Loading weather...")

        def update_ui():
            grid = calendar_plugin.popover_calendar.get_child()
            if grid:
                grid.attach(self.weather_label, 0, 1, 1, 1)
                grid.show()

        GLib.idle_add(update_ui)
        self.update_task = global_loop.create_task(self.periodic_weather_update())
        await self.fetch_and_update_weather_async()

    async def fetch_weather_data_async(self):
        """Asynchronously fetch weather data from the API."""
        lat, lon = COORDINATES
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        headers = {"User-Agent": "MyWeatherApp/1.0 youremail@example.com"}
        try:
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
            self.logger.error("Failed to fetch weather data: Request timed out.")
            return None
        except Exception as e:
            self.logger.error(f"Failed to fetch weather data: {e}")
            return None

    async def fetch_and_update_weather_async(self):
        """Asynchronously fetch weather data and update the UI."""
        temperature = await self.fetch_weather_data_async()

        def update_label():
            if temperature is not None:
                self.weather_label.set_label(f"Weather: {temperature}°C")  # pyright: ignore
            else:
                self.weather_label.set_label("Weather: Error")  # pyright: ignore

        GLib.idle_add(update_label)

    async def periodic_weather_update(self):
        """Periodically fetch and update weather data."""
        while True:
            try:
                await asyncio.sleep(1800)
                await self.fetch_and_update_weather_async()
            except asyncio.CancelledError:
                self.logger.info("Periodic weather update task was cancelled.")
                break
            except Exception as e:
                self.logger.error(f"Error in periodic weather update: {e}")

    def __del__(self):
        """Cleanup method to cancel the periodic task when the plugin is destroyed."""
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()

    def about(self):
        """
        This plugin adds a weather display to another plugin's user
        interface, fetching weather data asynchronously and updating the
        display periodically.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this plugin is to extend the functionality
        of a host plugin using asynchronous and thread-safe operations.
        Its design is based on these principles:
        1.  **UI Dependency and Augmentation**: The plugin has no
            standalone UI. Instead, it acts as a dependent module that
            searches for and attaches a custom widget (a weather label)
            to a pre-existing UI element provided by another plugin
            (the calendar popover).
        2.  **Asynchronous Networking**: It uses Python's `asyncio`
            to perform non-blocking network requests. Crucially, it
            leverages `run_in_executor` to safely execute the
            synchronous `requests.get` call in a background thread,
            preventing the main application's event loop from stalling.
        3.  **Thread-Safe UI Updates**: All interactions with the GUI
            are carefully scheduled on the main GTK thread using
            `GLib.idle_add()`. This is a critical pattern for ensuring
            that UI updates, such as changing the weather label's text,
            are performed in a thread-safe manner, avoiding crashes
            and race conditions.
        """
        return self.code_explanation.__doc__
