def get_plugin_metadata(_):
    about = """
            A plugin that displays the title and icon of the currently
            focused window on the panel with a context menu to open
            the Window Rules manager.
            """
    return {
        "id": "org.waypanel.plugin.window_title",
        "name": "Window Title",
        "version": "1.3.0",
        "enabled": True,
        "index": 1,
        "priority": 970,
        "container": "top-panel-left",
        "deps": [
            "top_panel",
            "event_manager",
            "view_property_controller",
            "css_generator",
        ],
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core.event_handler_decorator import subscribe_to_event
    from src.plugins.core._base import BasePlugin
    from typing import Any, Dict, Optional

    class WindowTitlePlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

        def on_start(self) -> None:
            """Registers the click controller and initial state trackers."""
            self._load_config()
            self.window_title_content = self.gtk.Box()

            self.click_gesture = self.gtk.GestureClick()
            self.click_gesture.set_button(1)
            self.click_gesture.connect("pressed", self._on_left_click)
            self.window_title_content.add_controller(self.click_gesture)

            self.main_widget = (self.window_title_content, "append")
            self.window_title_label = self.gtk.Label()
            self.window_title_icon = self.gtk.Image.new_from_icon_name("None")
            self.window_title_icon.add_css_class("window-title-icon")
            self.window_title_content.append(self.window_title_icon)
            self.window_title_content.append(self.window_title_label)
            self.window_title_content.add_css_class("window-title-content")
            self.window_title_label.add_css_class("window-title-label")

            self._debounce_timer_id: Optional[int] = None
            self._debounce_interval: int = 50
            self._last_view_data: Optional[Dict[str, Any]] = None
            self._last_toplevel_view_focused: Optional[Dict[str, Any]] = None

            first_view = self.ipc.get_focused_view()
            if first_view:
                self.update_title_icon(first_view)

            self.glib.idle_add(self._subscribe_to_events_with_retry)
            self.plugins["css_generator"].install_css("window-title.css")

        def _on_left_click(self, gesture, n_press, x, y):
            """Handles left click to open the rules management menu."""
            view = self._last_toplevel_view_focused
            if not view:
                return

            popover = self.gtk.Popover()
            popover.set_parent(self.window_title_content)

            vbox = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL, spacing=6)
            for m in ["start", "end", "top", "bottom"]:
                getattr(vbox, f"set_margin_{m}")(10)

            # --- Window Rules Integration ---
            rules_plugin = self.plugins.get("org.waypanel.plugin.window_rules")
            if rules_plugin:
                btn_rules = self.gtk.Button(label="Open Window Rules")
                btn_rules.add_css_class("suggested-action")
                btn_rules.connect(
                    "clicked",
                    lambda _: [rules_plugin.open_rules_manager(), popover.popdown()],
                )
                vbox.append(btn_rules)
            else:
                vbox.append(self.gtk.Label(label="Window Rules plugin not found"))

            popover.set_child(vbox)
            popover.popup()

        def _subscribe_to_events_with_retry(self) -> bool:
            """Retries subscription until event_manager is ready."""
            plugin_name = self.__module__.split(".")[-1]
            mgr_id = "org.waypanel.plugin.event_manager"

            if mgr_id not in self.plugins:
                self.glib.timeout_add(100, self._subscribe_to_events_with_retry)
                return self.glib.SOURCE_CONTINUE

            event_manager = self.plugins[mgr_id]
            event_manager.subscribe_to_event(
                "view-focused", self.on_view_focused, plugin_name=plugin_name
            )
            event_manager.subscribe_to_event(
                "view-closed", self.on_view_closed, plugin_name=plugin_name
            )
            event_manager.subscribe_to_event(
                "view-title-changed",
                self.on_view_title_changed,
                plugin_name=plugin_name,
            )
            return self.glib.SOURCE_REMOVE

        def _load_config(self) -> None:
            """Loads window_title specific config."""
            config_data = self.config_handler.config_data.get("window_title", {})
            self.title_length: int = config_data.get("title_length", 30)

        def on_disable(self) -> None:
            """Cleanup operations when the plugin is disabled."""
            if self._debounce_timer_id is not None:
                self.glib.source_remove(self._debounce_timer_id)
            self.clear_widget()

        @subscribe_to_event("view-focused")
        def on_view_focused(self, event_message: Dict[str, Any]) -> None:
            try:
                view = event_message.get("view")
                if view:
                    if view.get("role") == "toplevel":
                        self._last_toplevel_view_focused = view
                    self.update_title_icon_debounced(view)
            except Exception as e:
                self.logger.error(f"Error handling 'view-focused' event: {e}")

        @subscribe_to_event("view-closed")
        def on_view_closed(self, event_message: Dict[str, Any]) -> None:
            try:
                view_id = event_message.get("view", {}).get("id")
                if self._last_view_data and view_id == self._last_view_data.get("id"):
                    self.clear_widget()
                if (
                    self._last_toplevel_view_focused
                    and view_id == self._last_toplevel_view_focused.get("id")
                ):
                    self._last_toplevel_view_focused = None
            except Exception as e:
                self.logger.error(f"Error handling 'view-closed' event: {e}")

        @subscribe_to_event("view-title-changed")
        def on_view_title_changed(self, event_message: Dict[str, Any]) -> None:
            try:
                view = event_message.get("view")
                if view:
                    self.update_title_icon_debounced(view)
            except Exception as e:
                self.logger.error(f"Error handling 'view-title-changed' event: {e}")

        def sway_translate_ipc(self, view: Dict[str, Any]) -> Dict[str, Any]:
            """Translates Wayland-specific keys for compatibility."""
            v = view.copy()
            v["app-id"] = view.get("app_id")
            v["title"] = view.get("name")
            return v

        def update_title_icon_debounced(self, view: Dict[str, Any]) -> None:
            """Debounce updates to prevent excessive calls."""
            self._last_view_data = view
            if self._debounce_timer_id is not None:
                self.glib.source_remove(self._debounce_timer_id)
            self._debounce_timer_id = self.glib.timeout_add(
                self._debounce_interval, self._perform_debounced_update
            )

        def _perform_debounced_update(self) -> bool:
            """Internal method to perform UI update after debounce."""
            self._debounce_timer_id = None
            if self._last_view_data:
                self.update_title_icon(self._last_view_data)
            return self.glib.SOURCE_REMOVE

        def update_title_icon(self, view: Optional[Dict[str, Any]]) -> None:
            """Update the title and icon based on the focused view."""
            try:
                if not view:
                    return
                if view.get("app_id") is not None:
                    view = self.sway_translate_ipc(view)
                if self.compositor == "wayfire":
                    view = self.is_view_valid(view)
                if not view:
                    return
                title: str = self.filter_title(view.get("title", ""))
                app_id: Optional[str] = None
                if view.get("window_properties"):
                    app_id = view.get("window_properties", {}).get("class")
                else:
                    app_id = view.get("app-id", "").lower()
                if app_id:
                    icon_name = self.ipc.get_view_property(view.get("id"), "icon")
                    if icon_name:
                        self.update_title(title, icon_name)
            except Exception as e:
                self.logger.error(f"Error updating title/icon: {e}")
                self.clear_widget()

        def filter_title(self, title: str) -> str:
            """Filter and shorten the title."""
            if not title:
                return ""
            title = self.gtk_helper.filter_utf_for_gtk(title)
            MAX_WORD_LENGTH = 20
            MAX_TITLE_LENGTH = self.title_length
            if " — " in title:
                title = title.split(" — ")[0].strip()
            words = title.split()
            shortened_words = []
            for word in words:
                if len(word) > MAX_WORD_LENGTH:
                    word = word[:MAX_WORD_LENGTH] + "…"
                shortened_words.append(word)
            title = " ".join(shortened_words)
            if len(title) > MAX_TITLE_LENGTH:
                title = title[: MAX_TITLE_LENGTH - 1] + "…"
            return title

        def update_title(self, title: str, icon_name: str) -> None:
            """Update the window title widget with new title and icon."""
            try:
                self.window_title_label.set_label(title)
                icon_to_set = icon_name if icon_name else "None"
                self.window_title_icon.set_from_icon_name(icon_to_set)
                if title:
                    self.window_title_content.add_css_class("title-active")
                else:
                    self.safe_remove_css_class(
                        self.window_title_content, "title-active"
                    )
            except Exception as e:
                self.logger.error(f"Error updating window title widget: {e}")

        def clear_widget(self) -> None:
            """Clear the widget when no view is focused."""
            self.update_title("", "None")
            self._last_view_data = None

    return WindowTitlePlugin
