import os
import toml
from gi.repository import Gtk
from waypanel.src.ipc_server.ipc_client import WayfireClientIPC
from ...core.utils import Utils


class WindowTitlePlugin:
    def __init__(self, obj, app):
        """
        Initialize the plugin.

        Args:
            obj: The main panel object from panel.py
            app: The main application instance
        """
        self.obj = obj
        self.app = app
        self.utils = Utils()
        self.logger = app.logger  # Assuming logger is available via app instance
        self.config_path = os.path.expanduser("~/.config/waypanel/waypanel.toml")
        self.load_config()

        # Create window title widget components
        self.window_title_content = Gtk.Box()
        self.window_title_label = Gtk.Label()
        self.window_title_icon = Gtk.Image.new_from_icon_name("None")

        # Assemble the widget
        self.window_title_content.append(self.window_title_icon)
        self.window_title_content.append(self.window_title_label)

        # Add CSS classes for styling
        self.window_title_label.add_css_class("topbar-title-content-label")
        self.window_title_icon.add_css_class("topbar-title-content-icon")
        self.window_title_content.add_css_class("topbar-title-content")

        # Add the widget to the top panel's window title box
        obj.top_panel_box_left.append(self.window_title_content)

        # Set up IPC client
        self.ipc_client = WayfireClientIPC(self.handle_event)
        self.ipc_client.wayfire_events_setup("/tmp/waypanel.sock")

    def load_config(self):
        """Load configuration from waypanel.toml."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                self.config = toml.load(f)
        else:
            self.config = {}

    def handle_event(self, event):
        """
        Handle IPC events from the Wayfire compositor.

        Args:
            event: The event dictionary received from the IPC server.
        """
        if self.handle_view_event(event):
            return
        try:
            if event.get("event") == "view-focused":
                view = event.get("view", {})
                self.update_title_icon(view)
            elif event.get("event") == "view-closed":
                self.clear_widget()
            elif event.get("event") == "view-title-changed":
                view = event.get("view", {})
                self.update_title_icon(view)
        except Exception as e:
            self.logger.error(f"Error handling IPC event: {e}")

    def handle_view_event(self, msg):
        # Validate the event using handle_event_checks
        if not self.utils.handle_event_checks(msg, required_keys=["event"]):
            return True

        view = msg.get("view")

        # Common checks for view-related events
        if view is None:
            return True

        if view["pid"] == -1 or view.get("role") != "toplevel":
            return True

        if view.get("app-id") in ["", "nil"]:
            return True

    def update_title_icon(self, view):
        """
        Update the title and icon based on the focused view.

        Args:
            view: The view object containing details like title, app-id, etc.
        """
        try:
            title = self.filter_title(view.get("title", ""))
            wm_class = view.get("app-id", "").lower()
            initial_title = title.split()[0].lower() if title else ""
            icon = self.utils.get_icon(wm_class, initial_title, title)

            # Update the widget
            self.update_widget(title, icon)
        except Exception as e:
            self.logger.error(f"Error updating title/icon: {e}")

    def clear_widget(self):
        """Clear the widget when no view is focused."""
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
        if len(title) > 20:
            words = title.split()
            first_word_length = len(words[0]) if words else 0
            if first_word_length > 10:
                title = words[0]
            else:
                title = title[:20]

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


def initialize_plugin(obj, app):
    """
    Initialize the plugin.

    Args:
        obj: The main panel object from panel.py
        app: The main application instance
    """
    return WindowTitlePlugin(obj, app)


def position():
    """
    Define the plugin's position and order.

    Returns:
        tuple: (position, order)
    """
    position = "center"
    order = 5
    return position, order
