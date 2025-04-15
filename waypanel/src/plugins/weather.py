import requests
from gi.repository import Gtk, GLib

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def position():
    """Define the plugin's position and order."""
    position = "center"  # Center-aligned in the panel
    order = 6  # Priority order (adjust as needed)
    return position, order


def initialize_plugin(obj, app):
    """Initialize the weather plugin."""
    if ENABLE_PLUGIN:
        weather_plugin = WeatherPlugin(obj, app)
        weather_plugin.create_weather_widget()


class WeatherPlugin:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app
        self.weather_label = None
        self.update_interval = 3600  # Update every hour (in seconds)

    def create_weather_widget(self):
        """Create and setup the weather widget."""
        # Create a horizontal box container for the weather label
        self.weather_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.weather_box.set_halign(Gtk.Align.CENTER)
        self.weather_box.add_css_class("weather-box")

        # Create the weather label
        self.weather_label = Gtk.Label()
        self.weather_label.add_css_class("weather-label")
        self.weather_label.set_text("Loading...")  # Initial placeholder text

        # Add the label to the box
        self.weather_box.append(self.weather_label)

        # Add the weather box to the center panel
        self.obj.top_panel_box_center.append(self.weather_box)

        # Fetch and update the weather data, no idle_add will hang the code until the data is fetched
        def run_once():
            self.fetch_and_update_weather()
            return False

        GLib.idle_add(run_once)

        # Schedule periodic updates
        GLib.timeout_add_seconds(self.update_interval, self.fetch_and_update_weather)

    def fetch_and_update_weather(self):
        """Fetch weather data and update the label."""
        try:
            # Coordinates for São Paulo
            lat, lon = -23.5505, -46.6333
            url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"

            headers = {
                "User-Agent": "MyWeatherApp/1.0 youremail@example.com"  # Required by met.no
            }

            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = response.json()

            # Extract current temperature
            timeseries = data["properties"]["timeseries"][0]
            instant_details = timeseries["data"]["instant"]["details"]
            temperature = instant_details["air_temperature"]

            # Update the label with the temperature value
            GLib.idle_add(self.weather_label.set_text, f"{temperature}°C")
        except Exception as e:
            # Handle errors gracefully
            GLib.idle_add(self.weather_label.set_text, "Error")
            print(f"Failed to fetch weather data: {e}")

        # Return True to keep the timeout active
        return True
