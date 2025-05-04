import os
from gi.repository import Gtk, GdkPixbuf
from PIL import Image
from io import BytesIO

import urllib.parse
import cairosvg
import base64

from src.plugins.core._base import BasePlugin

# TODO: allow hardcoded custom icon but add an option in the config too
CUSTOM_ICON = {"notify-send": "cs-notifications-symbolic"}


class NotifyUtils(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

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
            self.log_error(f"Error creating pixbuf: {e}")
            return None

    # Helper function to create a PNG from raw pixel data
    def create_png_from_pixel_data(self, width, height, pixel_data):
        # Create an image from raw pixel data
        img = Image.new("RGBA", (width, height))
        img.putdata(
            [tuple(pixel_data[i : i + 4]) for i in range(0, len(pixel_data), 4)]
        )

        # Save the image to a bytes buffer in PNG format
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def svg_to_pixbuf(self, svg_data):
        """
        Convert SVG data to a GdkPixbuf.Pixbuf.

        :param svg_data: The raw SVG content as bytes.
        :return: A GdkPixbuf.Pixbuf object or None if conversion fails.
        """
        try:
            # Convert SVG to PNG using cairosvg
            png_data = cairosvg.svg2png(bytestring=svg_data)

            # Load the PNG data into a GdkPixbuf
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(png_data)
            loader.close()
            return loader.get_pixbuf()
        except Exception as e:
            self.log_error(f"Error converting SVG to Pixbuf: {e}")
            return None

    def load_svg_from_data_uri(self, data_uri):
        """
        Load an icon from a data URI.

        :param data_uri: The data URI string.
        :return: A Gtk.Image widget or None if loading fails.
        """
        # Step 1: Decode the data URI
        svg_data = self.decode_data_uri(data_uri)
        if not svg_data:
            return None

        # Step 2: Convert SVG to Pixbuf
        pixbuf = self.svg_to_pixbuf(svg_data)
        if not pixbuf:
            return None

        # Step 3: Create a Gtk.Image from the Pixbuf
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        return image

    def load_png_from_data_uri(self, data_uri):
        """
        Load an icon from a PNG data URI or raw pixel data.

        :param data_uri: The data URI string or raw pixel data parameters.
        :return: A Gtk.Image widget or None if loading fails.
        """
        try:
            # Step 1: Check if the input is a data URI
            if isinstance(data_uri, str) and data_uri.startswith("data:image/png"):
                # Decode the data URI
                png_data = self.decode_data_uri(data_uri)
                if not png_data:
                    return None
            else:
                # Assume raw pixel data is provided as a dictionary or tuple
                width = data_uri.get("width", 0)
                height = data_uri.get("height", 0)
                pixel_data = data_uri.get("pixels", [])
                png_data = self.create_png_from_pixel_data(width, height, pixel_data)
                if not png_data:
                    return None

            # Step 2: Load the PNG data into a GdkPixbuf
            try:
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(png_data)
                loader.close()
                pixbuf = loader.get_pixbuf()
            except Exception as e:
                print(f"Error loading PNG into GdkPixbuf: {e}")
                return None

            # Step 3: Create a Gtk.Image from the Pixbuf
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            return image

        except Exception as e:
            print(f"Error in load_png_from_data_uri: {e}")
            return None

    def decode_data_uri(self, data_uri):
        """
        Decode a data URI and return the raw content.

        :param data_uri: The data URI string.
        :return: The decoded content as bytes.
        """
        try:
            # Parse the data URI
            header, encoded_data = data_uri.split(",", 1)
            if "base64" in header:
                # Decode base64-encoded data
                return base64.b64decode(encoded_data)
            else:
                # Percent-decode non-base64 data
                return urllib.parse.unquote(encoded_data).encode("utf-8")
        except Exception as e:
            print(f"Error decoding data URI: {e}")
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
        """Load the appropriate icon/image for a notification based on multiple cases."""
        # Extract necessary fields from the notification
        app_icon = notification.get("app_icon", "")
        app_name = notification.get("app_name", "").lower()
        hints = notification.get("hints", {})

        try:
            # Case 1: Check if hints contain raw image data
            if "image-data" in hints:
                image_data = hints["image-data"]

                # Validate the structure of image_data
                if isinstance(image_data, (list, tuple)) and len(image_data) == 5:
                    width, height, rowstride, has_alpha, pixels = image_data

                    # Validate individual components
                    if (
                        isinstance(width, int)
                        and isinstance(height, int)
                        and isinstance(rowstride, int)
                        and isinstance(has_alpha, bool)
                        and isinstance(pixels, (bytes, list, tuple))
                    ):
                        # Proceed to create GdkPixbuf
                        pixbuf = self.create_pixbuf_from_pixels(
                            width, height, rowstride, has_alpha, pixels
                        )
                        icon = Gtk.Image.new_from_pixbuf(pixbuf)
                        return icon  # Successfully loaded from image-data
                    else:
                        self.logger.error("Invalid image-data format: Incorrect types.")
                else:
                    # self.logger.error(f"Malformed image-data: {image_data}")
                    # too much log spam
                    pass

            # Case 2: Use app_icon as a file path or icon name
            if app_icon:
                if self.is_valid_path(app_icon):
                    try:
                        thumbnail_path = self.load_thumbnail(app_icon)
                        if thumbnail_path:
                            icon = Gtk.Image.new_from_file(thumbnail_path)
                        else:
                            icon = Gtk.Image.new_from_file(app_icon)
                        return icon  # Successfully loaded from file path
                    except Exception as e:
                        self.logger.error(f"Error loading app_icon from file: {e}")
                else:
                    try:
                        icon = Gtk.Image.new_from_icon_name(app_icon)
                        return icon  # Successfully loaded from icon name
                    except Exception as e:
                        self.logger.error(f"Error loading app_icon as icon name: {e}")

            # Case 3: Use app_name as the icon name
            if app_name:
                try:
                    if app_name not in CUSTOM_ICON:
                        icon = Gtk.Image.new_from_icon_name(app_name)
                    else:
                        icon = Gtk.Image.new_from_icon_name(CUSTOM_ICON[app_name])
                    return icon  # Successfully loaded from app_name
                except Exception as e:
                    self.logger.error(f"Error loading app_name as icon name: {e}")

            # Case 4: Fallback to a default icon
            return Gtk.Image.new_from_icon_name("image-missing")  # Final fallback icon

        except Exception as e:
            self.logger.error(f"Unexpected error while loading icon: {e}")
            return Gtk.Image.new_from_icon_name("message-new")  # Final fallback icon
