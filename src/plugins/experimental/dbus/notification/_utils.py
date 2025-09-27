import os
from gi.repository import Gtk, GdkPixbuf
from PIL import Image
from io import BytesIO
from typing import Optional, Dict, Any, Union, List, Tuple
import urllib.parse
import cairosvg
import base64
from src.plugins.core._base import BasePlugin

CUSTOM_ICON = {"notify-send": "cs-notifications-symbolic"}


class NotifyUtils(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

    def is_valid_path(self, path):
        return os.path.exists(path)

    def create_pixbuf_from_pixels(
        self,
        width: int,
        height: int,
        rowstride: int,
        has_alpha: bool,
        pixels: Union[bytes, List[int], Tuple[int, ...], str],
    ) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Create a GdkPixbuf.Pixbuf from raw pixel data.
        :param width: Width of the image in pixels.
        :param height: Height of the image in pixels.
        :param rowstride: Number of bytes per row.
        :param has_alpha: Whether the image has an alpha channel (True/False).
        :param pixels: Raw pixel data as bytes, list/tuple of integers, or comma-separated string.
        :return: GdkPixbuf.Pixbuf object or None on failure.
        """
        try:
            if isinstance(pixels, bytes):
                pixel_data = pixels
            elif isinstance(pixels, (list, tuple)):
                pixel_data = bytes(pixels)
            elif isinstance(pixels, str):
                pixel_data = bytes([int(x.strip()) for x in pixels.split(",")])
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                pixel_data,  # pyright: ignore
                GdkPixbuf.Colorspace.RGB,
                has_alpha,
                8,
                width,
                height,
                rowstride,
                None,
            )
            return pixbuf
        except Exception as e:
            self.logger.error(f"Error creating pixbuf: {e}")
            return None

    def create_png_from_pixel_data(
        self, width: int, height: int, pixel_data: bytes
    ) -> Optional[bytes]:
        img = Image.new("RGBA", (width, height))
        img.putdata(
            [tuple(pixel_data[i : i + 4]) for i in range(0, len(pixel_data), 4)]
        )
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def svg_to_pixbuf(self, svg_data: bytes) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Convert SVG data to a GdkPixbuf.Pixbuf.
        :param svg_data: The raw SVG content as bytes.
        :return: A GdkPixbuf.Pixbuf object or None if conversion fails.
        """
        try:
            png_data = cairosvg.svg2png(bytestring=svg_data)
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            if png_data:
                loader.write(png_data)
                loader.close()
                return loader.get_pixbuf()
            else:
                self.logger.info("svg to pixbuf: no png data found")
        except Exception as e:
            self.logger.error(f"Error converting SVG to Pixbuf: {e}")
            return None

    def load_svg_from_data_uri(self, data_uri) -> Optional[Gtk.Image]:
        """
        Load an icon from a data URI.
        :param data_uri: The data URI string.
        :return: A Gtk.Image widget or None if loading fails.
        """
        svg_data = self.decode_data_uri(data_uri)
        if not svg_data:
            return None
        pixbuf = self.svg_to_pixbuf(svg_data)
        if not pixbuf:
            return None
        return Gtk.Image.new_from_pixbuf(pixbuf)

    def load_png_from_data_uri(self, data_uri) -> Optional[Gtk.Image]:
        """
        Load an icon from a PNG data URI or raw pixel data.
        :param data_uri: The data URI string or raw pixel data parameters.
        :return: A Gtk.Image widget or None if loading fails.
        """
        try:
            if isinstance(data_uri, str) and data_uri.startswith("data:image/png"):
                png_data = self.decode_data_uri(data_uri)
                if not png_data:
                    return None
            else:
                width = data_uri.get("width", 0)  # pyright: ignore
                height = data_uri.get("height", 0)  # pyright: ignore
                pixel_data = data_uri.get("pixels", [])  # pyright: ignore
                png_data = self.create_png_from_pixel_data(width, height, pixel_data)
                if not png_data:
                    return None
            try:
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(png_data)
                loader.close()
                pixbuf = loader.get_pixbuf()
            except Exception as e:
                print(f"Error loading PNG into GdkPixbuf: {e}")
                return None
            return Gtk.Image.new_from_pixbuf(pixbuf)
        except Exception as e:
            print(f"Error in load_png_from_data_uri: {e}")
            return None

    def decode_data_uri(self, data_uri) -> Optional[bytes]:
        """
        Decode a data URI and return the raw content.
        :param data_uri: The data URI string.
        :return: The decoded content as bytes.
        """
        try:
            header, encoded_data = data_uri.split(",", 1)
            if "base64" in header:
                return base64.b64decode(encoded_data)
            else:
                return urllib.parse.unquote(encoded_data).encode("utf-8")
        except Exception as e:
            print(f"Error decoding data URI: {e}")
            return None

    def load_thumbnail(self, image_path, max_size=(64, 64)) -> Optional[str]:
        """
        Load and resize an image to create a thumbnail.
        :param image_path: Path to the original image file.
        :param max_size: Maximum dimensions (width, height) for the thumbnail.
        :return: Path to the temporary thumbnail file.
        """
        try:
            with Image.open(image_path) as img:
                img.thumbnail(max_size)
                thumbnail_path = "/tmp/thumbnail.png"
                img.save(thumbnail_path, format="PNG")
                return thumbnail_path
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return None

    def load_icon(self, notification: Dict[str, Any]) -> Optional[Gtk.Image]:
        """Load the appropriate icon/image for a notification based on multiple cases."""
        app_icon = notification.get("app_icon", "").lower()
        app_icon_from_name = notification.get("app_name", "").lower().replace(" ", "-")
        app_icon_from_name = self.gtk_helper.get_icon(app_icon_from_name, "", "")
        hints = notification.get("hints", {})
        try:
            if "image-data" in hints:
                image_data = hints["image-data"]
                if isinstance(image_data, (list, tuple)) and len(image_data) == 5:
                    width, height, rowstride, has_alpha, pixels = image_data
                    if (
                        isinstance(width, int)
                        and isinstance(height, int)
                        and isinstance(rowstride, int)
                        and isinstance(has_alpha, bool)
                        and isinstance(pixels, (bytes, list, tuple))
                    ):
                        pixbuf = self.create_pixbuf_from_pixels(
                            width, height, rowstride, has_alpha, pixels
                        )
                        icon = Gtk.Image.new_from_pixbuf(pixbuf)
                        return icon
                    else:
                        self.logger.error("Invalid image-data format: Incorrect types.")
                else:
                    self.logger.error(f"Malformed image-data: {image_data}")
                    pass
            if app_icon:
                app_icon_path = app_icon
                if "file://" in app_icon:
                    app_icon_path = app_icon.split("file://")[1]
                if self.is_valid_path(app_icon):
                    try:
                        thumbnail_path = self.load_thumbnail(app_icon_path)
                        if thumbnail_path:
                            icon = Gtk.Image.new_from_file(thumbnail_path)
                        else:
                            icon = Gtk.Image.new_from_file(app_icon_path)
                        return icon
                    except Exception as e:
                        self.logger.error(f"Error loading app_icon from file: {e}")
                else:
                    try:
                        if "file://" not in app_icon:
                            icon = Gtk.Image.new_from_icon_name(app_icon)
                            return icon
                    except Exception as e:
                        self.logger.error(f"Error loading app_icon as icon name: {e}")
            if app_icon_from_name:
                try:
                    if app_icon_from_name in CUSTOM_ICON:
                        icon_name_to_use = CUSTOM_ICON[app_icon_from_name]
                    else:
                        icon_name_to_use = app_icon_from_name
                    icon = Gtk.Image.new_from_icon_name(icon_name_to_use)
                    print(icon_name_to_use, app_icon)
                    return icon
                except Exception as e:
                    self.logger.error(f"Error loading app_name as icon name: {e}")
            return Gtk.Image.new_from_icon_name("message-new")
        except Exception as e:
            self.logger.error(f"Unexpected error while loading icon: {e}")
            return Gtk.Image.new_from_icon_name("message-new")
