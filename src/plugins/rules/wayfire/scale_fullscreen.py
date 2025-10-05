ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        window_rules = call_plugin_class()
        return window_rules(panel_instance)


def call_plugin_class():
    from src.plugins.core.event_handler_decorator import subscribe_to_event
    from core._base import BasePlugin

    class WindowRulesPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.fullscreen_views = {}

        @subscribe_to_event("plugin-activation-state-changed")
        def handle_scale_event(self, event_message):
            try:
                plugin = event_message.get("plugin")
                state = event_message.get("state")
                if plugin != "scale":
                    return
                if state:
                    self.on_scale_activated()
                else:
                    self.on_scale_deactivated()
            except Exception as e:
                self.logger.error(f"Error handling scale event: {e}")

        def set_focused_view_fullscreen_false(self):
            focused_view = self.ipc.get_focused_view()
            if focused_view and focused_view.get("fullscreen"):
                if self.obj.display["id"] == self.ipc.get_focused_output()["id"]:
                    view_id = focused_view["id"]
                    self.fullscreen_views[view_id] = True

                    def run_once():
                        self.ipc.set_view_fullscreen(view_id, False)
                        return False

                    self.glib.idle_add(run_once)

        def restore_fullscreen_state(self):
            for view_id, was_fullscreen in list(self.fullscreen_views.items()):
                if was_fullscreen:
                    focused_view_id = self.ipc.get_focused_view()["id"]
                    if view_id != focused_view_id:
                        self.ipc.set_focus(focused_view_id)
                    else:
                        self.ipc.set_view_fullscreen(view_id, True)
                    del self.fullscreen_views[view_id]

        def on_scale_activated(self):
            try:
                self.set_focused_view_fullscreen_false()
            except Exception as e:
                self.logger.error(f"Error handling scale activation: {e}")

        def on_scale_deactivated(self):
            try:
                self.restore_fullscreen_state()
            except Exception as e:
                self.logger.error(f"Error handling scale deactivation: {e}")

        def about(self):
            """
            A background plugin that manages window states to prevent
            the Wayland panel from being hidden by fullscreen windows
            when a window overview feature is activated.
            """
            return self.about.__doc__

        def code_explanation(self):
            """
            The core logic of this plugin is a reactive, event-driven
            architecture that temporarily manages window states. Its
            key principles are:
            1.  **Event-Driven Triggering**: The plugin operates as a
                background service, listening for changes in the `scale`
                plugin's activation state via an event subscription.
                This allows it to react instantly and without polling.
            2.  **Temporary State Management**: When the `scale` view is
                activated, the plugin identifies if the currently focused
                window is in fullscreen mode. It then stores this state
                in a dictionary (`self.fullscreen_views`) before using
                Inter-Process Communication (IPC) to temporarily take the
                window out of fullscreen.
            3.  **State Restoration**: When the `scale` view is
                deactivated, the plugin iterates through its stored state.
                For each window that was previously in fullscreen, it uses
                an IPC call to restore its original state, ensuring a
                seamless user experience once the overview is dismissed.
            """
            return self.code_explanation.__doc__

    return WindowRulesPlugin
