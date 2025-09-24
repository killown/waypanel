# The MIT License (MIT)
#
# Copyright (c) 2023 Thiago <systemofdown@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import os
import sqlite3
import json
from gi.repository import Gtk  # pyright: ignore
from ._utils import NotifyUtils
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

DEPS = ["top_panel", "notify_server"]

DEFAULT_CONFIG = {
    "notify": {
        "client": {
            "max_notifications": 5.0,
            "body_max_width_chars": 80.0,
            "notification_icon_size": 64.0,
            "popover_width": 500.0,
            "popover_height": 600.0,
        },
        "server": {"show_messages": True},
    }
}


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-center"
    order = 10
    priority = 99
    return position, order, priority


def initialize_plugin(panel_instance):
    """Initialize the Notification Popover Plugin."""
    if ENABLE_PLUGIN:
        return NotificationPopoverPlugin(panel_instance)


class NotificationPopoverPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

        # Ensure the 'notify.client' section exists and is fully populated
        if "notify" not in self.config_handler.config_data:
            self.config_handler.config_data["notify"] = {}
        if "client" not in self.config_handler.config_data.get("notify"):
            self.config_handler.config_data["notify"]["client"] = {}
        self.config_handler.config_data["notify"]["client"] = {
            **DEFAULT_CONFIG["notify"]["client"],
            **self.config_handler.config_data["notify"]["client"],
        }

        # Ensure the 'notify.server' section exists
        if "server" not in self.config_handler.config_data["notify"]:
            self.config_handler.config_data["notify"]["server"] = {}
        self.config_handler.config_data["notify"]["server"] = {
            **DEFAULT_CONFIG["notify"]["server"],
            **self.config_handler.config_data["notify"]["server"],
        }

        self.config_handler.save_config()
        self.config_handler.reload_config()

        self.notify_utils = NotifyUtils(self.obj)
        self.notification_server = self.plugins["notify_server"]
        # Create a vertical box to hold notification details
        self.vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        self.vbox.set_margin_top(10)
        self.vbox.set_margin_bottom(10)
        self.vbox.set_margin_start(10)
        self.show_messages = None
        self.max_notifications = (
            self.config_handler.config_data.get("notify", {})
            .get("client", {})
            .get("max_notifications", 5)
        )

        self.vbox.set_margin_end(10)
        self.notification_on_popover = {}
        self.notification_button = Gtk.Button.new_from_icon_name(
            self.gtk_helper.set_widget_icon_name(
                "notify",
                ["liteupdatesnotify", "org.gnome.Settings-notifications-symbolic"],
            )
        )
        self.notification_button.add_css_class("notification-panel-button")
        self.notification_button.set_tooltip_text("View Recent Notifications")
        self.notification_button.connect("clicked", self.open_popover_notifications)
        self.gtk_helper.add_cursor_effect(self.notification_button)
        # Initialize the Do Not Disturb switch
        self.dnd_switch = Gtk.Switch()
        self.dnd_switch.set_active(False)
        self.dnd_switch.connect("state-set", self.on_dnd_toggled)

        # Define the main widget and action
        self.main_widget = (self.notification_button, "append")

        # Path to the notifications database
        self.db_path = os.path.expanduser("~/.config/waypanel/notifications.db")

    def update_dnd_switch_state(self):
        """Update the Do Not Disturb switch state based on the server setting."""
        try:
            show_messages = (
                self.config_handler.config_data("notify", {})
                .get("server", {})
                .get("show_messages", True)
            )
            self.dnd_switch.set_active(
                not show_messages
            )  # Invert the value since DND is the opposite of showing messages
        except Exception as e:
            self.log_error(f"Error updating DND switch state: {e}")

    def on_dnd_toggled(self, switch, state):
        """Callback when the Do Not Disturb switch is toggled."""
        new_show_messages = (
            not state
        )  # Invert the state to match the `show_messages` setting

        try:
            # Update the configuration
            if "notify" not in self.config_handler.config_data:
                self.config_handler.config_data["notify"] = {}
            if "server" not in self.config_handler.config_data["notify"]:
                self.config_handler.config_data["notify"]["server"] = {}

            self.config_handler.config_data["notify"]["server"]["show_messages"] = (
                new_show_messages
            )

            # Save the updated configuration
            self.config_handler.save_config()

            # Reload the configuration in the panel instance
            self.config_handler.reload_config()

            self.logger.info(
                f"Do Not Disturb mode {'enabled' if state else 'disabled'}"
            )
        except Exception as e:
            self.log_error(f"Error toggling Do Not Disturb mode: {e}")

    def fetch_last_notifications(self, limit=5):
        limit = self.max_notifications
        """
        Fetch the last 3 notifications from the database.
        :return: List of notifications (dictionaries).
        """
        try:
            if not os.path.exists(self.db_path):
                self.logger.warning(f"Database file not found at {self.db_path}")
                return []

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, app_name, summary, body, app_icon, actions, hints, timestamp
                FROM notifications
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            rows = cursor.fetchall()
            conn.close()

            notifications = []
            for row in rows:
                (
                    notification_id,
                    app_name,
                    summary,
                    body,
                    app_icon,
                    actions,
                    hints,
                    timestamp,
                ) = row
                if notification_id in self.notification_on_popover:
                    continue

                notifications.append(
                    {
                        "id": notification_id,
                        "app_name": app_name,
                        "summary": summary,
                        "body": body,
                        "app_icon": app_icon,
                        "actions": actions,
                        "hints": json.loads(hints)
                        if hints
                        else {},  # Deserialize hints
                        "timestamp": timestamp,
                    }
                )
            return notifications
        except Exception as e:
            self.log_error(f"Error fetching notifications from database: {e}")

    def on_notification_click(self, notification, widget):
        """Handle click action on a notification."""
        try:
            actions = notification.get("actions", [])
            if isinstance(actions, tuple):
                action_id, action_label = actions[0]  # Default to the first action
                if action_id == "default":
                    self.handle_default_action(notification, widget)
                else:
                    self.logger.error(f"Unexpected action_id: {action_id}")
            else:
                actions = actions.split(",")[0]
                if actions == "default":
                    self.handle_default_action(notification, widget)
                else:
                    self.logger.error(f"Unexpected action_id: {actions}")
        except Exception as e:
            self.logger.error(f"Error handling notification click: {e}")

    def handle_default_action(self, notification, widget):
        """Handle the default action for a notification."""
        # FIXME: need a proper way to handle those actions
        try:
            hints = notification.get("hints", {})
            url = hints.get("url", "")
            desktop_entry = hints.get("desktop-entry", "").lower()
            print(desktop_entry)

            if url:
                self.cmd.open_url(url)
            elif desktop_entry:
                self.cmd.run(desktop_entry)
                self.popover.popdown()
                return True
            else:
                self.logger.info("No default action defined in hints.")
        except Exception as e:
            self.logger.error(f"Error handling default action: {e}")

    def execute_default_action(self, action, notification):
        """Execute the default action specified in hints."""
        try:
            self.logger.info(f"Executing default action: {action}")
            if action.startswith("app://"):
                app_id = action.split("://")[1]
                self.cmd.run(app_id)
        except Exception as e:
            self.logger.error(f"Error executing default action '{action}': {e}")

    def create_notification_box(self, notification):
        """Create a notification box with an optional image on the left, content on the right, and a close button.

        :param notification: Dictionary containing notification details.
        :param notification_box: The parent box to which the notification will be added.
        :return: Gtk.Box containing the notification content.
        """
        body_max_width_chars = (
            self.config_handler.config_data.get("notify", {})
            .get("client", {})
            .get("body_max_width_chars", 50)
        )

        notification_icon_size = (
            self.config_handler.config_data.get("notify", {})
            .get("client", {})
            .get("notification_icon_size", 64)
        )

        # Create a horizontal box to hold the image and text content
        hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 30)  # spacing between columns
        hbox.add_css_class("notify-client-box")

        # Add a close button
        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_button.set_tooltip_text("Close Notification")
        self.gtk_helper.add_cursor_effect(close_button)

        close_button.set_margin_start(10)  # Add spacing between content and button
        close_button.connect(
            "clicked", lambda _: self.delete_notification(notification.get("id"), hbox)
        )
        self.update_widget_safely(hbox.append, close_button)

        # Left column: Icon/Image container
        left_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        left_box.set_halign(Gtk.Align.START)
        left_box.set_valign(Gtk.Align.START)

        # Right column: Text content container
        right_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        right_box.set_halign(Gtk.Align.START)

        # Make the entire hbox clickable

        if "gestures_setup" in self.plugins:
            gestures_setup = self.plugins["gestures_setup"]
            gestures_setup.create_gesture(
                widget=hbox,
                mouse_button=1,  # Left mouse button
                callback=lambda widget: self.on_notification_click(
                    notification, widget
                ),
            )

        # Load the icon/image
        icon = self.notify_utils.load_icon(notification)
        if icon and icon.get_name():
            icon.set_pixel_size(notification_icon_size)
            icon.set_halign(Gtk.Align.START)
            icon.add_css_class("notification-icon")
            self.update_widget_safely(left_box.append, icon)

        # App Name
        app_label = Gtk.Label(label=f"<b>{notification['app_name']}</b>")
        app_label.set_use_markup(True)
        app_label.set_halign(Gtk.Align.START)
        self.update_widget_safely(left_box.append, app_label)

        # Summary
        summary_label = Gtk.Label(label=notification["summary"])
        summary_label.set_wrap(True)
        summary_label.set_halign(Gtk.Align.START)
        summary_label.add_css_class("notify-client-heading")
        self.update_widget_safely(right_box.append, summary_label)

        # Body
        body_label = Gtk.Label(label=notification["body"])
        body_label.set_wrap(True)
        body_label.set_max_width_chars(body_max_width_chars)
        body_label.set_halign(Gtk.Align.START)
        self.update_widget_safely(right_box.append, body_label)
        body_label.add_css_class("notify-client-body-label")

        # Timestamp
        timestamp_label = Gtk.Label(label=notification["timestamp"])
        timestamp_label.set_halign(Gtk.Align.START)
        timestamp_label.add_css_class("notify-client-timestamp")
        self.update_widget_safely(right_box.append, timestamp_label)

        # Add left and right boxes to the horizontal box
        self.update_widget_safely(hbox.append, left_box)
        self.update_widget_safely(hbox.append, right_box)

        # Add the horizontal box to the notification_box
        self.update_widget_safely(self.vbox.append, hbox)
        self.notification_on_popover["id"] = notification

        return hbox

    def clear_all_notifications(self, *_):
        """Clear all notifications from the database and remove them from the UI."""
        try:
            # Clear all notifications from the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM notifications")
            conn.commit()
            conn.close()

            # Remove all notifications from the UI
            child = self.vbox.get_first_child()
            while child:
                next_child = (
                    child.get_next_sibling()
                )  # Get the next sibling before removing
                self.vbox.remove(child)  # Remove the current child
                child = next_child  # Move to the next child

            print("All notifications cleared.")
        except Exception as e:
            print(f"Error clearing notifications: {e}")

    def delete_notification(self, notification_id, notification_box):
        """Delete a notification from the database and remove it from the UI.
        If there are older notifications, append the next oldest one to the UI.

        :param notification_id: ID of the notification to delete.
        :param notification_box: The Gtk.Box containing the notification content.
        """
        try:
            # Delete the notification from the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
            conn.commit()
            conn.close()

            # Remove the notification box from the UI
            parent = notification_box.get_parent()
            if parent:
                parent.remove(notification_box)

            print(f"Notification {notification_id} deleted.")

            # Append the next oldest notification to the UI
            self.append_next_oldest_notification()

        except Exception as e:
            print(f"Error deleting notification {notification_id}: {e}")

    def append_next_oldest_notification(self):
        """Fetch the next oldest notification from the database and append it to the UI."""
        try:
            # Fetch the last 3 notifications currently displayed
            notifications = self.fetch_last_notifications(limit=1)
            if notifications:
                notifications = notifications[0]
            print(notifications)

            # Fetch the next oldest notification from the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                    SELECT id, app_name, summary, body, app_icon, actions, hints, timestamp
                    FROM notifications
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
            row = cursor.fetchone()
            conn.close()

            if row:
                # Create a notification dictionary
                notification = {
                    "id": row[0],
                    "app_name": row[1],
                    "summary": row[2],
                    "body": row[3],
                    "app_icon": row[4],
                    "actions": row[5],
                    "hints": json.loads(row[6]),
                    "timestamp": row[7],
                }

                vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
                vbox.set_margin_top(10)
                vbox.set_margin_bottom(10)
                vbox.set_margin_start(10)
                vbox.set_margin_end(10)

                # Append the notification to the UI
                self.create_notification_box(notification)

        except Exception as e:
            self.log_error(f"Error appending next oldest notification: {e}")

    def open_popover_notifications(self, *_):
        if not hasattr(self, "popover") or not self.popover:
            self.popover = Gtk.Popover.new()
            self.popover_width = (
                self.config_handler.config_data.get("notify", {})
                .get("client", {})
                .get("popover_width", 500)
            )
            self.popover_height = (
                self.config_handler.config_data.get("notify", {})
                .get("client", {})
                .get("popover_height", 600)
            )
            # Main vertical box for the popover content
            self.main_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            self.main_vbox.set_margin_top(10)
            self.main_vbox.set_margin_bottom(10)
            self.main_vbox.set_margin_start(10)
            self.main_vbox.set_margin_end(10)
            # Clear All button
            clear_button = Gtk.Button(label="Clear")
            clear_button.connect("clicked", lambda _: self.clear_all_notifications())
            clear_button.set_tooltip_text("Clear All Notifications")
            clear_button.set_margin_start(10)
            self.gtk_helper.add_cursor_effect(clear_button)
            self.update_widget_safely(self.main_vbox.append, clear_button)

            # Notification content area (scrollable)
            self.vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            self.vbox.set_vexpand(True)  # Allow the vbox to expand and fill space
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_child(self.vbox)
            scrolled_window.set_vexpand(True)  # Ensure the scroll area expands
            scrolled_window.set_propagate_natural_width(True)
            self.update_widget_safely(self.main_vbox.append, scrolled_window)

            # Bottom controls container
            bottom_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            bottom_box.set_margin_top(10)  # Add spacing above the bottom controls

            # Do Not Disturb switch
            self.dnd_switch = Gtk.Switch()
            self.dnd_switch.set_active(False)
            self.dnd_switch.connect("state-set", self.on_dnd_toggled)
            self.gtk_helper.add_cursor_effect(self.dnd_switch)

            dnd_label = Gtk.Label(label="Do Not Disturb")
            dnd_label.set_halign(Gtk.Align.START)
            dnd_label.set_margin_end(10)

            dnd_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)
            self.update_widget_safely(dnd_box.append, dnd_label)
            self.update_widget_safely(dnd_box.append, self.dnd_switch)

            self.update_widget_safely(bottom_box.append, dnd_box)

            # Add the bottom box to the main container
            self.update_widget_safely(self.main_vbox.append, bottom_box)

            # Set the main container as the popover's child
            self.popover.set_child(self.main_vbox)

        # Ensure no existing parent conflicts
        if self.popover.get_parent():
            self.popover.unparent()

        # Clear existing children from vbox
        child = self.vbox.get_first_child()
        while child:
            next_child = (
                child.get_next_sibling()
            )  # Get the next sibling before removing
            self.vbox.remove(child)  # Remove the current child
            child = next_child  # Move to the next child

        # Fetch and display notifications
        notifications = self.fetch_last_notifications()
        if not notifications:
            self.logger.info("No notifications to display.")
            return

        box_size = 100
        height = 100
        for notification in notifications:
            height += box_size
            self.create_notification_box(notification)

        self.main_vbox.set_size_request(self.popover_width, self.popover_height)

        # Initialize DND state
        self.update_dnd_switch_state()

        self.popover.set_parent(self.notification_button)
        self.popover.popup()

    def about(self):
        """
        This plugin provides a graphical user interface (GUI) on a panel
        for viewing and managing recent desktop notifications, acting as
        a client to the D-Bus notification server plugin.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This code is the client-side component of a two-part notification
        system. Its core logic revolves around the following principles:

        1.  **UI and Interaction**: The plugin creates a panel button that
            activates a popover. This popover dynamically populates itself
            with notification data retrieved from a local SQLite database.
            It provides user controls like a "Clear All" button and a
            "Do Not Disturb" toggle.

        2.  **State Management**: It manages the state of the "Do Not
            Disturb" mode. When the user toggles the switch, the plugin
            writes the new state to the application's configuration file,
            which the companion notification server reads to determine if
            it should display new pop-ups.

        3.  **Data Retrieval**: Notifications are fetched from a database
            that is populated by the separate notification server daemon.
            This ensures that the UI can display a history of messages
            even if it's not active, as the server handles all real-time
            notification reception.

        4.  **Decoupling**: By separating the UI (this plugin) from the
            backend logic (the server plugin), the system ensures that
            notifications can be processed and stored independently of
            the UI's state. This makes the system robust and modular.
        """
        return self.code_explanation.__doc__
