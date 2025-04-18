import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "center"
    order = 0
    priority = 1
    return position, order, priority


def initialize_plugin(obj, app):
    """Initialize the Plugin Communicator."""
    if ENABLE_PLUGIN:
        print("Initializing Plugin Communicator.")
        communicator = PluginCommunicator(obj, app)
        communicator.create_ui()
        print("Plugin Communicator initialized.")


class PluginCommunicator:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app

    def create_ui(self):
        """Create UI elements for the Plugin Communicator."""
        # Create a button to interact with Clock Calendar Plugin
        self.clock_button = Gtk.Button(label="Get Time")
        self.clock_button.connect("clicked", self.get_current_time)

        # Create a button to interact with Volume Scroll Plugin
        self.volume_button = Gtk.Button(label="Get Volume")
        self.volume_button.connect("clicked", self.get_current_volume)

        # Add buttons to the panel
        if hasattr(self.obj, "top_panel_box_for_buttons"):
            self.obj.top_panel_box_for_buttons.append(self.clock_button)
            self.obj.top_panel_box_for_buttons.append(self.volume_button)

    def get_current_time(self, widget):
        """Get current time from clock_calendar_plugin."""
        if "clock" in self.obj.plugins:
            clock_plugin = self.obj.plugins["clock"]
            try:
                current_time = clock_plugin.clock_label.get_text()
                print(f"Current Time: {current_time}")
            except Exception as e:
                print(e)
        else:
            print("clock plugin is not loaded")

    def get_current_volume(self, widget):
        """Get current volume from volume_scroll_plugin."""
        if "volume_scroll" in self.obj.plugins:
            volume_plugin = self.obj.plugins["volume_scroll"]
            try:
                max_volume = volume_plugin.max_volume
                print(f"Max Volume: {max_volume}")
            except AttributeError:
                print("volume_scroll plugin does not have current_volume property")
        else:
            print("volume scroll plugin is not loaded")
