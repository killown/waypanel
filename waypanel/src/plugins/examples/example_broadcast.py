import asyncio
from gi.repository import Gtk
from src.plugins.core._base import BasePlugin


# Enable or disable the plugin
ENABLE_PLUGIN = True

# Define plugin dependencies (if any)
DEPS = ["event_manager"]  # No additional dependencies required


def get_plugin_placement(panel_instance):
    """
    Define the plugin's position and order in the panel.
    """
    position = "top-panel-right"  # Position in the panel
    order = 5  # Order relative to other plugins
    return position, order


def initialize_plugin(panel_instance):
    """
    Initialize the plugin and return its instance.
    Args:
        panel_instance: The main panel object from panel.py.
    """
    if not ENABLE_PLUGIN:
        panel_instance.logger.info("ExampleBroadcastPlugin is disabled.")
        return None

    # Create and return the plugin instance
    plugin = ExampleBroadcastPlugin(panel_instance)
    plugin.setup_plugin()
    return plugin


class ExampleBroadcastPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """
        Initialize the plugin.
        """
        pass

    def setup_plugin(self):
        """
        Set up the plugin's UI and functionality.
        """
        self.logger.info("Setting up ExampleBroadcastPlugin...")

        # Create a button widget
        self.button = self.create_broadcast_button()

        # Define the main widget for the plugin
        self.main_widget = (self.button, "append")  # Add the button to the panel

    def create_broadcast_button(self):
        """
        Create a button that triggers an IPC broadcast when clicked.
        """
        button = Gtk.Button()
        button.connect("clicked", self.on_button_clicked)
        button.set_tooltip_text("Click to broadcast a message!")
        return button

    def on_button_clicked(self, widget):
        """
        Handle button click event.
        """
        self.logger.info("ExampleBroadcastPlugin button clicked!")

        # Define a custom message to broadcast
        message = {
            "event": "custom_message",
            "data": "Hello from ExampleBroadcastPlugin!",
        }

        # Broadcast the message using the IPC server
        asyncio.run(self.broadcast_message(message))

    async def broadcast_message(self, message):
        """
        Broadcast a custom message to all connected clients via the IPC server.
        Args:
            message (dict): The message to broadcast.
        """
        try:
            self.logger.info(f"Broadcasting message: {message}")
            await self.ipc_server.broadcast_message(message)
        except Exception as e:
            self.logger.error(f"Failed to broadcast message: {e}")

    def on_start(self):
        """
        Called when the plugin is started.
        """
        self.logger.info("ExampleBroadcastPlugin has started.")

    def on_stop(self):
        """
        Called when the plugin is stopped or unloaded.
        """
        self.logger.info("ExampleBroadcastPlugin has stopped.")

    def on_reload(self):
        """
        Called when the plugin is reloaded dynamically.
        """
        self.logger.info("ExampleBroadcastPlugin has been reloaded.")

    def on_cleanup(self):
        """
        Called before the plugin is completely removed.
        """
        self.logger.info("ExampleBroadcastPlugin is cleaning up resources.")
