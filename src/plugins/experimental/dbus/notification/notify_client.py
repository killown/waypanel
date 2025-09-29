import os
import sqlite3
import json
import re
from gi.repository import Gtk  # pyright: ignore
from ._utils import NotifyUtils
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True
DEPS = ["top_panel", "notify_server"]


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
        self.notify_utils = NotifyUtils(self.obj)
        self.notification_server = self.plugins["notify_server"]
        self.vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        self.vbox.set_margin_top(10)
        self.vbox.set_margin_bottom(10)
        self.vbox.set_margin_start(10)
        self.show_messages = None
        self.max_notifications = self.get_config(
            ["notify", "client", "max_notifications"], 5
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
        self.dnd_switch = Gtk.Switch()
        self.dnd_switch.set_active(False)
        self.dnd_switch.connect("state-set", self.on_dnd_toggled)
        self.main_widget = (self.notification_button, "append")
        self.db_path = os.path.expanduser("~/.config/waypanel/notifications.db")

    def update_dnd_switch_state(self):
        """Update the Do Not Disturb switch state based on the server setting."""
        try:
            show_messages = self.get_config(["notify", "server", "show_messages"], True)
            self.dnd_switch.set_active(not show_messages)
        except Exception as e:
            self.logger.error(f"Error updating DND switch state: {e}")

    def on_dnd_toggled(self, switch, state):
        """Callback when the Do Not Disturb switch is toggled."""
        new_show_messages = not state
        try:
            self.update_config(["notify", "server", "show_messages"], new_show_messages)
            self.logger.info(
                f"Do Not Disturb mode {'enabled' if state else 'disabled'}"
            )
        except Exception as e:
            self.logger.error(f"Error toggling Do Not Disturb mode: {e}")

    def fetch_last_notifications(self, limit=5):
        limit = self.max_notifications
        """
        Fetch the last notifications from the database.
        :return: List of notifications (dictionaries).
        """
        try:
            if not os.path.exists(self.db_path):
                self.logger.warning(f"Database file not found at {self.db_path}")
                return []
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            limit_int = int(limit) if limit is not None else 5
            cursor.execute(f"""
                SELECT id, app_name, summary, body, app_icon, actions, hints, timestamp
                FROM notifications
                ORDER BY timestamp DESC
                LIMIT {limit_int}
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
                notifications.append(
                    {
                        "id": notification_id,
                        "app_name": app_name,
                        "summary": summary,
                        "body": body,
                        "app_icon": app_icon,
                        "actions": actions,
                        "hints": json.loads(hints) if hints else {},
                        "timestamp": timestamp,
                    }
                )
            return notifications
        except Exception as e:
            self.logger.error(f"Error fetching notifications from database: {e}")

    def _extract_first_uri_from_text(self, text: str) -> str | None:
        """
        Uses a regular expression to find and return the first URL in a string.
        """
        url_regex = r"(?:https?|ftp)://\S+|www\.\S+"
        matches = re.findall(url_regex, text)
        if matches:
            uri = matches[0].rstrip(".,;")
            return uri
        return None

    def on_launch_uri(self, uri: str):
        """
        Launches the specified URI using xdg-open via the command utility
        and closes the popover.
        """
        self.cmd.open_url(uri)
        if hasattr(self, "popover") and self.popover:
            self.popover.popdown()
        self.logger.info(f"Launching URI: {uri}")
        return True

    def on_launch_uri_clicked(self, button: Gtk.Button, uri: str):
        """Handler for the dedicated 'Open Link' button."""
        self.on_launch_uri(uri)

    def on_notification_click(self, notification, widget):
        """
        Handle click action on a notification:
        1. Link in body (Highest Priority)
        2. Link in hints (Fallback)
        3. Desktop Entry in hints (App Launch)
        """
        self.logger.info(f"Notification clicked: {notification.get('id')}")
        extracted_uri = self._extract_first_uri_from_text(notification.get("body", ""))
        hints = notification.get("hints", {})
        hint_url = hints.get("url", "")
        uri_to_launch = extracted_uri or hint_url
        if uri_to_launch:
            self.on_launch_uri(uri_to_launch)
            return
        desktop_entry = hints.get("desktop-entry", "").lower()
        if desktop_entry:
            self.cmd.run(desktop_entry)
            if hasattr(self, "popover") and self.popover:
                self.popover.popdown()
            self.logger.info(f"Launching application: {desktop_entry}")
            return
        if hasattr(self, "popover") and self.popover:
            self.popover.popdown()
            self.logger.debug("Notification click closed popover (no action found).")

    def handle_default_action(self, notification):
        """Deprecated: Logic centralized in on_notification_click."""
        self.on_notification_click(notification, None)

    def execute_default_action(self, action, notification):
        """Execute the default action specified in hints."""
        try:
            self.logger.info(f"Executing default action: {action}")
            if action.startswith("app://"):
                app_id = action.split("://")[1]
                self.cmd.run(app_id)
                if hasattr(self, "popover") and self.popover:
                    self.popover.popdown()
        except Exception as e:
            self.logger.error(f"Error executing default action '{action}': {e}")

    def create_notification_box(self, notification):
        """Create a notification box. No explicit link button is added."""
        body_max_width_chars = self.get_config(
            ["notify", "client", "body_max_width_chars"], 50
        )
        notification_icon_size = self.get_config(
            ["notify", "client", "notification_icon_size"], 64
        )
        hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 30)
        hbox.add_css_class("notify-client-box")
        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_button.set_tooltip_text("Close Notification")
        self.gtk_helper.add_cursor_effect(close_button)
        close_button.set_margin_start(10)
        close_button.connect(
            "clicked", lambda _: self.delete_notification(notification.get("id"), hbox)
        )
        self.update_widget_safely(hbox.append, close_button)
        left_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        left_box.set_halign(Gtk.Align.START)
        left_box.set_valign(Gtk.Align.START)
        right_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        right_box.set_halign(Gtk.Align.START)
        if "gestures_setup" in self.plugins:
            gestures_setup = self.plugins["gestures_setup"]
            gestures_setup.create_gesture(
                widget=hbox,
                mouse_button=1,
                callback=lambda widget: self.on_notification_click(
                    notification, widget
                ),
            )
        icon = self.notify_utils.load_icon(notification)
        if icon and icon.get_name():
            icon.set_pixel_size(notification_icon_size)
            icon.set_halign(Gtk.Align.START)
            icon.add_css_class("notification-icon")
            self.update_widget_safely(left_box.append, icon)
        app_label = Gtk.Label(label=f"<b>{notification['app_name']}</b>")
        app_label.set_use_markup(True)
        app_label.set_halign(Gtk.Align.START)
        self.update_widget_safely(left_box.append, app_label)
        summary_label = Gtk.Label(label=notification["summary"])
        summary_label.set_wrap(True)
        summary_label.set_halign(Gtk.Align.START)
        summary_label.add_css_class("notify-client-heading")
        self.update_widget_safely(right_box.append, summary_label)
        body_label = Gtk.Label(label=notification["body"])
        body_label.set_wrap(True)
        body_label.set_max_width_chars(body_max_width_chars)
        body_label.set_halign(Gtk.Align.START)
        self.update_widget_safely(right_box.append, body_label)
        body_label.add_css_class("notify-client-body-label")
        timestamp_label = Gtk.Label(label=notification["timestamp"])
        timestamp_label.set_halign(Gtk.Align.START)
        timestamp_label.add_css_class("notify-client-timestamp")
        self.update_widget_safely(right_box.append, timestamp_label)
        self.update_widget_safely(hbox.append, left_box)
        self.update_widget_safely(hbox.append, right_box)
        separator = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        self.update_widget_safely(self.vbox.append, hbox)
        self.update_widget_safely(self.vbox.append, separator)
        self.notification_on_popover[notification["id"]] = hbox
        return hbox

    def clear_all_notifications(self, *_):
        """Clear all notifications from the database and remove them from the UI."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM notifications")
            conn.commit()
            conn.close()
            child = self.vbox.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.vbox.remove(child)
                child = next_child
            self.notification_on_popover = {}
            self.logger.info("All notifications cleared.")
        except Exception as e:
            self.logger.error(f"Error clearing notifications: {e}")

    def delete_notification(self, notification_id, notification_box):
        """Delete a notification from the database and remove it from the UI.
        :param notification_id: ID of the notification to delete.
        :param notification_box: The Gtk.Box containing the notification content (the hbox).
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
            conn.commit()
            conn.close()
            parent = notification_box.get_parent()
            if parent:
                separator = notification_box.get_next_sibling()
                parent.remove(notification_box)
                if separator and isinstance(separator, Gtk.Separator):
                    parent.remove(separator)
            if notification_id in self.notification_on_popover:
                del self.notification_on_popover[notification_id]
            self.logger.info(f"Notification {notification_id} deleted.")
        except Exception as e:
            self.logger.error(f"Error deleting notification {notification_id}: {e}")

    def append_next_oldest_notification(self):
        """Fetch the next oldest notification from the database and append it to the UI."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            displayed_ids = tuple(self.notification_on_popover.keys())
            query = f"""
                SELECT id, app_name, summary, body, app_icon, actions, hints, timestamp
                FROM notifications
                WHERE id NOT IN ({",".join(["?"] * len(displayed_ids)) if displayed_ids else "NULL"})
                ORDER BY timestamp DESC
                LIMIT 1
            """
            cursor.execute(query, displayed_ids)
            row = cursor.fetchone()
            conn.close()
            if row:
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
                self.create_notification_box(notification)
        except Exception as e:
            self.logger.error(f"Error appending next oldest notification: {e}")

    def open_popover_notifications(self, *_):
        if not hasattr(self, "popover") or not self.popover:
            self.popover = Gtk.Popover.new()
            self.popover_width = self.get_config(
                ["notify", "client", "popover_width"], 500
            )
            self.popover_height = self.get_config(
                ["notify", "client", "popover_height"], 600
            )
            self.main_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            self.main_vbox.set_margin_top(10)
            self.main_vbox.set_margin_bottom(10)
            self.main_vbox.set_margin_start(10)
            self.main_vbox.set_margin_end(10)
            clear_button = Gtk.Button(label="Clear")
            clear_button.connect("clicked", lambda _: self.clear_all_notifications())
            clear_button.set_tooltip_text("Clear All Notifications")
            clear_button.set_margin_start(10)
            self.gtk_helper.add_cursor_effect(clear_button)
            self.update_widget_safely(self.main_vbox.append, clear_button)
            self.vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            self.vbox.set_vexpand(True)
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_child(self.vbox)
            scrolled_window.set_vexpand(True)
            scrolled_window.set_propagate_natural_width(True)
            self.update_widget_safely(self.main_vbox.append, scrolled_window)
            bottom_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            bottom_box.set_margin_top(10)
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
            self.update_widget_safely(self.main_vbox.append, bottom_box)
            self.popover.set_child(self.main_vbox)
        if self.popover.get_parent():
            self.popover.unparent()
        child = self.vbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.vbox.remove(child)
            child = next_child
        self.notification_on_popover = {}
        notifications = self.fetch_last_notifications()
        if not notifications:
            self.logger.info("No notifications to display.")
            no_notify_label = Gtk.Label(label="No recent notifications")
            no_notify_label.add_css_class("no-notifications-label")
            self.update_widget_safely(self.vbox.append, no_notify_label)
        for notification in notifications:
            self.create_notification_box(notification)
        self.main_vbox.set_size_request(self.popover_width, self.popover_height)
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
        2.  **Robust Click Handling**: The `on_notification_click` method
            now implements a robust action hierarchy:
            - **Highest Priority**: Checks the notification's `body` for an
              embedded URL using a regex.
            - **Second Priority**: Checks the notification's `hints` for a
              `url` field.
            - **Action**: If *any* URL is found, it is launched using
              `self.cmd.open_url` (which typically executes `xdg-open`),
              and the popover closes.
            - **Third Priority**: If no URL is found, it checks `hints` for a
              `desktop-entry` field and launches the corresponding application
              using `self.cmd.run`.
            - **Fallback**: If no action is found, it simply closes the popover.
        3.  **No Dedicated Button**: The explicit "Open Link" button has been
            removed. All URI and app launch actions are now driven by the
            single click gesture on the notification box itself.
        """
        return self.code_explanation.__doc__
