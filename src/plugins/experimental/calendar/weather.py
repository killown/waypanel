def get_plugin_metadata(_):
    about = """
    This plugin adds a weather display to another plugin's user
    interface, fetching weather data asynchronously and updating the
    display periodically.
    """
    return {
        "id": "org.waypanel.plugin.weather",
        "name": "Weather",
        "version": "1.2.0",
        "enabled": True,
        "priority": 99,
        "deps": ["calendar"],
        "description": about,
    }


def get_plugin_class():
    """
    The main plugin class entry point. ALL imports are deferred here
    to comply with the Waypanel loading architecture.
    Returns:
        type: The WeatherPlugin class.
    """
    from datetime import datetime
    from typing import cast, Dict, Any, Optional
    from src.plugins.core._base import BasePlugin

    class WeatherPlugin(BasePlugin):
        """
        Plugin to fetch and display a detailed weather summary,
        integrated into the calendar popover using a structured Gtk.Grid.
        """

        def __init__(self, panel_instance):
            """
            Initialize the plugin and retrieve configuration settings.
            Args:
                panel_instance: The main panel instance provided by the framework.
            """
            super().__init__(panel_instance)
            self.config_handler.set_setting_hint(
                "org.waypanel.plugin.calendar",
                ["weather"],
                "Settings for the weather plugin's integration into the calendar popover. Enable the Weather plugin for this section to be used.",
            )
            self.config_handler.set_setting_hint(
                "org.waypanel.plugin.calendar",
                ["weather", "coordinates"],
                "The latitude and longitude coordinates (as a tuple of strings) for fetching local weather data. Example: [-23.5505, -46.6333]",
            )
            self.weather_grid: Optional[self.gtk.Grid] = None  # pyright: ignore
            self.weather_title_label: Optional[self.gtk.Label] = None  # pyright: ignore
            self.current_temp_value_label: Optional[self.gtk.Label] = None  # pyright: ignore
            self.temp_value_label: Optional[self.gtk.Label] = None  # pyright: ignore
            self.wind_value_label: Optional[self.gtk.Label] = None  # pyright: ignore
            self.humidity_value_label: Optional[self.gtk.Label] = None  # pyright: ignore
            self.rain_summary_label: Optional[self.gtk.Label] = None  # pyright: ignore
            self.rain_total_label: Optional[self.gtk.Label] = None  # pyright: ignore
            self.update_task = None
            config_coords = self.get_root_setting(
                ["org.waypanel.plugin.calendar", "weather", "coordinates"],
                [
                    "-23.5505",
                    "-46.6333",
                ],
            )
            if isinstance(config_coords, (list, tuple)) and len(config_coords) == 2:
                self.coordinates = tuple(config_coords)
                self.logger.info(f"Using coordinates from config: {self.coordinates}")
            else:
                self.coordinates = ("-23.5505", "-46.6333")
                self.logger.warning(
                    f"Weather coordinates not configured or invalid. Defaulting to {self.coordinates}."
                )

        def on_start(self):
            """
            Starts the asynchronous weather setup if coordinates are available.
            """
            if self.coordinates:
                self.run_in_async_task(self.setup_weather_async())
            else:
                self.logger.error(
                    "Weather coordinates are missing or invalid in config. Plugin functionally disabled."
                )

        async def setup_weather_async(self):
            """Asynchronously set up the weather functionality."""
            await self.asyncio.sleep(0)
            if "calendar" not in self.plugins:
                self.logger.error(
                    "Calendar plugin is not loaded. Cannot initialize weather."
                )
                return
            calendar_plugin = self.plugins["calendar"]
            if (
                not hasattr(calendar_plugin, "popover_calendar")
                or not calendar_plugin.popover_calendar
            ):
                self.logger.error("Calendar popover not found. Cannot attach weather.")
                return
            await self.attach_weather_to_calendar_async(calendar_plugin)

        async def attach_weather_to_calendar_async(self, calendar_plugin):
            """
            Asynchronously attach weather functionality to the calendar popover
            using a Gtk.Grid for structured layout.
            """
            self.weather_grid = self.gtk.Grid()
            self.weather_grid.add_css_class("weather-grid")  # pyright: ignore
            self.weather_grid.set_column_spacing(12)  # pyright: ignore
            self.weather_grid.set_row_spacing(6)  # pyright: ignore
            self.weather_grid.set_margin_start(12)  # pyright: ignore
            self.weather_grid.set_valign(self.gtk.Align.START)  # pyright: ignore
            self.weather_title_label = self.gtk.Label(label="🌍 Loading Weather...")  # pyright: ignore
            self.weather_title_label.add_css_class("weather-title-label")  # pyright: ignore
            self.weather_title_label.set_halign(self.gtk.Align.START)  # pyright: ignore
            self.weather_grid.attach(self.weather_title_label, 0, 0, 2, 1)  # pyright: ignore

            def create_weather_row(icon: str, name: str, row: int) -> self.gtk.Label:  # pyright: ignore
                """Creates a label-value row and returns the value label."""
                icon_label = self.gtk.Label(label=f"{icon} {name}")
                icon_label.set_halign(self.gtk.Align.START)
                self.weather_grid.attach(icon_label, 0, row, 1, 1)  # pyright: ignore
                value_label = self.gtk.Label(label="...")
                value_label.set_halign(self.gtk.Align.END)
                self.weather_grid.attach(value_label, 1, row, 1, 1)  # pyright: ignore
                return value_label

            self.current_temp_value_label = create_weather_row("🌡️", "Current Temp:", 1)
            self.current_temp_value_label.add_css_class("weather-temp-value-label")  # pyright: ignore
            self.temp_value_label = create_weather_row("📊", "Avg Temp (24h):", 2)
            self.temp_value_label.add_css_class("weather-temp-avg-value-label")  # pyright: ignore
            self.wind_value_label = create_weather_row("💨", "Avg Wind:", 3)
            self.wind_value_label.add_css_class("weather-wind-value-label")  # pyright: ignore
            self.humidity_value_label = create_weather_row("💧", "Avg Humidity:", 4)
            self.humidity_value_label.add_css_class("weather-humidity-value-label")  # pyright: ignore
            self.rain_summary_label = self.gtk.Label(label="🌦️ Rain (next 6h):\n  ...")
            self.rain_summary_label.add_css_class("weather-rain-summary-label")  # pyright: ignore
            self.rain_summary_label.set_halign(self.gtk.Align.START)  # pyright: ignore
            self.rain_summary_label.set_justify(self.gtk.Justification.LEFT)  # pyright: ignore
            self.weather_grid.attach(self.rain_summary_label, 0, 5, 2, 1)  # pyright: ignore
            self.rain_total_label = self.gtk.Label(label="Total rain (24h): ...")
            self.rain_total_label.add_css_class("weather-total-label")  # pyright: ignore
            self.rain_total_label.set_halign(self.gtk.Align.START)  # pyright: ignore
            self.weather_grid.attach(self.rain_total_label, 0, 6, 2, 1)  # pyright: ignore

            def update_ui():
                """Attaches the grid to the calendar popover."""
                grid = calendar_plugin.popover_calendar.get_child()
                if grid:
                    grid.attach(cast(self.gtk.Grid, self.weather_grid), 1, 0, 1, 1)  # pyright: ignore
                    cast(self.gtk.Grid, self.weather_grid).show()  # pyright: ignore
                    grid.show()

            self.schedule_in_gtk_thread(update_ui)
            self.run_in_async_task(self.fetch_and_update_weather_async())
            self.update_task = self.global_loop.create_task(
                self.periodic_weather_update()
            )

        async def fetch_weather_data_async(self) -> Optional[Dict[str, Any]]:
            """
            Asynchronously fetch full weather data from the API.
            This runs the blocking network request in a separate thread
            to avoid blocking the main asyncio event loop.
            Returns:
                dict | None: The parsed JSON response, or None on failure.
            """
            lat, lon = self.coordinates
            url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
            headers = {"User-Agent": "WaypanelWeatherPlugin/1.2 (github.com/waypanel)"}
            try:
                response = await self.asyncio.to_thread(
                    self.requests.get, url, headers=headers, timeout=10
                )
                response.raise_for_status()
                return response.json()
            except self.asyncio.TimeoutError:
                self.logger.error("Failed to fetch weather data: Request timed out.")
                return None
            except Exception as e:
                self.logger.error(f"Failed to fetch weather data: {e}")
                return None

        def _process_weather_data(
            self, data: Dict[str, Any]
        ) -> Optional[Dict[str, Any]]:
            """
            Processes the raw forecast JSON into a structured dictionary.
            Args:
                data (dict): The JSON data from the weather API.
            Returns:
                dict | None: A dictionary of formatted strings and bools for UI display
                             (including "current_temp"), or None on failure.
            """
            try:
                results: Dict[str, Any] = {}
                timeseries = data["properties"]["timeseries"]
                if not timeseries:
                    self.logger.warning("Weather data timeseries is empty.")
                    return None
                try:
                    current_details = (
                        timeseries[0]
                        .get("data", {})
                        .get("instant", {})
                        .get("details", {})
                    )
                    current_temp = current_details.get("air_temperature")
                    if current_temp is not None:
                        results["current_temp"] = f"{current_temp:.1f} °C"
                    else:
                        results["current_temp"] = "N/A"
                except (IndexError, KeyError, TypeError) as e:
                    self.logger.warning(f"Could not parse current temp: {e}")
                    results["current_temp"] = "N/A"
                next_24h = timeseries[:24]
                rain_hours = []
                total_rain = 0.0
                temps, winds, hums = [], [], []
                for entry in next_24h:
                    instant_details = (
                        entry.get("data", {}).get("instant", {}).get("details", {})
                    )
                    if instant_details:
                        temps.append(instant_details.get("air_temperature"))
                        winds.append(instant_details.get("wind_speed"))
                        hums.append(instant_details.get("relative_humidity"))
                    next_1_hr = entry.get("data", {}).get("next_1_hours", {})
                    if next_1_hr:
                        rain = next_1_hr.get("details", {}).get(
                            "precipitation_amount", 0.0
                        )
                        total_rain += rain
                        if rain > 0:
                            rain_hours.append((entry.get("time"), rain))
                valid_temps = [t for t in temps if t is not None]
                valid_winds = [w for w in winds if w is not None]
                valid_hums = [h for h in hums if h is not None]
                if valid_temps:
                    avg_temp = sum(valid_temps) / len(valid_temps)
                    results["temp"] = f"{avg_temp:.1f} °C"
                else:
                    results["temp"] = "N/A"
                if valid_winds:
                    avg_wind = sum(valid_winds) / len(valid_winds)
                    results["wind"] = f"{avg_wind:.1f} m/s"
                else:
                    results["wind"] = "N/A"
                if valid_hums:
                    avg_hum = sum(valid_hums) / len(valid_hums)
                    results["humidity"] = f"{avg_hum:.0f}%"
                else:
                    results["humidity"] = "N/A"
                rain_next_6h = [
                    r for r in rain_hours if r[0] < timeseries[6]["time"] and r[1] > 0
                ]
                results["has_6h_rain"] = bool(rain_next_6h)
                rain_summary_lines = ["🌦️ Rain (next 6h):"]
                if rain_next_6h:
                    for t, r in rain_next_6h:
                        t_local = datetime.fromisoformat(
                            t.replace("Z", "+00:00")
                        ).strftime("%H:%M")
                        rain_summary_lines.append(f"  • {t_local}: {r:.1f} mm")
                else:
                    rain_summary_lines.append("  ☀️ No rain expected.")
                results["rain_summary"] = "\n".join(rain_summary_lines)
                results["has_24h_rain"] = total_rain > 0
                results["rain_total"] = f"Total rain (24h): {total_rain:.1f} mm"
                return results
            except (KeyError, IndexError, TypeError, ZeroDivisionError) as e:
                self.logger.error(f"Error processing weather data: {e}", exc_info=True)
                return None

        async def fetch_and_update_weather_async(self):
            """Asynchronously fetch weather data and update the UI grid."""
            data = await self.fetch_weather_data_async()
            processed_data: Optional[Dict[str, Any]] = None
            if data:
                processed_data = self._process_weather_data(data)

            def update_ui():
                """Safely update GTK labels from the main thread."""
                if not self.weather_grid:
                    return
                assert self.weather_title_label is not None
                assert self.current_temp_value_label is not None
                assert self.temp_value_label is not None
                assert self.wind_value_label is not None
                assert self.humidity_value_label is not None
                assert self.rain_summary_label is not None
                assert self.rain_total_label is not None
                if processed_data:
                    self.weather_title_label.set_label("🌍 Weather Summary")
                    self.current_temp_value_label.set_label(
                        processed_data["current_temp"]
                    )
                    self.temp_value_label.set_label(processed_data["temp"])
                    self.wind_value_label.set_label(processed_data["wind"])
                    self.humidity_value_label.set_label(processed_data["humidity"])
                    has_6h_rain = processed_data.get("has_6h_rain", False)
                    self.rain_summary_label.set_visible(has_6h_rain)
                    if has_6h_rain:
                        self.rain_summary_label.set_label(
                            processed_data["rain_summary"]
                        )
                    has_24h_rain = processed_data.get("has_24h_rain", False)
                    self.rain_total_label.set_visible(has_24h_rain)
                    if has_24h_rain:
                        self.rain_total_label.set_label(processed_data["rain_total"])
                else:
                    status_text = "Failed to fetch" if not data else "Parse error"
                    self.weather_title_label.set_label(f"🌍 Weather: {status_text}")
                    self.current_temp_value_label.set_label("N/A")
                    self.temp_value_label.set_label("N/A")
                    self.wind_value_label.set_label("N/A")
                    self.humidity_value_label.set_label("N/A")
                    self.rain_summary_label.set_visible(False)
                    self.rain_total_label.set_visible(False)

            self.schedule_in_gtk_thread(update_ui)

        async def periodic_weather_update(self):
            """Periodically fetch and update weather data every 30 minutes."""
            while True:
                try:
                    await self.asyncio.sleep(1800)
                    self.run_in_async_task(self.fetch_and_update_weather_async())
                except self.asyncio.CancelledError:
                    self.logger.info("Periodic weather update task was cancelled.")
                    break
                except Exception as e:
                    self.logger.error(f"Error in periodic weather update: {e}")
                    await self.asyncio.sleep(300)

        def on_stop(self):
            """Cleanup method to cancel the periodic task when the plugin is stopped."""
            if self.update_task and not self.update_task.done():
                self.update_task.cancel()
                self.logger.info("Cancelled weather periodic update task.")

        def code_explanation(self):
            """
            Explains the core architecture of the plugin.
            1.  **Configuration**: Reads coordinates from `self.get_root_setting` in `__init__`.
            2.  **Concurrency**: Uses `BasePlugin` helpers. `self.run_in_async_task()` launches
                fire-and-forget tasks, while `self.global_loop.create_task()` creates
                the manageable background task, which is explicitly cancelled in `on_stop`.
            3.  **Async I/O**: The blocking `self.requests.get` call is run in a
                separate thread using `await self.asyncio.to_thread(...)` to keep
                the main event loop responsive.
            4.  **Thread Safety**: All GTK UI modifications are safely dispatched
                to the main thread via `self.schedule_in_gtk_thread()`.
            5.  **UI Structure**: Replaced the monolithic `Gtk.Label` with a `Gtk.Grid`.
                This component-based approach isolates individual data points
                (e.g., `self.temp_value_label`) for precise updates and reliable
                tabular alignment, independent of font size or content length.
            6.  **Data Processing**: The `_process_weather_data` method parses the
                API JSON. It extracts the *current* temperature from `timeseries[0]`
                and calculates 24-hour averages by iterating over the first 24
                hourly entries.
            """
            return self.code_explanation.__doc__

    return WeatherPlugin
