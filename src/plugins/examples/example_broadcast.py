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

        # The main widget must always be set after the main widget container to which we want to append the target_box.
        # The available actions are `append` to append widgets to the top_panel and `set_content`,
        # which is used to set content in other panels such as the left-panel or right-panel.
        # This part of the code is highly important, as the plugin loader strictly requires this metadata.
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

    def about(self):
        """An example plugin that demonstrates how to create a UI widget and broadcast a message via the IPC server."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin is an example demonstrating how to create a simple user
        interface (UI) element and use the Inter-Process Communication (IPC)
        system to broadcast a message to other components.

        The core logic is centered on **event-driven UI and IPC broadcasting**:

        1.  **UI Creation**: It creates a Gtk.Button and sets it as the main
            widget, specifying its placement on the top-right of the panel.
        2.  **Event Handling**: It connects the button's "clicked" signal to the
            `on_button_clicked` method, which logs the click.
        3.  **IPC Broadcasting**: When the button is clicked, it calls the
            asynchronous `broadcast_message` method.
        4.  **Message Payload**: The `broadcast_message` method then uses the
            `ipc_server` to send a predefined message to any other plugin or
            client that is listening for the "custom_message" event.
        """
        return self.code_explanation.__doc__
