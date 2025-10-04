from gi.repository import Gtk, GLib  # pyright: ignore
from src.plugins.core.event_handler_decorator import subscribe_to_event
from src.plugins.core._base import BasePlugin
from typing import Any, Dict, Optional

ENABLE_PLUGIN = True
DEPS = ["top_panel", "event_manager"]


def initialize_plugin(panel_instance) -> "WindowTitlePlugin":
    """
    Initialize the plugin.
    """
    return WindowTitlePlugin(panel_instance)


def get_plugin_placement(panel_instance) -> tuple[str, int]:
    """
    Define the plugin's position and order.
    Returns:
        tuple: (position, order)
    """
    position = "top-panel-left"
    order = 5
    return position, order


class WindowTitlePlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """
        Initialize the Window Title plugin.
        """
        pass

    def on_start(self) -> None:
        """
        Hook for when plugin is loaded. Used to defer event subscription until
        the EventManagerPlugin is guaranteed to be loaded.
        """
        self._load_config()
        self.window_title_content = Gtk.Box()
        self.main_widget = (self.window_title_content, "append")
        self.window_title_label = Gtk.Label()
        self.window_title_icon = Gtk.Image.new_from_icon_name("None")
        self.window_title_icon.add_css_class("window-title-icon")
        self.window_title_content.append(self.window_title_icon)
        self.window_title_content.append(self.window_title_label)
        self.window_title_content.add_css_class("window-title-content")
        self.window_title_label.add_css_class("window-title-label")
        self._debounce_timer_id: Optional[int] = None
        self._debounce_interval: int = 50
        self._last_view_data: Optional[Dict[str, Any]] = None
        first_title_update_from_focused_view = self.ipc.get_focused_view()
        if first_title_update_from_focused_view:
            self.update_title_icon(first_title_update_from_focused_view)
        GLib.idle_add(self._subscribe_to_events_with_retry)

    def _subscribe_to_events_with_retry(self) -> bool:
        """
        Implements the retry logic to manually subscribe to events only when the
        'event_manager' plugin is fully loaded, ensuring the callbacks work.
        Returns:
            bool: GLib.SOURCE_CONTINUE (True) to retry, GLib.SOURCE_REMOVE (False) to stop.
        """
        plugin_name = self.__module__.split(".")[-1]
        if "event_manager" not in self._panel_instance.plugin_loader.plugins:
            self.logger.debug(f"{plugin_name} is waiting for EventManagerPlugin.")
            GLib.timeout_add(100, self._subscribe_to_events_with_retry)
            return GLib.SOURCE_CONTINUE
        event_manager = self._panel_instance.plugin_loader.plugins["event_manager"]
        self.logger.info(f"Subscribing to events for {plugin_name} Plugin (deferred).")
        event_manager.subscribe_to_event(
            "view-focused",
            self.on_view_focused,
            plugin_name=plugin_name,
        )
        event_manager.subscribe_to_event(
            "view-closed",
            self.on_view_closed,
            plugin_name=plugin_name,
        )
        event_manager.subscribe_to_event(
            "view-title-changed",
            self.on_view_title_changed,
            plugin_name=plugin_name,
        )
        return GLib.SOURCE_REMOVE

    def _load_config(self) -> None:
        """Loads configuration from config_handler with defaults."""
        config_data = self.config_handler.config_data.get("window_title", {})
        self.title_length: int = config_data.get("title_length", 50)
        self.logger.debug(f"Loaded title_length: {self.title_length}")

    def on_disable(self) -> None:
        """
        Hook for when plugin is disabled. Cleans up GLib timer.
        BasePlugin.disable() will handle self.main_widget removal.
        """
        if self._debounce_timer_id is not None:
            GLib.source_remove(self._debounce_timer_id)
            self._debounce_timer_id = None
            self.logger.debug("Debounce timer stopped.")
        self.clear_widget()

    @subscribe_to_event("view-focused")
    def on_view_focused(self, event_message: Dict[str, Any]) -> None:
        """
        Handle when a view gains focus.
        """
        try:
            view = event_message.get("view")
            if view:
                self.update_title_icon_debounced(view)
        except Exception as e:
            self.logger.error(f"Error handling 'view-focused' event: {e}")

    @subscribe_to_event("view-closed")
    def on_view_closed(self, event_message: Dict[str, Any]) -> None:
        """
        Handle when a view is closed.
        """
        try:
            if self._last_view_data and event_message.get("view", {}).get(
                "id"
            ) == self._last_view_data.get("id"):
                self.clear_widget()
        except Exception as e:
            self.logger.error(f"Error handling 'view-closed' event: {e}")

    @subscribe_to_event("view-title-changed")
    def on_view_title_changed(self, event_message: Dict[str, Any]) -> None:
        """
        Handle when a view's title changes.
        """
        try:
            view = event_message.get("view")
            if view:
                self.update_title_icon_debounced(view)
        except Exception as e:
            self.logger.error(f"Error handling 'view-title-changed' event: {e}")

    def sway_translate_ipc(self, view: Dict[str, Any]) -> Dict[str, Any]:
        """Translates Wayland-specific keys to Sway/legacy keys for compatibility."""
        v = view.copy()
        v["app-id"] = view.get("app_id")
        v["title"] = view.get("name")
        return v

    def update_title_icon_debounced(self, view: Dict[str, Any]) -> None:
        """Debounce updates to prevent excessive calls during rapid changes."""
        self._last_view_data = view
        if self._debounce_timer_id is not None:
            GLib.source_remove(self._debounce_timer_id)
        self._debounce_timer_id = GLib.timeout_add(
            self._debounce_interval, self._perform_debounced_update
        )

    def update_title_icon(self, view: Optional[Dict[str, Any]]) -> None:
        """
        Update the title and icon based on the focused view.
        """
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
            initial_title = ""
            if title:
                initial_title = title.split()[0]
            app_id: Optional[str] = None
            if view.get("window_properties"):
                app_id = view.get("window_properties", {}).get("class")
            else:
                app_id = view.get("app-id", "").lower()
            if app_id:
                icon_name = self._gtk_helper.get_icon(app_id, initial_title, title)
                if icon_name:
                    self.update_title(title, icon_name)
        except Exception as e:
            self.logger.error(f"Error updating title/icon: {e}")
            self.clear_widget()

    def clear_widget(self) -> None:
        """
        Clear the widget when no view is focused.
        """
        self.update_title("", "")

    def filter_title(self, title: str) -> str:
        """
        Filter and shorten the title.
        """
        if not title:
            return ""
        title = self.gtk_helper.filter_utf_for_gtk(title)
        MAX_WORD_LENGTH = 30
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
        """
        Update the window title widget with new title and icon.
        Includes a defensive CSS check to prevent the GTK assertion crash.
        """
        try:
            self.window_title_label.set_label(title)
            icon_to_set = icon_name if icon_name else "None"
            self.window_title_icon.set_from_icon_name(icon_to_set)
            CLASS_NAME = "title-active"
            if title:
                self.window_title_content.add_css_class(CLASS_NAME)
            else:
                if self.window_title_content.has_css_class(CLASS_NAME):
                    self.safe_remove_css_class(self.window_title_content, CLASS_NAME)
        except Exception as e:
            self.logger.error(f"Error updating window title widget: {e}")

    def _perform_debounced_update(self) -> bool:
        """Internal method to perform the actual UI update after debounce."""
        self._debounce_timer_id = None
        if self._last_view_data:
            self.update_title_icon(self._last_view_data)
        return GLib.SOURCE_REMOVE

    def about(self):
        """
        A plugin that displays the title and icon of the currently
        focused window on the panel.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin tracks the active window and updates a panel widget
        to display its title and icon. It uses an event-driven model to
        remain synchronized with the system.
        Its core logic is centered on **event subscription, state
        synchronization, and debounced updates**:
        1.  **Event Subscription**: The plugin listens for system events
            such as "view-focused," "view-closed," and "view-title-changed."
            This allows it to react instantly to changes in the active
            window's state. It now uses a deferred retry loop (`_subscribe_to_events_with_retry`)
            to ensure the `event_manager` plugin is loaded before attempting
            to register callbacks.
        2.  **Debounced Updates**: To prevent the panel from flickering or
            excessively updating during rapid title changes (e.g., when a
            web page is loading), it uses a debouncing mechanism. This
            ensures updates are processed at a controlled rate by cancelling
            and resetting the GLib timer on every incoming event.
        3.  **Title and Icon Management**: It extracts the title and
            application ID from the event data. It filters the title to
            remove extraneous information and truncates it to a set
            length. It then uses the application ID to find and display
            the correct icon.
        4.  **UI Updates**: The plugin directly manipulates its internal
            widgets to reflect the current state, displaying the
            processed title and icon. The cleanup is handled in the
            `on_disable` hook, ensuring the GLib timer is correctly stopped.
        """
        return self.code_explanation.__doc__
