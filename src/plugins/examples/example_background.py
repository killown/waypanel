def get_plugin_metadata(_):
    """
    Define the plugin's properties and placement using the modern dictionary format.

    Valid Positions:
        - Top Panel:
            "top-panel-left"
            "top-panel-center"
            "top-panel-right"
            "top-panel-systray"
            "top-panel-after-systray"

        - Bottom Panel:
            "bottom-panel-left"
            "bottom-panel-center"
            "bottom-panel-right"

        - Left Panel:
            "left-panel-top"
            "left-panel-center"
            "left-panel-bottom"

        - Right Panel:
            "right-panel-top"
            "right-panel-center"
            "right-panel-bottom"

        - Background:
            "background"  # For plugins that don't have a UI

    Returns:
        dict: Plugin configuration metadata.
    """
    return {
        "id": "org.waypanel.plugin.example_background",
        "name": "Example Background Plugin",
        "version": "1.0.0",
        "enabled": True,
        "container": "top-panel-right",
        "index": 5,
        "deps": ["event_manager"],
        "description": "An example plugin that demonstrates how to create a UI widget and broadcast a message via the IPC server.",
    }


def get_plugin_class():
    """
    Returns the main plugin class. All necessary imports are deferred here.
    """
    import asyncio
    from src.plugins.core._base import BasePlugin

    class ExampleBroadcastPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.button = None

        def on_start(self):
            """
            Asynchronous entry point, replacing the deprecated initialize_plugin().
            """
            self.logger.info("Setting up ExampleBroadcastPlugin...")
            self._setup_plugin_ui()
            self.logger.info("ExampleBroadcastPlugin has started.")

        def _setup_plugin_ui(self):
            """
            Set up the plugin's UI and functionality.
            """
            self.button = self.create_broadcast_button()
            self.main_widget = (self.button, "append")

        def create_broadcast_button(self):
            """
            Create a button that triggers an IPC broadcast when clicked.
            """
            # Use self.gtk helper for widget creation
            button = self.gtk.Button()
            button.connect("clicked", self.on_button_clicked)
            button.set_tooltip_text("Click to broadcast a message!")
            return button

        def on_button_clicked(self, widget):
            """
            Handle button click event by correctly scheduling the async broadcast.
            """
            self.logger.info("ExampleBroadcastPlugin button clicked!")

            message = {
                "event": "custom_message",
                "data": "Hello from ExampleBroadcastPlugin!",
            }

            asyncio.create_task(self.broadcast_message(message))

        async def broadcast_message(self, message):
            """
            Broadcast a custom message to all connected clients via the IPC server.
            """
            try:
                self.logger.info(f"Broadcasting message: {message}")
                await self.ipc_server.broadcast_message(message)
            except Exception as e:
                self.logger.error(f"Failed to broadcast message: {e}")

        async def on_stop(self):
            """
            Called when the plugin is stopped or unloaded.
            """
            self.logger.info("ExampleBroadcastPlugin has stopped.")

        async def on_reload(self):
            """
            Called when the plugin is reloaded dynamically.
            """
            self.logger.info("ExampleBroadcastPlugin has been reloaded.")

        async def on_cleanup(self):
            """
            Called before the plugin is completely removed.
            """
            self.logger.info("ExampleBroadcastPlugin is cleaning up resources.")

        def code_explanation(self):
            """
            This plugin is an example demonstrating how to create a simple user
            interface (UI) element and use the Inter-Process Communication (IPC)
            system to broadcast a message to other components.

            The core logic is centered on **event-driven UI and IPC broadcasting**:

            1.  **UI Creation**: It creates a Gtk.Button and sets it as the main
                widget, specifying its placement on the top-right of the panel.
            2.  **Event Handling**: It connects the button's "clicked" signal to the
                `on_button_clicked` method, which correctly schedules the
                asynchronous `broadcast_message` using `asyncio.create_task`.
            3.  **IPC Broadcasting**: The `broadcast_message` method then uses the
                `ipc_server` to send a predefined message to any other plugin or
                client that is listening for the "custom_message" event.
            """
            return self.code_explanation.__doc__

    return ExampleBroadcastPlugin
