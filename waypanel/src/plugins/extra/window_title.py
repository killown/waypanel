from gi.repository import Gtk
from ...core.utils import Utils


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
    position = "left"
    order = 5
    return position, order


class WindowTitlePlugin:
    def __init__(self, panel_instance):
        """
        Initialize the Window Title plugin.
        """
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.utils = Utils()
        self.title_length = 50

        # Create window title widget components
        self.window_title_content = Gtk.Box()
        self.window_title_label = Gtk.Label()
        self.window_title_icon = Gtk.Image.new_from_icon_name("None")
        self.title_length = 50

        # Assemble the widget
        self.window_title_content.append(self.window_title_icon)
        self.window_title_content.append(self.window_title_label)

        # Add CSS classes for styling
        self.window_title_label.add_css_class("topbar-title-content-label")

        # Subscribe to necessary events using the EventManagerPlugin
        self._subscribe_to_events()

    def append_widget(self):
        return self.window_title_content

    def _subscribe_to_events(self):
        """
        Subscribe to relevant events using the EventManagerPlugin.
        """
        if "event_manager" not in self.obj.plugin_loader.plugins:
            self.logger.error(
                "Event Manager Plugin is not loaded. Cannot subscribe to events."
            )
            return

        event_manager = self.obj.plugin_loader.plugins["event_manager"]

        # Subscribe to view-related events
        event_manager.subscribe_to_event(
            "view-focused", self.on_view_focused, plugin_name="window_title"
        )
        event_manager.subscribe_to_event(
            "view-closed",
            self.on_view_closed,
            plugin_name="window_title",
        )
        event_manager.subscribe_to_event(
            "view-title-changed",
            self.on_view_title_changed,
            plugin_name="window_title",
        )

        self.logger.info("Window Title Plugin subscribed to view events.")

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
            self.logger.error(f"Error handling 'view-focused' event: {e}")

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
            self.logger.error(f"Error handling 'view-title-changed' event: {e}")

    def update_title_icon(self, view):
        """
        Update the title and icon based on the focused view.

        Args:
            view: The view object containing details like title, app-id, etc.
        """
        try:
            view = self.utils.is_view_valid(view)
            if not view:
                return
            title = self.filter_title(view.get("title", ""))
            wm_class = view.get("app-id", "").lower()
            initial_title = title.split()[0].lower() if title else ""
            icon = self.utils.get_icon(wm_class, initial_title, title)

            # Update the widget
            self.update_widget(title, icon)
        except Exception as e:
            self.logger.error(f"Error updating title/icon: {e}")

    def clear_widget(self):
        """
        Clear the widget when no view is focused.
        """
        self.update_widget("", "")

    def filter_title(self, title):
        """
        Filter and shorten the title based on certain rules.

        Args:
            title: The raw title string.

        Returns:
            str: The filtered title.
        """
        if not title:
            return ""

        # Remove UTF-8 issues
        title = self.utils.filter_utf_for_gtk(title)

        # Shorten the title if too long
        if len(title) > self.title_length:
            words = title.split()
            first_word_length = len(words[0]) if words else 0
            if first_word_length > 10:
                title = words[0]
            else:
                title = title[: self.title_length]

        if " — " in title:
            title = title.split(" — ")[0]
        return title

    def update_widget(self, title, icon_name):
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
            self.logger.error(f"Error updating window title widget: {e}")
