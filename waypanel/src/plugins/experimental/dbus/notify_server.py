import os
import sqlite3
import json
import time
from pydbus import SessionBus
from gi.repository import Gtk, GLib, Gio
from pydbus.generic import signal
from gi.repository import Gtk, Gtk4LayerShell as LayerShell
import toml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from waypanel.src.plugins.core._base import BasePlugin


class NotificationDaemon(BasePlugin):
    """
    DBus Notification Daemon implementation with database storage and GTK4 popups.
    """

    # Define DBus signals
    NotificationClosed = signal()
    ActionInvoked = signal()

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        # Connect to the session bus
        self.bus = SessionBus()
        self.layer_shell = LayerShell
        self.last_modified = None
        self.timeout = (
            self.config.get("notify", {}).get("server", {}).get("timeout", 10)
        )
        self.show_messages = (
            self.config.get("notify", {}).get("server", {}).get("show_messages", True)
        )

        # Define the DBus introspection XML
        self.introspection_xml = """
        <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
            "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
        <node name="/org/freedesktop/Notifications">
            <interface name="org.freedesktop.Notifications">
                <method name="GetCapabilities">
                    <arg direction="out" name="capabilities" type="as"/>
                </method>
                <method name="Notify">
                    <arg direction="in" name="app_name" type="s"/>
                    <arg direction="in" name="replaces_id" type="u"/>
                    <arg direction="in" name="app_icon" type="s"/>
                    <arg direction="in" name="summary" type="s"/>
                    <arg direction="in" name="body" type="s"/>
                    <arg direction="in" name="actions" type="as"/>
                    <arg direction="in" name="hints" type="a{sv}"/>
                    <arg direction="in" name="expire_timeout" type="i"/>
                    <arg direction="out" name="id" type="u"/>
                </method>
                <method name="CloseNotification">
                    <arg direction="in" name="id" type="u"/>
                </method>
                <method name="GetServerInformation">
                    <arg direction="out" name="name" type="s"/>
                    <arg direction="out" name="vendor" type="s"/>
                    <arg direction="out" name="version" type="s"/>
                    <arg direction="out" name="spec_version" type="s"/>
                </method>
                <signal name="NotificationClosed">
                    <arg name="id" type="u"/>
                    <arg name="reason" type="u"/>
                </signal>
                <signal name="ActionInvoked">
                    <arg name="id" type="u"/>
                    <arg name="action_key" type="s"/>
                </signal>
            </interface>
        </node>
        """

        # Verify the XML is valid
        try:
            Gio.DBusNodeInfo.new_for_xml(self.introspection_xml)
            print("Introspection XML parsed successfully.")
        except Exception as e:
            print(f"Error parsing introspection XML: {e}")
            raise

        # Register the service
        self.bus.publish(
            "org.freedesktop.Notifications",
            ("/org/freedesktop/Notifications", self, self.introspection_xml),
        )

        # Initialize the database
        self.db_path = self._initialize_db()

        # Store notifications
        self.notifications = {}
        self.next_id = 1

        # Initialize GTK application for popups
        self.app = Gtk.Application(application_id="com.example.NotificationPopup")
        self.app.connect("activate", self.on_activate)

        print("Notification daemon started. Listening for notifications...")

    def notify_reload_config(self):
        self.config = self.load_config()
        self.show_messages = (
            self.config.get("notify", {}).get("server", {}).get("show_messages", True)
        )
        self.timeout = (
            self.config.get("notify", {}).get("server", {}).get("timeout", 10)
        )

    def load_config(self):
        config_path = os.path.expanduser("~/.config/waypanel/waypanel.toml")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return toml.load(f)
        return {}

    def _initialize_db(self):
        """
        Initialize the SQLite database to store notifications.
        :return: Path to the database file.
        """
        db_path = os.path.expanduser("~/.config/waypanel/notifications.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    body TEXT,
                    app_icon TEXT,
                    actions TEXT,
                    hints JSON,
                    expire_timeout INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
            print(f"Database initialized at {db_path}")
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise

        return db_path

    def _save_notification_to_db(self, notification):
        """
        Save a notification to the database.
        :param notification: Dictionary containing notification details.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO notifications (
                    app_name, summary, body, app_icon, actions, hints, expire_timeout
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    notification["app_name"],
                    notification["summary"],
                    notification["body"],
                    notification["app_icon"],
                    ",".join(notification["actions"]),
                    json.dumps(notification["hints"]),
                    notification["expire_timeout"],
                ),
            )
            conn.commit()
            conn.close()
            print("Notification saved to database.")
        except Exception as e:
            print(f"Error saving notification to database: {e}")

    def close_notification(self, id, reason):
        """
        Close a notification and emit the NotificationClosed signal.
        """
        if id in self.notifications:
            print(f"Closing notification {id} with reason {reason}")
            del self.notifications[id]

    def Notify(
        self,
        app_name,
        replaces_id,
        app_icon,
        summary,
        body,
        actions,
        hints,
        expire_timeout,
    ):
        """
        Handle incoming notifications.
        :param app_name: Name of the application sending the notification.
        :param replaces_id: ID of the notification to replace (0 if none).
        :param app_icon: Icon associated with the notification.
        :param summary: Summary text of the notification.
        :param body: Body text of the notification.
        :param actions: List of actions (action_id, label).
        :param hints: Dictionary of hints.
        :param expire_timeout: Timeout in milliseconds (-1 for default).
        :return: ID of the new notification.
        """
        # Generate a unique ID
        notification_id = (
            replaces_id if replaces_id != 0 else len(self.notifications) + 1
        )

        # Store the notification
        notification = {
            "app_name": app_name,
            "summary": summary,
            "body": body,
            "app_icon": app_icon,
            "actions": actions,
            "hints": hints,
            "expire_timeout": expire_timeout,
        }
        self.notifications[notification_id] = notification

        # Save the notification to the database
        self._save_notification_to_db(notification)

        # Print the notification details
        print(f"Received notification {notification_id}:")
        print(f"  App: {app_name}")
        print(f"  Summary: {summary}")
        print(f"  Body: {body}")
        print(f"  Icon: {app_icon}")

        # Show a popup for the notification
        GLib.idle_add(self.show_popup, notification)

        # Emit the NotificationClosed signal after the timeout
        if expire_timeout > 0:
            GLib.timeout_add(
                expire_timeout, self.close_notification, notification_id, 1
            )

        return notification_id

    def show_popup(self, notification):
        """
        Show a GTK4 popup for the notification using LayerShell.
        :param notification: Dictionary containing notification details.
        """
        self.notify_reload_config()
        if not self.show_messages:
            self.logger.info("Do Not Disturb mode is active. Notification suppressed.")
            return

        window_width = 300
        window_height = 100
        output_w = self.ipc.get_focused_output()["geometry"]["width"]
        center_popup_position = (output_w - window_width) // 2
        top_popup_position = 32
        new_width_position = (
            self.config.get("notify", {})
            .get("server", {})
            .get("popup_position_x", False)
        )
        new_height_position = (
            self.config.get("notify", {})
            .get("server", {})
            .get("popup_position_y", False)
        )
        if new_width_position:
            center_popup_position = new_width_position
        if new_height_position:
            top_popup_position = new_height_position

        # Create a new window for the popup
        window = Gtk.Window()
        window.add_css_class("notify-window")
        self.layer_shell.init_for_window(window)
        self.layer_shell.set_layer(
            window, self.layer_shell.Layer.TOP
        )  # Set the popup to the top layer
        self.layer_shell.set_anchor(
            window, self.layer_shell.Edge.TOP, True
        )  # Anchor to the top of the screen
        self.layer_shell.set_anchor(
            window, self.layer_shell.Edge.RIGHT, True
        )  # Anchor to the right of the screen
        self.layer_shell.set_margin(
            window, self.layer_shell.Edge.TOP, top_popup_position
        )  # Add margin from the top
        self.layer_shell.set_margin(
            window, self.layer_shell.Edge.RIGHT, center_popup_position
        )  # Add margin from the right

        # Center the popup horizontally by anchoring to both left and right edges

        # Create the content of the popup
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.add_css_class("notify-server-vbox")

        # Icon
        if notification["app_icon"]:
            icon = Gtk.Image.new_from_file(notification["app_icon"])
            icon.set_pixel_size(48)
            vbox.append(icon)

        # Summary
        summary_label = Gtk.Label(label=notification["summary"])
        summary_label.add_css_class("notify-server-summary-label")
        vbox.append(summary_label)

        # Body
        body_label = Gtk.Label(label=notification["body"])
        body_label.add_css_class("notify-server-body-label")
        body_label.set_wrap(True)
        body_label.set_halign(Gtk.Align.START)
        vbox.append(body_label)

        # Close button
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _: window.close())
        vbox.append(close_button)

        # Set the content of the window
        window.set_child(vbox)
        window.set_default_size(
            window_width, window_height
        )  # Set default size for the popup

        # Add CSS classes for styling
        vbox.add_css_class("notification-box")
        summary_label.add_css_class("notification-summary")
        body_label.add_css_class("notification-body")

        # Present the window
        window.present()

        # Automatically close the popup after self.timeout seconds
        GLib.timeout_add_seconds(self.timeout, lambda: window.close())

    def on_activate(self, app):
        """
        Callback when the GTK application is activated.
        """
        pass

    def CloseNotification(self, id):
        """
        Close a notification.
        :param id: ID of the notification to close.
        """
        if id in self.notifications:
            self.close_notification(id, 3)
        else:
            print(f"Attempted to close non-existent notification {id}")

    def GetCapabilities(self):
        """
        Return the capabilities of the notification daemon.
        :return: List of capabilities.
        """
        return ["actions", "body", "icon-static"]

    def GetServerInformation(self):
        """
        Return information about the notification server.
        :return: Tuple of (name, vendor, version, spec_version).
        """
        return ("Python Notification Daemon", "Example", "1.0", "1.2")

    async def run(self):
        """
        Start the main loop to listen for DBus signals.
        """
        loop = GLib.MainLoop()
        try:
            loop.run()
        except KeyboardInterrupt:
            print("Stopping notification daemon...")
            loop.quit()
