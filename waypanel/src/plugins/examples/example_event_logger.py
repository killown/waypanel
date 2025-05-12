from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

# List of all known Wayfire IPC events to subscribe to
ALL_EVENTS = [
    "view-focused",
    "view-unmapped",
    "view-mapped",
    "view-title-changed",
    "view-app-id-changed",
    "view-closed",
    "output-added",
    "output-removed",
    "wset-workspace-changed",
    "workspace-activated",
    "command-binding",
    "plugin-activation-state-changed",
]


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI"""
    return "background"


def initialize_plugin(panel_instance):
    """Initialize the plugin if enabled"""
    if ENABLE_PLUGIN:
        return EventLoggerPlugin(panel_instance)


class EventLoggerPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.subscribe_to_events()

    def subscribe_to_events(self):
        """Subscribe to all Wayfire IPC events"""
        if "event_manager" not in self.obj.plugin_loader.plugins:
            self.logger.error(
                "Event Manager Plugin is not loaded. Cannot subscribe to events."
            )
            return

        event_manager = self.obj.plugin_loader.plugins["event_manager"]

        for event in ALL_EVENTS:
            try:
                event_manager.subscribe_to_event(event, self.handle_event)
                self.logger.info(f"Subscribed to event: {event}")
            except Exception as e:
                self.logger.error(f"Failed to subscribe to event {event}: {e}")

    def handle_event(self, event_data):
        """Handle incoming events from Wayfire IPC"""
        self.logger.info(event_data)
