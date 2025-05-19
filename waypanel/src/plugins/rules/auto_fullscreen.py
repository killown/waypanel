"""
Auto Fullscreen App Matcher Plugin for waypanel

This plugin listens for 'view-focused' events and automatically sets views
to fullscreen if their app-id and (optional) title match any defined in the configuration file.
"""

from gi.repository import GLib
from core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event

import logging

ENABLE_PLUGIN = True
DEPS = ["event_manager"]


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return AutoFullscreenAppPlugin(panel_instance)


class AutoFullscreenAppPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger = logging.getLogger("auto_fullscreen_app")
        self.logger.info("AutoFullscreenAppPlugin initialized")

        # Load config
        self.plugin_config = self.config.get("auto_fullscreen_app", {})
        self.match_items = self.plugin_config.get("items", [])
        self.fullscreen_views = {}  # Track which views are fullscreened

    @subscribe_to_event("view-focused")
    def on_view_focused(self, msg):
        view = msg.get("view")
        if not view:
            return

        view_id = view.get("id")
        if not view_id:
            return

        GLib.idle_add(self.fullscreen_if_match, view_id)

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
        GLib.idle_add(self.check_and_update_fullscreen_state, view_id)

    def check_and_update_fullscreen_state(self, view_id):
        try:
            view = self.ipc.get_view(view_id)
            if not view:
                return

            app_id = view.get("app-id", "").lower()
            title = view.get("title", "").lower()

            match_found = False
            for item in self.match_items:
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
                return

            app_id = None
            if "window_properties" in view:
                # SWAY
                app_id = view["window_properties"].get("class", None)
            else:
                app_id = view.get("app-id", "").lower()
            title = view.get("title", "").lower()

            for item in self.match_items:
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
