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
        self.window_title_content = Gtk.Box()
        self.main_widget = (self.window_title_content, "append")
        self.window_title_label = Gtk.Label()
        self.window_title_icon = Gtk.Image.new_from_icon_name("None")
        self.window_title_icon.add_css_class("window-title-icon")
        self.title_length = self.config_handler.config_data.get("window_title", {}).get(
            "title_length", 50
        )

        self.window_title_content.append(self.window_title_icon)
        self.window_title_content.append(self.window_title_label)
        self.window_title_content.add_css_class("window-title-content")

        self.window_title_label.add_css_class("window-title-label")

        self.update_title("", "focus-windows")

        self._debounce_pending = False
        self._debounce_timer_id = None
        self._debounce_interval = 333  # ~3 updates per second (1000/3 ≈ 333ms)
        self._last_view_data = None

    def disable(self):
        self.gtk_helper.remove_widget(self.window_title_content)

    @subscribe_to_event("view-focused")
    def on_view_focused(self, event_message):
        """
        Handle when a view gains focus.

        Args:
            event_message (dict): The event message containing view details.
        """
        try:
            view = event_message.get("view")
            if view:
                self.update_title_icon_debounced(view)
        except Exception as e:
            self.logger.error(f"Error handling 'view-focused' event: {e}")

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
            self.logger.error(f"Error handling 'view-closed' event: {e}")

    @subscribe_to_event("view-title-changed")
    def on_view_title_changed(self, event_message):
        """
        Handle when a view's title changes.

        Args:
            event_message (dict): The event message containing view details.
        """
        try:
            view = event_message.get("view")
            if view:
                self.update_title_icon_debounced(view)
        except Exception as e:
            self.logger.error(f"Error handling 'view-title-changed' event: {e}")

    def sway_translate_ipc(self, view):
        # Create a copy to avoid side-effects
        v = view.copy()
        v["app-id"] = view.get("app_id")
        v["title"] = view.get("name")
        return v

    def update_title_icon_debounced(self, view):
        """Debounce updates to prevent excessive calls during rapid changes."""
        self._last_view_data = view
        if not self._debounce_pending:
            self._debounce_pending = True
            self._debounce_timer_id = GLib.timeout_add(
                self._debounce_interval, self._perform_debounced_update
            )
            self.update_title_icon(self._last_view_data)

    def update_title_icon(self, view):
        """
        Update the title and icon based on the focused view.

        Args:
            view: The view object containing details like title, app-id, etc.
        """
        try:
            if not view:
                return

            if view.get("app_id") is not None:
                view = self.sway_translate_ipc(view)

            if self.compositor == "wayfire":
                view = self.wf_helper.is_view_valid(view)

            if not view:
                return

            title = self.filter_title(view.get("title", ""))
            app_id = None
            if view.get("window_properties"):
                app_id = view.get("window_properties", {}).get("class")
            else:
                app_id = view.get("app-id", "").lower()

            initial_title = title.split()[0].lower() if title else ""
            icon = self.gtk_helper.get_icon(app_id, initial_title, title)

            self.update_title(title, icon)
        except Exception as e:
            self.logger.error(f"Error updating title/icon: {e}")

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

        title = self.gtk_helper.filter_utf_for_gtk(title)

        MAX_WORD_LENGTH = 50
        MAX_TITLE_LENGTH = self.title_length

        if " — " in title:
            title = title.split(" — ")[0]

        words = title.split()
        shortened_words = []
        for word in words:
            if len(word) > MAX_WORD_LENGTH:
                word = word[:MAX_WORD_LENGTH] + "…"  # Add ellipsis for truncated words
            shortened_words.append(word)

        title = " ".join(shortened_words)

        if len(title) > MAX_TITLE_LENGTH:
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
            self.window_title_label.set_label(title)
            if icon_name:
                self.window_title_icon.set_from_icon_name(icon_name)
            else:
                self.window_title_icon.set_from_icon_name("None")
        except Exception as e:
            self.logger.error(f"Error updating window title widget: {e}")

    def _perform_debounced_update(self):
        """Internal method to perform the actual UI update after debounce."""
        self._debounce_pending = False
        self._debounce_timer_id = None
        self.update_title_icon(self._last_view_data)
        return False

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
            window's state.
        2.  **Debounced Updates**: To prevent the panel from flickering or
            excessively updating during rapid title changes (e.g., when a
            web page is loading), it uses a debouncing mechanism. This
            ensures updates are processed at a controlled rate.
        3.  **Title and Icon Management**: It extracts the title and
            application ID from the event data. It filters the title to
            remove extraneous information and truncates it to a set
            length. It then uses the application ID to find and display
            the correct icon.
        4.  **UI Updates**: The plugin directly manipulates its internal
            widgets to reflect the current state, displaying the
            processed title and icon.
        """
        return self.code_explanation.__doc__
