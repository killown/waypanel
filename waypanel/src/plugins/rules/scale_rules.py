from gi.repository import GLib
from src.plugins.core.event_handler_decorator import subscribe_to_event

from core._base import BasePlugin

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return WindowRulesPlugin(panel_instance)


class WindowRulesPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

        # Initialize state variables
        self.fullscreen_views = {}

    @subscribe_to_event("plugin-activation-state-changed")
    def handle_scale_event(self, event_message):
        try:
            plugin = event_message.get("plugin")
            state = event_message.get("state")

            if plugin != "scale":
                return

            if state:  # Scale activated
                self.on_scale_activated()
            else:  # Scale deactivated
                self.on_scale_deactivated()

        except Exception as e:
            self.log_error(f"Error handling scale event: {e}")

    def set_focused_view_fullscreen_false(self):
        # the panels will disappear if the focused view is fullscreen
        # set_view_fullscreen False will make it appear then
        # we can restore the original state after scale is deactivated
        focused_view = self.ipc.get_focused_view()

        # Check if the focused view exists and is in fullscreen mode
        if focused_view and focused_view.get("fullscreen"):
            view_id = focused_view["id"]

            # Store the fullscreen state
            self.fullscreen_views[view_id] = True

            # Exit fullscreen
            def run_once():
                self.ipc.set_view_fullscreen(view_id, False)
                return False

            GLib.idle_add(run_once)

    def restore_fullscreen_state(self):
        for view_id, was_fullscreen in list(self.fullscreen_views.items()):
            if was_fullscreen:
                focused_view_id = self.ipc.get_focused_view()["id"]

                # don't restore the state if the focus is not the fullscreen
                if view_id != focused_view_id:
                    self.ipc.set_focus(focused_view_id)
                else:
                    # Restore fullscreen state
                    self.ipc.set_view_fullscreen(view_id, True)

                # Remove from tracking
                del self.fullscreen_views[view_id]

    def on_scale_activated(self):
        try:
            self.set_focused_view_fullscreen_false()
        except Exception as e:
            self.log_error(f"Error handling scale activation: {e}")

    def on_scale_deactivated(self):
        try:
            self.restore_fullscreen_state()
        except Exception as e:
            self.log_error(f"Error handling scale deactivation: {e}")
