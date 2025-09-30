from src.plugins.core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event

# FIX: Incorrect Behavior of Fullscreen Views During Cross-Monitor Drag-and-Drop
# https://github.com/WayfireWM/wayfire/issues/2635https://github.com/WayfireWM/wayfire/issues/2635

ENABLE_PLUGIN = True

DEPS = ["event_manager"]


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    """Initialize the plugin if enabled."""
    if ENABLE_PLUGIN:
        return FixFullscreenDragDropPlugin(panel_instance)
    return None


class FixFullscreenDragDropPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """Initialize the FixFullscreenDragDropPlugin."""
        self.logger.info("FixFullscreenDragDropPlugin initialized.")
        self.schedule_in_gtk_thread(self.subscribe_to_events)

    def subscribe_to_events(self):
        """Subscribe to relevant events."""
        event_manager = self.plugins["event_manager"]
        event_manager.subscribe_to_event(
            "plugin-activation-state-changed", self.handle_plugin_event
        )

    @subscribe_to_event("plugin-activation-state-changed")
    def handle_plugin_event(self, msg):
        """Handle plugin activation state changes."""
        try:
            if msg["plugin"] == "move" and msg["state"] is False:
                view = self.ipc.get_focused_view()
                if view and view.get("fullscreen"):
                    focused_output = self.ipc.get_focused_output()
                    if focused_output:
                        width = focused_output["geometry"]["width"]
                        height = focused_output["geometry"]["height"]
                        self.ipc.configure_view(view["id"], 0, 0, width, height)
        except Exception as e:
            self.logger.error(f"Error handling plugin event: {e}")
