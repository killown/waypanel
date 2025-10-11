def get_plugin_metadata(_):
    about = """
            A background plugin that manages window states to prevent
            the Wayland panel from being hidden by fullscreen windows
            when a window overview feature is activated (e.g., the 'scale' plugin).
            It temporarily un-fullscreens the focused window and restores it upon
            deactivation of the associated feature.
            """
    return {
        "id": "org.waypanel.plugin.windowrules",
        "name": "Window Rules",
        "version": "1.0.0",
        "enabled": True,
        "container": "background",
        "deps": ["event_manager"],
        "description": about,
    }


def get_plugin_class():
    """
    The factory function for the WindowRulesPlugin class.
    All necessary imports are deferred here to ensure fast top-level loading.
    """
    import asyncio
    from core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event
    from typing import Dict, Any

    class WindowRulesPlugin(BasePlugin):
        """
        A reactive background service that temporarily un-fullscreens the focused
        window upon activation of a window overview feature (like 'scale') and
        restores it upon deactivation.
        """

        def __init__(self, panel_instance: Any):
            """
            Initializes the plugin state. Lifecycle methods on_start and on_stop
            handle activation/deactivation logic.
            Args:
                panel_instance: The main panel instance.
            """
            super().__init__(panel_instance)
            self.fullscreen_views: Dict[str, bool] = {}

        async def on_start(self) -> None:
            """Logs plugin startup. All event subscriptions are handled by decorators."""
            self.logger.info("WindowRulesPlugin initialized and started.")

        async def on_stop(self) -> None:
            """
            The primary deactivation method. Ensures any window we tracked as
            fullscreen is returned to its original state.
            """
            self.logger.info(
                "WindowRulesPlugin stopping. Restoring saved fullscreen states."
            )
            tasks = []
            views_to_restore = list(self.fullscreen_views.keys())
            for view_id in views_to_restore:
                if self.fullscreen_views.get(view_id):

                    def restore_view_state(vid: str):
                        try:
                            self.ipc.set_view_fullscreen(vid, True)
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to restore fullscreen for view {vid} on stop: {e}"
                            )
                        finally:
                            self.fullscreen_views.pop(vid, None)

                    tasks.append(self.run_in_thread(restore_view_state, view_id))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self.fullscreen_views.clear()

        @subscribe_to_event("plugin-activation-state-changed")
        def handle_scale_event(self, event_message: Dict[str, Any]) -> None:
            """
            Handles the activation/deactivation event of the 'scale' plugin
            to trigger fullscreen state changes.
            """
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

        def set_focused_view_fullscreen_false(self) -> None:
            """
            Temporarily unsets fullscreen on the focused view and records its state
            for later restoration.
            """
            focused_view = self.ipc.get_focused_view()
            if focused_view and focused_view.get("fullscreen"):
                focused_output = self.ipc.get_focused_output()
                if self.obj.display and self.obj.display.get(
                    "id"
                ) == focused_output.get("id"):
                    view_id = focused_view["id"]
                    self.fullscreen_views[view_id] = True

                    def run_once():
                        """Runs the IPC call in the GTK main thread."""
                        try:
                            self.ipc.set_view_fullscreen(view_id, False)
                        except Exception as e:
                            self.logger.warning(
                                f"Error un-fullscreening view {view_id}: {e}"
                            )
                        return False

                    self.glib.idle_add(run_once)

        def restore_fullscreen_state(self) -> None:
            """
            Restores the fullscreen state for views that were temporarily un-fullscreened.
            """
            for view_id, was_fullscreen in list(self.fullscreen_views.items()):
                if was_fullscreen:
                    try:
                        focused_view = self.ipc.get_focused_view()
                        focused_view_id = (
                            focused_view.get("id") if focused_view else None
                        )
                        if view_id != focused_view_id:
                            self.ipc.set_focus(focused_view_id)
                        else:
                            self.ipc.set_view_fullscreen(view_id, True)
                    except Exception as e:
                        self.logger.error(
                            f"Error restoring fullscreen/focus for view {view_id}: {e}"
                        )
                    del self.fullscreen_views[view_id]

        def on_scale_activated(self) -> None:
            """Action taken when the 'scale' plugin is activated."""
            try:
                self.set_focused_view_fullscreen_false()
            except Exception as e:
                self.logger.error(f"Error handling scale activation: {e}")

        def on_scale_deactivated(self) -> None:
            """Action taken when the 'scale' plugin is deactivated."""
            try:
                self.restore_fullscreen_state()
            except Exception as e:
                self.logger.error(f"Error handling scale deactivation: {e}")

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
                and uses a `self.glib.idle_add` function call to synchronously
                request the compositor to unset the fullscreen state, allowing
                the window overview (scale) to function correctly.
            3.  **Restoration on Deactivation**: When the `scale` view is
                deactivated, the plugin restores the saved fullscreen state
                using the `self.fullscreen_views` dictionary, ensuring the
                user's environment returns to its previous state.
            4.  **Inter-Process Communication (IPC)**: The plugin
                orchestrates window state changes using `self.ipc` to interact
                with the Wayland compositor.
            """
            return self.code_explanation.__doc__

    return WindowRulesPlugin
