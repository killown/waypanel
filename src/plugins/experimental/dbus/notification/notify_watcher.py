def get_plugin_metadata(_):
    about = """
            This plugin monitors a local notifications database file and
            automatically shows or hides a notification button based on
            whether new notifications are available.
            """
    return {
        "id": "org.waypanel.plugin.notify_watcher",
        "name": "Notify Watcher",
        "version": "1.0.0",
        "enabled": True,
        "deps": ["notify_client"],
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class NotifyWatcherPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.notify_client = None
            self.notification_button = None
            self.db_path = self.path_handler.get_data_path("db/notify/notifications.db")
            self.gio_file = None
            self.gio_monitor = None
            self._last_mod_time = 0.0
            self.last_db_state = None

        def on_start(self):
            self.start_watching()

        def __del__(self):
            if self.gio_monitor:
                self.gio_monitor.cancel()

        def start_watching(self):
            """Start watching for notifications by monitoring the database file."""
            try:
                self.notify_client = self.plugin_loader.plugins.get("notify_client")
                if not self.notify_client:
                    self.logger.error("Notify client plugin is not loaded.")
                    return
                self.notification_button = getattr(
                    self.notify_client, "notification_button", None
                )
                if not self.notification_button:
                    self.logger.error("Notification button not found in notify_client.")
                    return
                self.monitor_database()
            except Exception as e:
                self.logger.error(f"Error initializing Notify Watcher Plugin: {e}")

        def _on_db_file_changed(self, monitor, file, other_file, event_type):
            if event_type in (
                self.gio.FileMonitorEvent.CHANGES_DONE_HINT,
                self.gio.FileMonitorEvent.MOVED,
                self.gio.FileMonitorEvent.CHANGED,
            ):
                try:
                    current_mod_time = self.os.path.getmtime(self.db_path)
                    if current_mod_time > self._last_mod_time:
                        self._last_mod_time = current_mod_time
                        self.glib.idle_add(self.check_notifications)
                except Exception as e:
                    self.logger.error(f"Error handling DB change: {e}")

        def monitor_database(self):
            """Monitor the database file for changes."""
            try:
                self.check_notifications()
                self.gio_file = self.gio.File.new_for_path(self.db_path)
                self.gio_monitor = self.gio_file.monitor_file(
                    self.gio.FileMonitorFlags.NONE, None
                )
                self.gio_monitor.connect("changed", self._on_db_file_changed)
                self._last_mod_time = self.os.path.getmtime(self.db_path)
            except Exception as e:
                self.logger.error(f"Error setting up database monitoring: {e}")

        def check_notifications(self):
            """Check if there are any notifications in the database."""
            try:
                if not self.os.path.exists(self.db_path):
                    has_notifications = False
                else:
                    conn = self.sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM notifications")
                    count = cursor.fetchone()[0]
                    conn.close()
                    has_notifications = count > 0
                if has_notifications != self.last_db_state:
                    self.last_db_state = has_notifications
                    self.update_button_visibility(has_notifications)
            except Exception as e:
                self.logger.error(f"Error checking database for notifications: {e}")

        def update_button_visibility(self, visible):
            """Update the visibility of the notification button."""
            try:
                if self.notification_button:
                    if visible:
                        self.notification_button.set_visible(True)
                        self.logger.info("Notification button is now visible.")
                    else:
                        self.notification_button.set_visible(False)
                        self.logger.info("Notification button is now hidden.")
            except Exception as e:
                self.logger.error(f"Error updating button visibility: {e}")

        def log_error(self, message):
            """Log an error message."""
            self.logger.error(message)

    return NotifyWatcherPlugin
