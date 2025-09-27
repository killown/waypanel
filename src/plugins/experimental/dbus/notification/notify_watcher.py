import os
import sqlite3
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.plugins.core._base import BasePlugin
import logging

ENABLE_PLUGIN = True
DEPS = ["notify_client"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    return


def initialize_plugin(panel_instance):
    """Initialize the Notify Watcher Plugin."""
    if ENABLE_PLUGIN:
        watcher = NotifyWatcherPlugin(panel_instance)
        watcher.start_watching()
        return watcher


class NotifyWatcherPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.notify_client = None
        self.notification_button = None
        self.db_path = os.path.expanduser("~/.config/waypanel/notifications.db")
        self.logger = logging.getLogger(__name__)
        self.observer = None
        self.last_db_state = None

    def start_watching(self):
        """Start watching for notifications by monitoring the database file."""
        try:
            self.notify_client = self.obj.plugins.get("notify_client")
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

    def monitor_database(self):
        """Monitor the database file for changes using watchdog."""
        try:
            self.check_notifications()
            event_handler = DatabaseChangeHandler(self)
            self.observer = Observer()
            self.observer.schedule(
                event_handler, path=os.path.dirname(self.db_path), recursive=False
            )
            self.observer.start()
        except Exception as e:
            self.logger.error(f"Error setting up database monitoring: {e}")

    def check_notifications(self):
        """Check if there are any notifications in the database."""
        try:
            if not os.path.exists(self.db_path):
                has_notifications = False
            else:
                conn = sqlite3.connect(self.db_path)
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


class DatabaseChangeHandler(FileSystemEventHandler):
    """Handles file system events for the database file."""

    def __init__(self, plugin):
        self.plugin = plugin

    def on_modified(self, event):
        """Triggered when the database file is modified."""
        if event.src_path == self.plugin.db_path:
            self.plugin.logger.info(
                "Database file modified. Checking for notifications."
            )
            self.plugin.check_notifications()

    def about(self):
        """
        This plugin monitors a local notifications database file and
        automatically shows or hides a notification button based on
        whether new notifications are available.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this plugin is to create a dynamic visual
        indicator by linking a background process to a UI component
        from a separate plugin. It operates on three key principles:
        1.  **File System Monitoring**: The plugin uses the `watchdog`
            library to set up a listener on the notification database
            file. Instead of periodically polling the database, it
            reacts in real-time to file modification events, ensuring
            the UI is updated instantly when new data is written.
        2.  **State-Driven UI Updates**: It maintains an internal state
            variable (`self.last_db_state`) that represents whether
            notifications are present. When the database is modified,
            the plugin checks the current state and only updates the
            button's visibility if the state has genuinely changed.
            This prevents redundant UI operations.
        3.  **Cross-Plugin Interaction**: This plugin is "headless"
            in that it doesn't create its own UI element on the
            panel. Instead, it acts as a controller, retrieving a
            button object from the `notify_client` plugin and
            programmatically changing its visibility. This showcases
            a flexible, modular architecture.
        """
        return self.code_explanation.__doc__
