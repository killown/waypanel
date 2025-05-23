from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

# List of all known Wayfire IPC events to subscribe to
ALL_EVENTS = [
    # Emitted when a view gains focus (e.g., user clicks or tabs into it)
    "view-focused",
    # Emitted when a view is unmapped (hidden/closed, but not destroyed yet)
    "view-unmapped",
    # Emitted when a view is mapped (i.e., becomes visible on screen)
    "view-mapped",
    # Emitted when the title of a view changes (e.g., browser tab changes title)
    "view-title-changed",
    # Emitted when the application ID (app_id) of a view changes
    "view-app-id-changed",
    # Emitted when a view is moved to a different output (monitor)
    "view-set-output",
    # Emitted when a view moves from one workspace to another
    "view-workspace-changed",
    # Emitted when the geometry (position and size) of a view changes
    "view-geometry-changed",
    # Emitted when the active workspace set of an output changes
    "wset-workspace-changed",
    # Emitted when a workspace is activated (user switches to it)
    "workspace-activated",
    # Emitted when a plugin is activated or deactivated
    "plugin-activation-state-changed",
    # Emitted when an output gains input focus (e.g., mouse enters its area)
    "output-gain-focus",
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
