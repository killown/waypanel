# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def position():
    """
    Define the plugin's position and order.

    Since this is a background-only plugin (no UI), return `False`.
    """
    return "left", 99, 99


def initialize_plugin(panel_instance):
    """
    Initialize the plugin.

    Args:
        obj: The main panel object from panel.py.
        app: The main application instance.
    """
    if not ENABLE_PLUGIN:
        print("Plugin is disabled.")
        return

    # Ensure the EventManagerPlugin is loaded
    if "event_manager" not in panel_instance.plugins:
        print("Error: EventManagerPlugin is not loaded. Cannot subscribe to events.")
        return

    event_manager = panel_instance.plugin_loader.plugins["event_manager"]
    print("Subscribing to events..." * 100)

    # Subscribe to events with callbacks
    try:
        event_manager.subscribe_to_event("view-focused", on_view_focused)
        event_manager.subscribe_to_event("view-mapped", on_view_created)
        print("Successfully subscribed to events.")
    except Exception as e:
        print(f"Error subscribing to events: {e}")


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
