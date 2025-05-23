from src.plugins.core.event_handler_decorator import subscribe_to_event

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["event_manager"]

# List of all known Wayfire IPC events to subscribe to
ALL_EVENTS = [
    "view-focused",
    "view-unmapped",
    "view-mapped",
    "view-title-changed",
    "view-app-id-changed",
    "view-set-output",
    "view-workspace-changed",
    "view-geometry-changed",
    "wset-workspace-changed",
    "workspace-activated",
    "plugin-activation-state-changed",
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
