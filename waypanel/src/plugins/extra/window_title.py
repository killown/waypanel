from gi.repository import Gtk, GLib
from src.plugins.core.event_handler_decorator import subscribe_to_event
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

DEPS = ["top_panel"]


def initialize_plugin(panel_instance):
    """
    Initialize the plugin.

    Args:
        obj: The main panel object from panel.py
        app: The main application instance
    """
    return WindowTitlePlugin(panel_instance)


def get_plugin_placement(panel_instance):
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
        # Create window title widget components
        self.window_title_content = Gtk.Box()
        self.main_widget = (self.window_title_content, "append")
        self.window_title_label = Gtk.Label()
        self.window_title_icon = Gtk.Image.new_from_icon_name("None")
        self.window_title_icon.add_css_class("window-title-icon")
        self.title_length = self.config.get("window_title", {}).get("title_length", 50)

        # Assemble the widget
        self.window_title_content.append(self.window_title_icon)
        self.window_title_content.append(self.window_title_label)
        self.window_title_content.add_css_class("window-title-content")

        # Add CSS classes for styling
        self.window_title_label.add_css_class("window-title-label")

        # first update so it will set the default it if no focus yet
        self.update_title("", "focus-windows")

        # Debounce variables
        self._debounce_pending = False
        self._debounce_timer_id = None
        self._debounce_interval = 333  # ~3 updates per second (1000/3 ≈ 333ms)

    def disable(self):
        print(self.main_widget)
        self.utils.remove_widget(self.window_title_content)

    @subscribe_to_event("view-focused")
    def on_view_focused(self, event_message):
        """
        Handle when a view gains focus.

        Args:
            event_message (dict): The event message containing view details.
        """
        try:
            if "view" in event_message:
                view = event_message.get("view", {})
                self.update_title_icon(view)
        except Exception as e:
            self.log_error(f"Error handling 'view-focused' event: {e}")

    @subscribe_to_event("view-closed")
    def on_view_closed(self, event_message):
        """
        Handle when a view is closed.

        Args:
            event_message (dict): The event message containing view details.
        """
        try:
            self.clear_widget()
        except Exception as e:
            self.log_error(f"Error handling 'view-closed' event: {e}")

    @subscribe_to_event("view-title-changed")
    def on_view_title_changed(self, event_message):
        """
        Handle when a view's title changes.

        Args:
            event_message (dict): The event message containing view details.
        """
        try:
            if "view" in event_message:
                view = event_message.get("view", {})
                self.update_title_icon(view)
        except Exception as e:
            self.log_error(f"Error handling 'view-title-changed' event: {e}")

    def sway_translate_ipc(self, view):
        v = None
        if view["type"] == "con" or view["type"] == "floating_con":
            v = view
            v["app-id"] = view["app_id"]
            v["title"] = view["name"]
        return v

    def update_title_icon(self, view):
        """
        Update the title and icon based on the focused view.

        Args:
            view: The view object containing details like title, app-id, etc.
        """
        try:
            # check if the view is from sway socket

            if view:
                if "app_id" in view:
                    view = self.sway_translate_ipc(view)

                if self.compositor == "wayfire":
                    view = self.utils.is_view_valid(view)
                if not view:
                    return
                title = self.filter_title(view.get("title", ""))
                app_id = None
                # FIXME: The current approach becomes unwieldy when adding new compositors,
                # Solution: Standardize data output across compositors via IPC.
                # Implementation idea:
                # - Organize plugins by compositor (e.g., `sway/window_title.py`, `wayfire/window_title.py`)
                # - Auto-detect the active session (Sway/Wayfire/etc.)
                # - Plugin loader skips irrelevant compositor folders
                # This keeps things clean while maintaining compositor-specific logic where needed.
                if "window_properties" in view:
                    # SWAY
                    app_id = view["window_properties"].get("class", None)
                else:
                    # Wayfire
                    app_id = view.get("app-id", "").lower()
                initial_title = title.split()[0].lower() if title else ""
                icon = self.utils.get_icon(app_id, initial_title, title)

                # Update the widget
                self.update_title(title, icon)
        except Exception as e:
            self.log_error(f"Error updating title/icon: {e}")

    def clear_widget(self):
        """
        Clear the widget when no view is focused.
        """
        self.update_title("", "")

    def filter_title(self, title):
        """
        Filter and shorten the title based on certain rules, including limiting long words.

        Args:
            title: The raw title string.

        Returns:
            str: The filtered title.
        """
        if not title:
            return ""

        # Remove UTF-8 issues
        title = self.utils.filter_utf_for_gtk(title)

        # Maximum length for any single word (e.g., truncate after 50 chars)
        MAX_WORD_LENGTH = 50
        # Overall title length limit
        MAX_TITLE_LENGTH = self.title_length

        # Handle separator: take part before " — "
        if " — " in title:
            title = title.split(" — ")[0]

        # Split into words and limit each word's length
        words = title.split()
        shortened_words = []
        for word in words:
            if len(word) > MAX_WORD_LENGTH:
                word = word[:MAX_WORD_LENGTH] + "…"  # Add ellipsis for truncated words
            shortened_words.append(word)

        # Rebuild title
        title = " ".join(shortened_words)

        # Final truncation to respect overall title length
        if len(title) > MAX_TITLE_LENGTH:
            # Preserve space for ellipsis
            title = title[: MAX_TITLE_LENGTH - 1] + "…"

        return title

    def update_title(self, title, icon_name):
        """
        Update the window title widget with new title and icon.

        Args:
            title: The new title to display.
            icon_name: The new icon name to display.
        """
        try:
            # Update the label
            self.window_title_label.set_label(title)

            # Update the icon
            if icon_name:
                self.window_title_icon.set_from_icon_name(icon_name)
            else:
                self.window_title_icon.set_from_icon_name("None")
        except Exception as e:
            self.log_error(f"Error updating window title widget: {e}")

    def _perform_debounced_update(self):
        """Internal method to perform the actual UI update after debounce."""
        self._debounce_pending = False
        self._debounce_timer_id = None
        return False  # Return False to stop the timeout
