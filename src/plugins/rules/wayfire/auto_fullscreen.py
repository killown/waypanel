def get_plugin_metadata(_):
    about = """
            A background plugin that automatically sets specific windows
            to fullscreen based on their application ID and title, using
            a user-defined configuration.
            """
    return {
        "id": "org.waypanel.plugin.autofullscreen",
        "name": "Auto Fullscreen App",
        "version": "1.0.0",
        "enabled": False,
        "container": "background",
        "deps": ["event_manager"],
        "description": about,
    }


def get_plugin_class():
    import asyncio
    from core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event
    from typing import Dict, List, Any

    class AutoFullscreenAppPlugin(BasePlugin):
        """
        A reactive background service that automatically toggles the fullscreen state
        of windows based on user-defined application ID and title matching rules.
        """

        def __init__(self, panel_instance: Any):
            """
            Initializes the plugin state. Configuration fetching and asynchronous
            setup is deferred to on_start().
            Args:
                panel_instance: The main panel instance.
            """
            super().__init__(panel_instance)
            self.app_ids: List[Dict[str, str]] = []
            self.fullscreen_views: Dict[str, bool] = {}

        async def on_start(self) -> None:
            """
            The primary activation method (replaces old initialization logic).
            Fetches configuration and logs startup.
            """
            self.logger.info("AutoFullscreenAppPlugin initialized and starting up...")
            self.app_ids = self.get_plugin_setting(
                ["plugins", "auto_fullscreen_app", "app_ids"]
            )

        async def on_stop(self) -> None:
            """
            The primary deactivation method.
            Ensures that any window we force-fullscreened is returned to a normal state.
            """
            self.logger.info(
                "AutoFullscreenAppPlugin stopping. Reverting fullscreen views."
            )
            tasks = []
            for view_id in self.fullscreen_views.keys():

                def un_fullscreen(vid):
                    try:
                        self.ipc.set_view_fullscreen(vid, False)
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to un-fullscreen view {vid} on stop: {e}"
                        )

                tasks.append(self.run_in_thread(un_fullscreen, view_id))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self.fullscreen_views.clear()

        @subscribe_to_event("view-focused")
        def on_view_focused(self, msg: Dict[str, Any]) -> None:
            """Schedules fullscreen check when a view gains focus."""
            view = msg.get("view")
            if not view:
                return
            view_id = view.get("id")
            if not view_id:
                return
            self.schedule_in_gtk_thread(self.fullscreen_if_match, view_id)

        @subscribe_to_event("view-title-changed")
        def on_view_title_changed(self, msg: Dict[str, Any]) -> None:
            """Schedules state update when a view's title changes."""
            view = msg.get("view")
            if not view:
                return
            view_id = view.get("id")
            if not view_id:
                return
            self.logger.info(
                f"Title changed for view {view_id}, rechecking fullscreen status..."
            )
            self.schedule_in_gtk_thread(self.check_and_update_fullscreen_state, view_id)

        def check_and_update_fullscreen_state(self, view_id: str) -> None:
            """
            Checks view against rules and restores or exits fullscreen based on title changes.
            This function runs in the GTK thread.
            """
            try:
                view = self.ipc.get_view(view_id)
                if not view:
                    self.fullscreen_views.pop(view_id, None)
                    return
                app_id_raw = view.get("app-id", "").lower()
                if not app_id_raw and view.get("window_properties"):
                    app_id_raw = view["window_properties"].get("class", "").lower()
                title = view.get("title", "").lower()
                match_found = False
                for item in self.app_ids:
                    item_app_id = item.get("app_id", "").lower()
                    item_title = item.get("title", "").lower()
                    if item_app_id != app_id_raw:
                        continue
                    if item_title and item_title not in title:
                        continue
                    match_found = True
                    break
                current_fullscreen = view.get("fullscreen", False)
                if match_found and not current_fullscreen:
                    self.logger.info(f"Restoring fullscreen for view {view_id}")
                    self.ipc.set_view_fullscreen(view_id, True)
                    self.fullscreen_views[view_id] = True
                elif (
                    not match_found
                    and view_id in self.fullscreen_views
                    and current_fullscreen
                ):
                    self.logger.info(
                        f"Exiting fullscreen for view {view_id} (title no longer matches)"
                    )
                    self.ipc.set_view_fullscreen(view_id, False)
                    self.fullscreen_views.pop(view_id, None)
            except Exception as e:
                self.logger.error(f"Error handling title change: {e}")

        def fullscreen_if_match(self, view_id: str):
            """
            Checks view against rules and forces fullscreen if a match is found.
            This function runs in the GTK thread.
            """
            try:
                view = self.ipc.get_view(view_id)
                if not view:
                    return
                app_id_raw = view.get("app-id", "").lower()
                if not app_id_raw and view.get("window_properties"):
                    app_id_raw = view["window_properties"].get("class", "").lower()
                title = view.get("title", "").lower()
                for item in self.app_ids:
                    item_app_id = item.get("app_id", "").lower()
                    item_title = item.get("title", "").lower()
                    if item_app_id != app_id_raw:
                        continue
                    if item_title and item_title not in title:
                        continue
                    if not view.get("fullscreen"):
                        self.logger.info(
                            f"Fullscreening view {view_id} ({app_id_raw}) | Title: '{title}' matches '{item_title}'"
                        )
                        self.ipc.set_view_fullscreen(view_id, True)
                    self.fullscreen_views[view_id] = True
                    return
            except Exception as e:
                self.logger.error(f"Error fullscreening view: {e}")

        def code_explanation(self):
            """
            The core logic of this plugin is a reactive, rule-based
            system that interacts with the window manager. Its key
            principles are:
            1.  **Event-Driven Architecture**: The plugin operates as a
                background service, reacting to two critical events:
                `view-focused` (when a window is selected) and
                `view-title-changed` (for dynamic applications like
                web browsers). This ensures immediate and accurate
                application of rules.
            2.  **Configurable Matching Logic**: The plugin reads a list
                of rules from its configuration. It matches windows by
                their `app-id` and can be optionally refined with a
                partial title match. This flexible, layered approach
                allows for precise control over which windows are
                auto-fullscreened.
            3.  **State Management**: The plugin uses a dictionary to
                track which windows it has put into fullscreen mode.
                This prevents redundant IPC calls to the compositor and
                lays the groundwork for more complex state management,
                such as reverting changes if a window's title no longer
                matches a rule.
            4.  **Inter-Process Communication (IPC)**: The plugin
                orchestrates window state changes without direct
                control. It uses IPC calls to query window properties
                and to send commands to the compositor to set or unset
                a view's fullscreen state.
            """
            return self.code_explanation.__doc__

    return AutoFullscreenAppPlugin
