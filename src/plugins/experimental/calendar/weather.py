import asyncio
import requests
from gi.repository import Gtk, GLib  # pyright: ignore
from src.plugins.core._base import BasePlugin

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
        weather_plugin.run_in_async_task(weather_plugin.setup_weather_async())
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

        self.schedule_in_gtk_thread(update_ui)
        self.update_task = self.global_loop.create_task(self.periodic_weather_update())
        self.run_in_async_task(self.fetch_and_update_weather_async())

    async def fetch_weather_data_async(self):
        """Asynchronously fetch weather data from the API."""
        lat, lon = COORDINATES
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        headers = {"User-Agent": "MyWeatherApp/1.0 youremail@example.com"}
        try:
            response = await asyncio.to_thread(
                requests.get, url, headers=headers, timeout=10
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
            if self.weather_label:
                if temperature is not None:
                    self.weather_label.set_label(f"Weather: {temperature}°C")  # pyright: ignore
                else:
                    self.weather_label.set_label("Weather: Error")  # pyright: ignore

        self.schedule_in_gtk_thread(update_label)

    async def periodic_weather_update(self):
        """Periodically fetch and update weather data."""
        while True:
            try:
                await asyncio.sleep(1800)
                self.run_in_async_task(self.fetch_and_update_weather_async())
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
        of a host plugin using asynchronous and thread-safe operations, now
        refactored to use BasePlugin helpers:
        1.  **Concurrency Management**: Direct imports of global loop variables
            are replaced by `BasePlugin`'s helpers:
            -   `self.run_in_async_task()` is used for fire-and-forget coroutines (initial setup and periodic updates).
            -   `self.global_loop.create_task()` is used specifically for the `self.periodic_weather_update` coroutine so the resulting `Task` object can be captured and later cancelled in `__del__`.
        2.  **Asynchronous Networking**: The blocking `requests.get` call is safely wrapped using the modern, high-level `await asyncio.to_thread(...)`, which automatically runs the synchronous function in a thread pool executor without blocking the main event loop.
        3.  **Thread-Safe UI Updates**: All interactions with the GUI, previously handled by `GLib.idle_add()`, are now consistently scheduled on the main GTK thread using the `self.schedule_in_gtk_thread()` helper, ensuring stability and adherence to GTK's thread safety rules.
        """
        return self.code_explanation.__doc__
