ENABLE_PLUGIN = False
DEPS = ["event_manager"]


def get_plugin_metadata(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        auto_fs = get_plugin_class()
        return auto_fs(panel_instance)


def get_plugin_class():
    from core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event

    class AutoFullscreenAppPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.logger.info("AutoFullscreenAppPlugin initialized")
            self.app_ids = self.get_config(
                ["plugins", "auto_fullscreen_app", "app_ids"]
            )
            self.fullscreen_views = {}

        @subscribe_to_event("view-focused")
        def on_view_focused(self, msg):
            view = msg.get("view")
            if not view:
                return
            view_id = view.get("id")
            if not view_id:
                return
            self.schedule_in_gtk_thread(self.fullscreen_if_match, view_id)

        @subscribe_to_event("view-title-changed")
        def on_view_title_changed(self, msg):
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

        def check_and_update_fullscreen_state(self, view_id):
            try:
                view = self.ipc.get_view(view_id)
                if not view:
                    return False
                app_id = view.get("app-id", "").lower()
                title = view.get("title", "").lower()
                match_found = False
                for item in self.app_ids:
                    item_app_id = item.get("app_id", "").lower()
                    item_title = item.get("title", "").lower()
                    if item_app_id != app_id:
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
                elif not match_found and current_fullscreen:
                    self.logger.info(
                        f"Exiting fullscreen for view {view_id} (title no longer matches)"
                    )
                    self.ipc.set_view_fullscreen(view_id, False)
                    self.fullscreen_views.pop(view_id, None)
            except Exception as e:
                self.logger.error(f"Error handling title change: {e}")

        def fullscreen_if_match(self, view_id):
            try:
                view = self.ipc.get_view(view_id)
                if not view:
                    return False
                app_id = None
                if "window_properties" in view:
                    app_id = view["window_properties"].get("class", None)
                else:
                    app_id = view.get("app-id", "").lower()
                title = view.get("title", "").lower()
                for item in self.app_ids:
                    item_app_id = item.get("app_id", "").lower()
                    item_title = item.get("title", "").lower()
                    if item_app_id != app_id:
                        continue
                    if item_title and item_title not in title:
                        continue
                    if not view.get("fullscreen"):
                        self.logger.info(
                            f"Fullscreening view {view_id} ({app_id}) | Title: '{title}' matches '{item_title}'"
                        )
                        self.ipc.set_view_fullscreen(view_id, True)
                        self.fullscreen_views[view_id] = True
                    else:
                        self.fullscreen_views[view_id] = True
                    break
            except Exception as e:
                self.logger.error(f"Error fullscreening view: {e}")

        def about(self):
            """
            A background plugin that automatically sets specific windows
            to fullscreen based on their application ID and title, using
            a user-defined configuration.
            """
            return self.about.__doc__

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
