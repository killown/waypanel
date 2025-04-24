import os
import sqlite3
import asyncio
import json
from PIL import Image
from gi.repository import Gtk, GdkPixbuf
from pydbus.proxy import GLib
from waypanel.src.plugins.core._base import BasePlugin
from waypanel.src.plugins.experimental.dbus.notify_server import (
    NotificationDaemon,
)

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True

DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-center"  # Position: right side of the panel
    order = 10  # Order: determines the relative position among other plugins
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the Notification Popover Plugin."""
    if ENABLE_PLUGIN:
        return NotificationPopoverPlugin(panel_instance)


def run_server_in_background(panel_instance):
    """Start the notification server without blocking the main thread.

    Args:
        panel_instance: The main panel instance to pass to the NotificationDaemon.
    """

    async def _run_server():
        # Pass the panel_instance to the NotificationDaemon
        server = NotificationDaemon(panel_instance)
        await server.run()
        print("Notification server running in background")
        while True:  # Keep alive
            await asyncio.sleep(1)

    # Run in dedicated thread
    def _start_loop():
        asyncio.run(_run_server())

    import threading

    # Start the thread with daemon=True to ensure it exits when the main program exits
    thread = threading.Thread(target=_start_loop, daemon=True)
    thread.start()
    return thread


class NotificationPopoverPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger = self.obj.logger
        run_server_in_background(panel_instance)
        # Create a vertical box to hold notification details
        self.vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        self.vbox.set_margin_top(10)
        self.vbox.set_margin_bottom(10)
        self.vbox.set_margin_start(10)
        self.show_messages = None
        self.vbox.set_margin_end(10)
        self.notification_on_popover = {}
        self.notification_button = Gtk.Button.new_from_icon_name("liteupdatesnotify")
        self.notification_button.set_tooltip_text("View Recent Notifications")
        self.notification_button.connect("clicked", self.open_popover_notifications)

        # Define the main widget and action
        self.main_widget = (self.notification_button, "append")

        # Path to the notifications database
        self.db_path = os.path.expanduser("~/.config/waypanel/notifications.db")

    def update_dnd_switch_state(self):
        """Update the Do Not Disturb switch state based on the server setting."""
        try:
            show_messages = (
                self.config.get("notify", {})
                .get("server", {})
                .get("show_messages", True)
            )
            self.dnd_switch.set_active(
                not show_messages
            )  # Invert the value since DND is the opposite of showing messages
        except Exception as e:
            self.logger.error(f"Error updating DND switch state: {e}")

    def on_dnd_toggled(self, switch, state):
        """Callback when the Do Not Disturb switch is toggled."""
        new_show_messages = (
            not state
        )  # Invert the state to match the `show_messages` setting

        try:
            # Update the configuration
            if "notify" not in self.config:
                self.config["notify"] = {}
            if "server" not in self.config["notify"]:
                self.config["notify"]["server"] = {}

            self.config["notify"]["server"]["show_messages"] = new_show_messages

            # Save the updated configuration
            self.save_config()

            # Reload the configuration in the panel instance
            self.reload_config()

            self.logger.info(
                f"Do Not Disturb mode {'enabled' if state else 'disabled'}"
            )
        except Exception as e:
            self.logger.error(f"Error toggling Do Not Disturb mode: {e}")

    def fetch_last_notifications(self, limit=3):
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
                SELECT id, app_name, summary, body, app_icon, hints, timestamp
                FROM notifications
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            rows = cursor.fetchall()
            conn.close()

            notifications = []
            for row in rows:
                notification_id, app_name, summary, body, app_icon, hints, timestamp = (
                    row
                )
                if notification_id in self.notification_on_popover:
                    continue

                notifications.append(
                    {
                        "id": notification_id,
                        "app_name": app_name,
                        "summary": summary,
                        "body": body,
                        "app_icon": app_icon,
                        # "hints": json.loads(hints)
                        # if hints
                        # else {},  # Deserialize hints
                        "timestamp": timestamp,
                    }
                )
            return notifications
        except Exception as e:
            self.logger.error_handler.handle(
                f"Error fetching notifications from database: {e}"
            )

    def load_thumbnail(self, image_path, max_size=(64, 64)):
        """
        Load and resize an image to create a thumbnail.
        :param image_path: Path to the original image file.
        :param max_size: Maximum dimensions (width, height) for the thumbnail.
        :return: Path to the temporary thumbnail file.
        """
        try:
            # Open the image using Pillow
            with Image.open(image_path) as img:
                # Resize the image while maintaining aspect ratio
                img.thumbnail(max_size)

                # Create a temporary file to store the thumbnail
                thumbnail_path = "/tmp/thumbnail.png"
                img.save(thumbnail_path, format="PNG")

            return thumbnail_path
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return None

    def create_pixbuf_from_pixels(self, width, height, rowstride, has_alpha, pixels):
        """
        Create a GdkPixbuf.Pixbuf from raw pixel data.
        :param width: Width of the image in pixels.
        :param height: Height of the image in pixels.
        :param rowstride: Number of bytes per row.
        :param has_alpha: Whether the image has an alpha channel (True/False).
        :param pixels: Raw pixel data (list, array, or bytes).
        :return: GdkPixbuf.Pixbuf object.
        """
        try:
            # Validate and convert pixels to bytes
            if isinstance(pixels, bytes):
                pixel_data = pixels
            elif isinstance(pixels, (list, tuple)):
                # Ensure all values are integers in the range 0–255
                pixel_data = bytes(pixels)
            elif isinstance(pixels, str):
                # Parse the string into a list of integers
                pixel_data = bytes([int(x.strip()) for x in pixels.split(",")])
            else:
                raise ValueError(
                    "Unsupported type for pixels. Expected bytes, list, tuple, or string."
                )

            # Create the GdkPixbuf
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                pixel_data,
                GdkPixbuf.Colorspace.RGB,
                has_alpha,
                8,  # Bits per sample
                width,
                height,
                rowstride,
                None,  # Destroy function (None if no cleanup is needed)
            )
            return pixbuf

        except Exception as e:
            print(f"Error creating pixbuf: {e}")
            return None

    def create_notification_box(self, notification):
        """Create a notification box with an optional image on the left, content on the right, and a close button.

        :param notification: Dictionary containing notification details.
        :param notification_box: The parent box to which the notification will be added.
        :return: Gtk.Box containing the notification content.
        """

        def load_icon():
            """Load the icon/image and handle errors gracefully."""
            app_icon = notification.get("app_icon")
            hints = notification.get("hints", {})
            try:
                # Case 1: Check if hints contain raw image data
                if "image-data" in hints:
                    width, height, rowstride, has_alpha, pixels = hints["image-data"]
                    pixbuf = self.create_pixbuf_from_pixels(
                        width, height, rowstride, has_alpha, pixels
                    )
                    return Gtk.Image.new_from_pixbuf(pixbuf)

                # Case 2: Check if app_icon is a valid file path
                elif app_icon and os.path.isfile(app_icon):
                    thumbnail_path = self.load_thumbnail(app_icon)
                    if thumbnail_path:
                        return Gtk.Image.new_from_file(thumbnail_path)

                # Fallback to a default icon
                return Gtk.Image.new_from_icon_name("image-missing")

            except Exception as e:
                # Log the error and fallback to a default icon
                print(f"Error loading app icon: {e}")
                return Gtk.Image.new_from_icon_name("image-missing")

        # Create a horizontal box to hold the image and text content
        hbox = Gtk.Box.new(
            Gtk.Orientation.HORIZONTAL, 10
        )  # 10px spacing between columns

        # Left column: Icon/Image container
        left_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        left_box.set_halign(Gtk.Align.START)
        left_box.set_valign(Gtk.Align.START)

        # Right column: Text content container
        right_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        right_box.set_halign(Gtk.Align.START)

        # Load the icon/image
        icon = load_icon()
        if icon:
            icon.set_pixel_size(64)  # Set a fixed size for the icon
            icon.set_halign(Gtk.Align.START)
            icon.add_css_class("notification-icon")
            left_box.append(icon)

        # App Name
        app_label = Gtk.Label(label=f"<b>{notification['app_name']}</b>")
        app_label.set_use_markup(True)
        app_label.set_halign(Gtk.Align.START)
        right_box.append(app_label)

        # Summary
        summary_label = Gtk.Label(label=notification["summary"])
        summary_label.set_wrap(True)
        summary_label.set_halign(Gtk.Align.START)
        summary_label.add_css_class("heading")
        right_box.append(summary_label)

        # Body
        body_label = Gtk.Label(label=notification["body"])
        body_label.set_wrap(True)
        body_label.set_max_width_chars(50)
        body_label.set_halign(Gtk.Align.START)
        right_box.append(body_label)

        # Timestamp
        timestamp_label = Gtk.Label(label=notification["timestamp"])
        timestamp_label.set_halign(Gtk.Align.START)
        right_box.append(timestamp_label)

        # Add left and right boxes to the horizontal box
        hbox.append(left_box)
        hbox.append(right_box)

        # Add a close button
        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_button.set_tooltip_text("Close Notification")
        close_button.set_margin_start(10)  # Add spacing between content and button
        close_button.connect(
            "clicked", lambda _: self.delete_notification(notification["id"], hbox)
        )
        hbox.append(close_button)

        # Add the horizontal box to the notification_box
        self.vbox.append(hbox)
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
                    SELECT id, app_name, summary, body, app_icon, hints, timestamp
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
                    "hints": json.loads(row[5]),
                    "timestamp": row[6],
                }

                vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
                vbox.set_margin_top(10)
                vbox.set_margin_bottom(10)
                vbox.set_margin_start(10)
                vbox.set_margin_end(10)

                # Append the notification to the UI
                self.create_notification_box(notification)

        except Exception as e:
            print(f"Error appending next oldest notification: {e}")

    def open_popover_notifications(self, *_):
        if not hasattr(self, "popover") or not self.popover:
            self.popover = Gtk.Popover.new()
            self.vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            self.popover.set_child(self.vbox)
        child = self.vbox.get_first_child()
        while child:
            next_child = (
                child.get_next_sibling()
            )  # Get the next sibling before removing
            self.vbox.remove(child)  # Remove the current child
            child = next_child  # Move to the next child

        notifications = self.fetch_last_notifications()
        if not notifications:
            self.logger.info("No notifications to display.")
            return

        for notification in notifications:
            self.create_notification_box(notification)

        clear_button = Gtk.Button(label="Clear")
        clear_button.connect("clicked", lambda _: self.clear_all_notifications)
        clear_button.set_tooltip_text("Clear All Notifications")
        clear_button.set_margin_start(10)
        self.vbox.append(clear_button)
        # Add Do Not Disturb switch
        self.dnd_switch = Gtk.Switch()
        self.dnd_switch.set_active(False)
        self.dnd_switch.connect("state-set", self.on_dnd_toggled)

        # Add a label for the switch
        dnd_label = Gtk.Label(label="Do Not Disturb")
        dnd_label.set_halign(Gtk.Align.START)
        dnd_label.set_margin_end(10)

        # Create a horizontal box to hold the label and switch
        dnd_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)
        dnd_box.append(dnd_label)
        dnd_box.append(self.dnd_switch)

        # Add the Do Not Disturb box to the vertical layout
        self.vbox.append(dnd_box)

        # Initialize the state based on the current server setting
        self.update_dnd_switch_state()

        self.popover.set_parent(self.notification_button)
        self.popover.popup()
