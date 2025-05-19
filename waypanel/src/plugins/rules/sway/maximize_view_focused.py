from gi.repository import Gtk
from waypanel.src.plugins.core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event

# Set to False or remove the file to disable the plugin
ENABLE_PLUGIN = True

# This plugin depends on the event manager to receive events
DEPS = ["event_manager"]


def get_plugin_placement(panel_instance):
    """
    This is a background plugin with no UI.
    """
    return "background"


def initialize_plugin(panel_instance):
    """
    Initialize the plugin if enabled.
    """
    if ENABLE_PLUGIN:
        return AutoMaximizePlugin(panel_instance)


class AutoMaximizePlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger.info("AutoMaximizePlugin initialized.")

    @subscribe_to_event("view-mapped")
    @subscribe_to_event("view-focused")
    def on_view_focused(self, event_message):
        """
        Handle 'view-focused' event by maximizing the view.

        Args:
            event_message (dict): The event message containing view details.
        """
        try:
            if "view" in event_message:
                view = event_message["view"]
                view_id = view.get("id")

                if not view_id:
                    self.logger.warning("Received evenmd without a valid view ID.")
                    return

                # Use SwayUtils to maximize the view
                success = self.ipc.utils.maximize_view(view_id)

                if success:
                    self.logger.info(f"Maximized view with ID: {view_id}")
                else:
                    self.logger.warning(f"Failed to maximize view with ID: {view_id}")

        except Exception as e:
            self.logger.error(f"Error handling event: {e}")
