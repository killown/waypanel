import os
from gi.repository import Gtk, GdkPixbuf
from PIL import Image


class NotifyUtils:
    def __init__(self):
        pass

    def is_valid_path(self, path):
        return os.path.exists(path)

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

    def load_icon(self, notification):
        """
        Load the appropriate icon/image for a notification based on multiple cases.

        Args:
            notification (dict): The notification data containing app_icon, hints, app_name, etc.

        Returns:
            Gtk.Image: The loaded image/icon or a fallback image if none could be loaded.
        """
        # Extract necessary fields from the notification
        app_icon = notification.get("app_icon", "")
        hints = notification.get("hints", {})

        try:
            # Case 1: Check if hints contain raw image data
            if "image-data" in hints:
                try:
                    width, height, rowstride, has_alpha, pixels = hints["image-data"]
                    pixbuf = self.create_pixbuf_from_pixels(
                        width, height, rowstride, has_alpha, pixels
                    )
                    icon = Gtk.Image.new_from_pixbuf(pixbuf)
                    return icon  # Successfully loaded from image-data
                except Exception as e:
                    print(f"Error loading image-data: {e}")
                    # Fallback to other cases

            # Case 2: Check if app_icon is a valid file path
            if self.is_valid_path(app_icon):
                try:
                    thumbnail_path = self.load_thumbnail(
                        app_icon
                    )  # Optional: Use thumbnails if needed
                    if thumbnail_path:
                        icon = Gtk.Image.new_from_file(thumbnail_path)
                    else:
                        icon = Gtk.Image.new_from_file(app_icon)
                    return icon  # Successfully loaded from file path
                except Exception as e:
                    print(f"Error loading app_icon from file path: {e}")

            # Case 3: Use app_icon directly as an icon name
            if app_icon:
                try:
                    icon = Gtk.Image.new_from_icon_name(app_icon)
                    return icon  # Successfully loaded from icon name
                except Exception as e:
                    print(f"Error loading app_icon as icon name: {e}")

            # Case 4: Fallback to using app_name as the icon name
            app_name = notification.get("app_name", "image-missing").lower()
            icon = Gtk.Image.new_from_icon_name(app_name)
            return icon  # Fallback icon

        except Exception as e:
            print(f"Unexpected error while loading icon: {e}")
            return Gtk.Image.new_from_icon_name("image-missing")  # Final fallback icon
