import os
import sqlite3
import asyncio
import json
from PIL import Image
from gi.repository import Gtk, GdkPixbuf
from pydbus.proxy import GLib
from waypanel.src.plugins.core._base import BasePlugin
from waypanel.src.plugins.experimental.dbus_notifications.notify_server import (
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


def run_server_in_background():
    """Start the clipboard server without blocking main thread"""

    async def _run_server():
        server = NotificationDaemon()
        await server.run()
        print("Notification server running in background")
        while True:  # Keep alive
            await asyncio.sleep(1)

    # Run in dedicated thread
    def _start_loop():
        asyncio.run(_run_server())

    import threading

    thread = threading.Thread(target=_start_loop, daemon=True)
    thread.start()
    return thread


server_thread = run_server_in_background()


class NotificationPopoverPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger = self.obj.logger

        # Create the button to open the popover
        self.notification_button = Gtk.Button.new_from_icon_name(
            "preferences-system-notifications-symbolic"
        )
        self.notification_button.set_tooltip_text("View Recent Notifications")
        self.notification_button.connect("clicked", self.open_popover_notifications)

        # Define the main widget and action
        self.main_widget = (self.notification_button, "append")

        # Path to the notifications database
        self.db_path = os.path.expanduser("~/.config/waypanel/notifications.db")

    def fetch_last_notifications(self):
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
            cursor.execute("""
                SELECT id, app_name, summary, body, app_icon, hints, timestamp
                FROM notifications
                ORDER BY timestamp DESC
                LIMIT 3
            """)
            rows = cursor.fetchall()
            conn.close()

            notifications = []
            for row in rows:
                notification_id, app_name, summary, body, app_icon, hints, timestamp = (
                    row
                )
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

    def create_notification_box(self, notification, notification_box):
        """
        Display a notification with an icon or thumbnail.
        :param notification: Dictionary containing notification details.
        :param notification_box: The box to which the notification content will be added.
        :return: Gtk.Box containing the notification content.
        """

        def load_icon_idle():
            """Load the icon in an idle callback to avoid blocking the main thread."""
            app_icon = notification.get("app_icon")
            hints = notification.get("hints", {})
            icon = None

            try:
                # Check if hints contain raw image data
                if "image-data" in hints:
                    # Extract image data from hints and create a GdkPixbuf
                    width, height, rowstride, has_alpha, pixels = hints["image-data"]
                    # FIXME: still not working with images from hints
                    pixbuf = self.create_pixbuf_from_pixels(
                        width, height, rowstride, has_alpha, pixels
                    )
                    icon = Gtk.Image.new_from_pixbuf(pixbuf)

                # Otherwise, check if app_icon is a file path
                elif app_icon and os.path.isfile(app_icon):
                    # Generate a thumbnail for the image
                    thumbnail_path = self.load_thumbnail(app_icon)
                    if thumbnail_path:
                        icon = Gtk.Image.new_from_file(thumbnail_path)

                # Fallback to a default icon if no valid icon is found
                if not icon:
                    icon = Gtk.Image.new_from_icon_name("image-missing")

                # Set the icon size and alignment
                icon.set_pixel_size(64)
                icon.set_halign(Gtk.Align.START)
                icon.add_css_class("notification-icon")

                # Append the icon to the notification box
                GLib.idle_add(notification_box.append, icon)

            except Exception as e:
                # Log the error and fallback to a default icon
                print(f"Error loading app icon: {e}")
                GLib.idle_add(
                    notification_box.append,
                    Gtk.Image.new_from_icon_name("image-missing"),
                )

        # Create the notification box
        notification_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)

        # Schedule the icon loading in an idle callback
        GLib.idle_add(load_icon_idle)

        return notification_box

    def open_popover_notifications(self, *_):
        """Open a popover to display the last 3 notifications."""
        notifications = self.fetch_last_notifications()
        if not notifications:
            self.logger.info("No notifications to display.")
            return

        # Create a new popover
        popover = Gtk.Popover.new()
        popover.set_has_arrow(False)
        popover.set_autohide(True)

        # Create a vertical box to hold notification details
        vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        # Add each notification to the popover
        for notification in notifications:
            notification_box = self.create_notification_box(notification, vbox)

            # Notification Details (Vertical Box)
            details_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)

            # App Name
            app_label = Gtk.Label(label=f"<b>{notification['app_name']}</b>")
            app_label.set_use_markup(True)
            app_label.set_halign(Gtk.Align.START)
            details_box.append(app_label)

            # Summary
            summary_label = Gtk.Label(label=notification["summary"])
            summary_label.set_halign(Gtk.Align.START)
            summary_label.add_css_class("heading")
            details_box.append(summary_label)

            # Body
            body_label = Gtk.Label(label=notification["body"])
            body_label.set_halign(Gtk.Align.START)
            body_label.set_wrap(True)
            details_box.append(body_label)

            # Timestamp
            timestamp_label = Gtk.Label(
                label=f"<small>{notification['timestamp']}</small>"
            )
            timestamp_label.set_use_markup(True)
            timestamp_label.set_halign(Gtk.Align.START)
            details_box.append(timestamp_label)

            # Add details box to the notification box
            notification_box.append(details_box)

            # Separator
            separator = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
            notification_box.append(separator)

            vbox.append(notification_box)

        # Add a close button
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _: popover.popdown())
        vbox.append(close_button)

        # Set the popover content
        popover.set_child(vbox)

        # Show the popover
        popover.set_parent(self.notification_button)
        popover.popup()
