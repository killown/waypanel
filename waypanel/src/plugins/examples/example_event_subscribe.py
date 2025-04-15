# ==== FILE: waypanel/src/plugins/taskbar.py ====
# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def position():
    """
    Define the plugin's position and order.

    Since this is a background-only plugin (no UI), return `False`.
    """
    return False  # Background-only plugin


def initialize_plugin(obj, app):
    """Initialize the Taskbar plugin."""
    if ENABLE_PLUGIN:
        print("Initializing Taskbar plugin.")

        # Access the EventManagerPlugin instance
        if "event_manager" not in obj.plugins:
            print(
                "Error: EventManagerPlugin is not loaded. Cannot initialize Taskbar plugin."
            )
            return

        event_manager = obj.plugins["event_manager"]

        # Subscribe to "view-focused" events
        event_manager.subscribe_to_event("view-focused", on_view_focused)

        # Subscribe to "view-created" events
        event_manager.subscribe_to_event("view-created", on_view_created)

        print("Taskbar plugin initialized.")


def on_view_focused(event_message):
    """
    Handle when a view gains focus.

    Args:
        event_message (dict): The event message containing view details.
    """
    view_id = event_message.get("view", {}).get("id")
    print(f"View focused: {view_id}")


def on_view_created(event_message):
    """
    Handle when a view is created.

    Args:
        event_message (dict): The event message containing view details.
    """
    view_id = event_message.get("view", {}).get("id")
    print(f"View created: {view_id}" * 1000)


# ==== END OF FILE: waypanel/src/plugins/taskbar.py ====
