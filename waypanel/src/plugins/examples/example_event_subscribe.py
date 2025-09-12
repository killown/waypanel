from src.plugins.core.event_handler_decorator import subscribe_to_event

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["event_manager"]

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


def get_plugin_placement(panel_instance):
    """Background plugin"""
    # just return, do not use None or None, None
    return


def initialize_plugin(panel_instance):
    """
    Initialize the plugin.

    Args:
        obj: The main panel object from panel.py.
        app: The main application instance.
    """
    if not ENABLE_PLUGIN:
        panel_instance.logger.info("Plugin is disabled.")
        return


@subscribe_to_event("view-focused")
def on_view_focused(event_message):
    """
    Handle when a view gains focus.

    Args:
        event_message (dict): The event message containing view details.
    """
    try:
        if "view" in event_message and event_message["view"] is not None:
            view_id = event_message["view"].get("id")
            print(f"View focused id: {view_id}")
    except Exception as e:
        print(f"Error handling 'view-focused' event: {e}")


@subscribe_to_event("view-mapped")
def on_view_created(event_message):
    """
    Handle when a view is created.

    Args:
        event_message (dict): The event message containing view details.
    """
    try:
        view_id = event_message.get("view", {}).get("id")
        print(f"View created: {view_id}")
    except Exception as e:
        print(f"Error handling 'view-created' event: {e}")
