from src.plugins.core.event_handler_decorator import subscribe_to_event

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["event_manager"]

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
    "output-gain-focus",
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
