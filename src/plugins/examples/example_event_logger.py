# List of all known Wayfire IPC events to subscribe to
ALL_EVENTS = [
    # Emitted when a view gains focus (e.g., user clicks or tabs into it)
    # every view event type will have a view key with the following
    # {
    # │   'event': 'view-focused',
    # │   'view': {
    # │   │   'id': 225,
    # │   │   'pid': 47253,
    # │   │   'title': 'nvim',
    # │   │   'app-id': 'kitty',
    # │   │   'base-geometry': {'x': 0, 'y': 43, 'width': 1920, 'height': 1037},
    # │   │   'parent': -1,
    # │   │   'geometry': {'x': 0, 'y': 43, 'width': 1920, 'height': 1037},
    # │   │   'bbox': {'x': 0, 'y': 43, 'width': 1920, 'height': 1037},
    # │   │   'output-id': 1,
    # │   │   'output-name': 'DP-1',
    # │   │   'last-focus-timestamp': 4200257343877,
    # │   │   'role': 'toplevel',
    # │   │   'mapped': True,
    # │   │   'layer': 'workspace',
    # │   │   'tiled-edges': 15,
    # │   │   'fullscreen': False,
    # │   │   'minimized': False,
    # │   │   'activated': True,
    # │   │   'sticky': False,
    # │   │   'wset-index': 1,
    # │   │   'min-size': {'width': 0, 'height': 0},
    # │   │   'max-size': {'width': 0, 'height': 0},
    # │   │   'focusable': True,
    # │   │   'type': 'toplevel'
    # │   }
    # }
    "view-focused",
    # Emitted when a view is unmapped (hidden/closed, but not destroyed yet)
    "view-unmapped",
    # Emitted when a view is mapped (i.e., becomes visible on screen)
    "view-pre-map",
    # Emitted when a view is about to be mapped (i.e, before appear in the screen)
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
    # Emitted when a view is tiled (snapped to a side or maximized in tiling layout)
    "view-tiled",
    # Emitted when a view is minimized (hidden but still exists)
    "view-minimized",
    # Emitted when a view enters fullscreen mode
    "view-fullscreen",
    # Emitted when a view becomes sticky (visible across all workspaces)
    "view-sticky",
    # Emitted when the active workspace set of an output changes
    "wset-workspace-changed",
    # Emitted when a workspace is activated (user switches to it)
    "workspace-activated",
    # Emitted when an output's workspace set (wset) changes
    "output-wset-changed",
    # Emitted when a view's assigned workspace set (wset) changes
    "view-wset-changed",
    # Emitted when a plugin is activated or deactivated
    "plugin-activation-state-changed",
    # Emitted when an output gains input focus (e.g., mouse enters its area)
    # {
    # │   'event': 'output-gain-focus',
    # │   'output': {
    # │   │   'id': 231,
    # │   │   'name': 'DP-2',
    # │   │   'geometry': {'x': 0, 'y': 0, 'width': 2560, 'height': 1080},
    # │   │   'workarea': {'x': 0, 'y': 0, 'width': 2560, 'height': 1080},
    # │   │   'wset-index': 4,
    # │   │   'workspace': {'x': 0, 'y': 0, 'grid_width': 3, 'grid_height': 3}
    # │   }
    # }
    "output-gain-focus",
    # {
    # │   'event': 'output-layout-changed',
    # │   'configuration': [
    # │   │   {
    # │   │   │   'name': 'DP-1',
    # │   │   │   'output-id': 1,
    # │   │   │   'source': 'self',
    # │   │   │   'depth': 8,
    # │   │   │   'scale': 1.0,
    # │   │   │   'vrr': False,
    # │   │   │   'transform': 'normal',
    # │   │   │   'mirror-from': '',
    # │   │   │   'position': {'x': 32765, 'y': 1134464768},
    # │   │   │   'mode': {'width': 1920, 'height': 1080, 'refresh': 165000}
    # │   │   },
    # │   │   {
    # │   │   │   'name': 'DP-2',
    # │   │   │   'output-id': 3,
    # │   │   │   'source': 'dpms',
    # │   │   │   'depth': 8,
    # │   │   │   'scale': 1.0,
    # │   │   │   'vrr': True,
    # │   │   │   'transform': 'normal',
    # │   │   │   'mirror-from': '',
    # │   │   │   'position': {'x': 0, 'y': 0},
    # │   │   │   'mode': {'width': 2560, 'height': 1080, 'refresh': 75000}
    # │   │   }
    # │   ]
    # }
    "output-layout-changed",
    # Emitted when an output is removed
    "output-removed",
]


def get_plugin_metadata(_):
    """
    Define the plugin's properties and placement using the modern dictionary format.
    """
    return {
        "id": "org.waypanel.plugin.example_event_logger",
        "name": "Example Event Logger",
        "version": "1.0.0",
        "enabled": True,
        # background container is used when the plugin loader has no widget to append/set
        "container": "background",
        "index": 0,
        # CRITICAL: Always define dependencies if the current plugin requires certain plugin to be loaded first
        # WARNING: Missing dependencies can cause plugins to fail loading.
        "deps": ["event_manager"],
        "description": "Monitors and logs all Wayfire IPC events for debugging and tracking purposes.",
    }


def get_plugin_class():
    """
    Returns the main plugin class. All necessary imports are deferred here.
    """
    from src.plugins.core._base import BasePlugin

    class EventLoggerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

        def on_start(self):
            """
            Called asynchronously when the plugin is loaded.
            This replaces the deprecated initialize_plugin() function.
            """
            self.subscribe_to_events()

        def subscribe_to_events(self):
            """Subscribe to all Wayfire IPC events"""
            if "event_manager" not in self._panel_instance.plugin_loader.plugins:
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

        def code_explanation(self):
            """
            This plugin acts as a comprehensive event listener for the Wayfire compositor.
            It subscribes to a predefined list of known Inter-Process Communication (IPC)
            events and logs their data.

            Its core logic is centered on **event subscription and passive monitoring**:

            1.  **Event List**: It defines a static list, `ALL_EVENTS`, which contains
                the names of all relevant Wayfire IPC events.
            2.  **Subscription Loop**: In the `subscribe_to_events` method, it iterates
                through this list and uses the `event_manager` to subscribe the
                `handle_event` method as a callback for each event.
            3.  **Event Handling**: The `handle_event` method is a simple but crucial
                callback. When any of the subscribed events occur, the system sends
                the event data to this method, which logs the entire payload.
            4.  **Purpose**: This makes it a valuable background tool for debugging
                and understanding the flow of events within the Wayfire environment,
                without a visible UI.
            """
            return self.code_explanation.__doc__

    return EventLoggerPlugin
