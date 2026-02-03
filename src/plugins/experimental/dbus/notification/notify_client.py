def get_plugin_metadata(_):
    about = (
        "This plugin provides a graphical user interface (GUI) on a panel"
        "for viewing and managing recent desktop notificationons, acting as"
        "a client to the D-Bus notification server plugin."
    )
    return {
        "id": "org.waypanel.plugin.notify_client",
        "name": "Notify Client",
        "version": "1.0.0",
        "enabled": True,
        "index": 1,
        "container": "top-panel-center",
        "deps": ["notify_server", "css_generator", "status_notifier"],
        "description": about,
    }


def get_plugin_class():
    import re
    from ._utils import NotifyUtils
    from src.plugins.core._base import BasePlugin

    class NotificationPopoverPlugin(BasePlugin):
        def __init__(self, panel_instance):
            """
            Initializes the notification client plugin.

            Args:
                panel_instance: The main Waypanel application instance.
            """
            super().__init__(panel_instance)
            self.notify_utils = NotifyUtils(self.obj)
            self.notification_server = self.plugins["notify_server"]
            self.vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
            self.vbox.set_margin_top(10)
            self.vbox.set_margin_bottom(10)
            self.vbox.set_margin_start(10)
            self.show_messages = None
            self.cached_notifications = []

            self.add_hint(
                [
                    "Configuration for the Notification Client plugin, managing the history and UI."
                ],
                None,
            )
            self.max_notifications = self.get_plugin_setting_add_hint(
                ["max_notifications"],
                100,
                "The maximum number of recent notifications to display in the popover history.",
            )
            self.get_plugin_setting_add_hint(
                ["server_timeout"],
                10,
                "The timeout (in seconds) before a new notification disappears (server-side setting).",
            )
            self.popover_max_height = self.get_plugin_setting_add_hint(
                ["popover_max_height"],
                600,
                "The default height of the notification popover (in pixels).",
            )
            self.body_max_width_chars = self.get_plugin_setting_add_hint(
                ["body_max_width_chars"],
                50,
                "The maximum character width for the notification body text before it wraps in the popover.",
            )
            self.notification_icon_size = self.get_plugin_setting_add_hint(
                ["notification_icon_size"],
                64,
                "The size (in pixels) for the application icon displayed in a notification box.",
            )
            self.show_messages = self.get_plugin_setting_add_hint(
                ["show_messages"],
                True,
                "If True, the server shows messages; False enables Do Not Disturb mode (server-side setting).",
            )
            self.vbox.set_margin_end(10)
            self.notification_on_popover = {}
            self.notification_button = self.gtk.Button.new_from_icon_name(
                self.gtk_helper.set_widget_icon_name(
                    "notifications-applet-symbolic",
                    [
                        "notifications-applet-symbolic",
                        "org.gnome.Settings-notifications-symbolic",
                    ],
                )
            )
            self.notification_button.add_css_class("notification-panel-button")
            self.notification_button.set_tooltip_text("View Recent Notifications")
            self.notification_button.connect("clicked", self.open_popover_notifications)
            self.plugins["status_notifier"].tray_box.append(self.notification_button)
            self.gtk_helper.add_cursor_effect(self.notification_button)
            self.dnd_switch = self.gtk.Switch()
            self.dnd_switch.set_active(False)
            self.dnd_switch.connect("state-set", self.on_dnd_toggled)
            self.db_path = self.path_handler.get_data_path("db/notify/notifications.db")

        def on_start(self):
            """
            Pre-connects to the database and pre-loads notification data.
            """
            self.run_in_thread(self._preload_notifications)
            self.plugins["css_generator"].install_css("notify.css")

        def _preload_notifications(self):
            """Internal method to populate the cache in a background thread."""
            self.cached_notifications = self.fetch_last_notifications()
            self.logger.info(
                f"Preloaded {len(self.cached_notifications)} notifications."
            )

        def update_dnd_switch_state(self):
            """Update the Do Not Disturb switch state based on the server setting."""
            try:
                self.dnd_switch.set_active(not self.show_messages)
            except Exception as e:
                self.logger.error(f"Error updating DND switch state: {e}")

        def on_dnd_toggled(self, switch, state):
            """
            Callback when the Do Not Disturb switch is toggled.
            state: True means DND is ON (No messages)
            state: False means DND is OFF (Show messages)
            """
            new_show_messages = not state
            self.get_plugin_setting(
                ["show_messages"],
                new_show_messages,
            )
            self.set_plugin_setting(["show_messages"], new_show_messages)

            self.show_messages = new_show_messages
            self.logger.info(
                f"Do Not Disturb mode {'enabled' if state else 'disabled'}"
            )

        def fetch_last_notifications(self, limit=None):
            """
            Fetch the last notifications from the database.

            Args:
                limit: Maximum number of notifications to retrieve.
            """
            limit_val = limit if limit is not None else self.max_notifications
            try:
                if not self.os.path.exists(self.db_path):
                    self.logger.warning(f"Database file not found at {self.db_path}")
                    return []
                conn = self.sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                limit_int = int(limit_val)
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
                            "hints": self.json.loads(hints) if hints else {},
                            "timestamp": timestamp,
                        }
                    )
                return notifications
            except Exception as e:
                self.logger.error(f"Error fetching notifications from database: {e}")
                return []

        def _extract_first_uri_from_text(self, text: str) -> str | None:
            """
            Uses a regular expression to find and return the first URL in a string.

            Args:
                text: The string to search for URLs.
            """
            url_regex = r"(?:https?|ftp)://\S+|www\.\S+"
            matches = re.findall(url_regex, text)
            if matches:
                uri = matches[0].rstrip(".,;")
                return uri
            return None

        def on_launch_uri(self, uri: str):
            """
            Launches the specified URI and closes the popover.

            Args:
                uri: The URI string to open.
            """
            self.cmd.open_url(uri)
            if hasattr(self, "popover") and self.popover:
                self.popover.popdown()
            self.logger.info(f"Launching URI: {uri}")
            return True

        def on_launch_uri_clicked(self, button, uri: str):
            """
            Handler for the dedicated 'Open Link' button.

            Args:
                button: The GtkButton clicked.
                uri: The URI string to open.
            """
            self.on_launch_uri(uri)

        def on_notification_click(self, notification, widget):
            """
            Handle click action on a notification.

            Args:
                notification: The notification data dictionary.
                widget: The Gtk widget that received the click.
            """
            self.logger.info(f"Notification clicked: {notification.get('id')}")
            extracted_uri = self._extract_first_uri_from_text(
                notification.get("body", "")
            )
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

        def handle_default_action(self, notification):
            """
            Deprecated: Logic centralized in on_notification_click.

            Args:
                notification: The notification data dictionary.
            """
            self.on_notification_click(notification, None)

        def execute_default_action(self, action, notification):
            """
            Execute the default action specified in hints.

            Args:
                action: The action string to execute.
                notification: The notification data dictionary.
            """
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
            """
            Create a notification box.

            Args:
                notification: The notification data dictionary.
            """
            hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 30)
            hbox.add_css_class("notify-client-box")
            close_button = self.gtk.Button.new_from_icon_name("window-close-symbolic")
            close_button.set_tooltip_text("Close Notification")
            self.gtk_helper.add_cursor_effect(close_button)
            close_button.set_margin_start(10)
            close_button.connect(
                "clicked",
                lambda _: self.delete_notification(notification.get("id"), hbox),
            )
            self.update_widget_safely(hbox.append, close_button)
            left_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
            left_box.set_halign(self.gtk.Align.START)
            left_box.set_valign(self.gtk.Align.START)
            right_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
            right_box.set_halign(self.gtk.Align.START)
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
                icon.set_pixel_size(self.notification_icon_size)
                icon.set_halign(self.gtk.Align.START)
                icon.add_css_class("notification-icon")
                self.update_widget_safely(left_box.append, icon)
            app_label = self.gtk.Label(label=f"<b>{notification['app_name']}</b>")
            app_label.set_use_markup(True)
            app_label.set_halign(self.gtk.Align.START)
            self.update_widget_safely(left_box.append, app_label)
            summary_label = self.gtk.Label(label=notification["summary"])
            summary_label.set_wrap(True)
            summary_label.set_halign(self.gtk.Align.START)
            summary_label.add_css_class("notify-client-heading")
            self.update_widget_safely(right_box.append, summary_label)
            body_label = self.gtk.Label(label=notification["body"])
            body_label.set_wrap(True)
            body_label.set_max_width_chars(self.body_max_width_chars)
            body_label.set_halign(self.gtk.Align.START)
            self.update_widget_safely(right_box.append, body_label)
            body_label.add_css_class("notify-client-body-label")
            timestamp_label = self.gtk.Label(label=notification["timestamp"])
            timestamp_label.set_halign(self.gtk.Align.START)
            timestamp_label.add_css_class("notify-client-timestamp")
            self.update_widget_safely(right_box.append, timestamp_label)
            self.update_widget_safely(hbox.append, left_box)
            self.update_widget_safely(hbox.append, right_box)
            separator = self.gtk.Separator.new(self.gtk.Orientation.HORIZONTAL)
            self.update_widget_safely(self.vbox.append, hbox)
            self.update_widget_safely(self.vbox.append, separator)
            self.notification_on_popover[notification["id"]] = hbox
            return hbox

        def clear_all_notifications(self, *_) -> None:
            """Clear all notifications from the database and remove them from the UI."""
            try:
                conn = self.sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute("DELETE FROM notifications")
                conn.commit()  # Explicitly end the transaction

                conn.isolation_level = None
                cursor.execute("VACUUM")
                conn.isolation_level = ""  # Restore default behavior

                conn.close()

                child = self.vbox.get_first_child()
                while child:
                    next_child = child.get_next_sibling()
                    self.vbox.remove(child)
                    child = next_child

                self.notification_on_popover = {}
                self.cached_notifications = []
                self.logger.info("All notifications cleared and database vacuumed.")
            except Exception as e:
                self.logger.error(f"Error clearing notifications: {e}")

        def delete_notification(self, notification_id: int, notification_box) -> None:
            """
            Delete a notification from the database and remove it from the UI.

            Args:
                notification_id: ID of the notification to delete.
                notification_box: The GtkBox containing the notification.
            """
            try:
                conn = self.sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    "DELETE FROM notifications WHERE id = ?", (notification_id,)
                )
                conn.commit()

                conn.isolation_level = None
                cursor.execute("VACUUM")
                conn.isolation_level = ""

                conn.close()

                parent = notification_box.get_parent()
                if parent:
                    separator = notification_box.get_next_sibling()
                    parent.remove(notification_box)
                    if separator and isinstance(separator, self.gtk.Separator):
                        parent.remove(separator)

                if notification_id in self.notification_on_popover:
                    del self.notification_on_popover[notification_id]

                self.cached_notifications = [
                    n for n in self.cached_notifications if n["id"] != notification_id
                ]

                self.logger.info(
                    f"Notification {notification_id} deleted and database vacuumed."
                )
            except Exception as e:
                self.logger.error(f"Error deleting notification {notification_id}: {e}")

        def open_popover_notifications(self, *_) -> None:
            """Creates or updates the notification popover using cached data."""
            if not hasattr(self, "popover") or not self.popover:
                self.popover = self.gtk.Popover.new()
                self.main_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
                self.main_vbox.set_margin_top(10)
                self.main_vbox.set_margin_bottom(10)
                self.main_vbox.set_margin_start(10)
                self.main_vbox.set_margin_end(10)

                # Notifications Scrolled Area
                self.vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
                self.vbox.set_vexpand(True)

                scrolled_window = self.gtk.ScrolledWindow()
                scrolled_window.set_child(self.vbox)

                # Enable natural height AND width propagation
                scrolled_window.set_propagate_natural_height(True)
                scrolled_window.set_propagate_natural_width(True)

                scrolled_window.set_min_content_height(100)
                scrolled_window.set_max_content_height(self.popover_max_height)

                # Ensure the popover has a reasonable minimum width so it doesn't look cramped
                scrolled_window.set_min_content_width(300)

                scrolled_window.set_policy(
                    self.gtk.PolicyType.NEVER,
                    self.gtk.PolicyType.AUTOMATIC,
                )
                self.update_widget_safely(self.main_vbox.append, scrolled_window)

                # Bottom Controls Row
                bottom_box = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 10)
                bottom_box.set_margin_top(10)

                # Unified DND Toggle Button (Left)
                dnd_label = (
                    "Show Notifications"
                    if getattr(self, "dnd_enabled", False)
                    else "Do Not Disturb"
                )
                self.dnd_toggle_btn = self.gtk.Button(label=dnd_label)
                self.dnd_toggle_btn.add_css_class("notify-dnd-button")
                self.dnd_toggle_btn.connect("clicked", self.on_dnd_button_clicked)
                self.gtk_helper.add_cursor_effect(self.dnd_toggle_btn)

                # Clear All Button (Right)
                clear_button = self.gtk.Button(label="Clear All")
                clear_button.set_halign(self.gtk.Align.END)
                clear_button.set_hexpand(True)
                clear_button.connect(
                    "clicked", lambda _: self.clear_all_notifications()
                )
                clear_button.set_tooltip_text("Clear All Notifications")
                clear_button.add_css_class("notify-clear-button")
                self.gtk_helper.add_cursor_effect(clear_button)

                self.update_widget_safely(bottom_box.append, self.dnd_toggle_btn)
                self.update_widget_safely(bottom_box.append, clear_button)
                self.update_widget_safely(self.main_vbox.append, bottom_box)

                self.popover.set_child(self.main_vbox)

            if self.popover.get_parent():
                self.popover.unparent()

            # Clear existing widgets
            child = self.vbox.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.vbox.remove(child)
                child = next_child

            self.notification_on_popover = {}

            # Load notifications
            notifications = (
                self.cached_notifications
                if self.cached_notifications
                else self.fetch_last_notifications()
            )

            if not notifications:
                no_notify_label = self.gtk.Label(label="No recent notifications")
                no_notify_label.add_css_class("no-notifications-label")
                self.update_widget_safely(self.vbox.append, no_notify_label)
            else:
                for notification in notifications:
                    self.create_notification_box(notification)

            # Anchor and Show
            self.popover.set_parent(self.notification_button)
            self.popover.popup()
            self.run_in_thread(self._preload_notifications)

        def on_dnd_button_clicked(self, button) -> None:
            """Toggles DND state and updates the button label."""
            self.dnd_enabled = not getattr(self, "dnd_enabled", False)

            if self.dnd_enabled:
                button.set_label("Show Notifications")
            else:
                button.set_label("Do Not Disturb")

            self.on_dnd_toggled(None, self.dnd_enabled)

    return NotificationPopoverPlugin
