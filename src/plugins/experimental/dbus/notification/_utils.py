import os
import base64
import urllib.parse
from io import BytesIO
from typing import Optional, Dict, Any

import cairosvg
from PIL import Image
from gi.repository import Gtk, GdkPixbuf
from src.plugins.core._base import BasePlugin

CUSTOM_ICON = {"notify-send": "cs-notifications-symbolic"}


class NotifyUtils(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

    def is_valid_path(self, path: str) -> bool:
        return os.path.exists(path)

    def create_pixbuf_from_pixels(
        self,
        width: int,
        height: int,
        rowstride: int,
        has_alpha: bool,
        pixels: Any,
    ) -> Optional[GdkPixbuf.Pixbuf]:
        try:
            # dbus-fast Variant unpacking
            pixel_data = pixels.value if hasattr(pixels, "value") else pixels

            if isinstance(pixel_data, (list, tuple)):
                pixel_data = bytes(pixel_data)
            elif isinstance(pixel_data, str):
                pixel_data = bytes([int(x.strip()) for x in pixel_data.split(",")])

            return GdkPixbuf.Pixbuf.new_from_data(
                pixel_data,
                GdkPixbuf.Colorspace.RGB,
                has_alpha,
                8,
                width,
                height,
                rowstride,
                None,
            )
        except Exception as e:
            self.logger.error(f"Error creating pixbuf: {e}")
            return None

    def create_png_from_pixel_data(
        self, width: int, height: int, pixel_data: bytes
    ) -> Optional[bytes]:
        try:
            img = Image.new("RGBA", (width, height))
            img.putdata(
                [tuple(pixel_data[i : i + 4]) for i in range(0, len(pixel_data), 4)]
            )
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception:
            return None

    def svg_to_pixbuf(self, svg_data: bytes) -> Optional[GdkPixbuf.Pixbuf]:
        try:
            png_data = cairosvg.svg2png(bytestring=svg_data)
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            if png_data:
                loader.write(png_data)
                loader.close()
                return loader.get_pixbuf()
        except Exception as e:
            self.logger.error(f"Error converting SVG to Pixbuf: {e}")
            return None

    def decode_data_uri(self, data_uri: str) -> Optional[bytes]:
        try:
            header, encoded_data = data_uri.split(",", 1)
            if "base64" in header:
                return base64.b64decode(encoded_data)
            return urllib.parse.unquote(encoded_data).encode("utf-8")
        except Exception as e:
            self.logger.error(f"Error decoding data URI: {e}")
            return None

    def load_thumbnail(self, image_path: str, max_size=(64, 64)) -> Optional[str]:
        try:
            with Image.open(image_path) as img:
                img.thumbnail(max_size)
                thumbnail_path = "/tmp/notification_thumbnail.png"
                img.save(thumbnail_path, format="PNG")
                return thumbnail_path
        except Exception as e:
            self.logger.error(f"Error creating thumbnail: {e}")
            return None

    def load_icon(self, notification: Dict[str, Any]) -> Gtk.Image:
        try:
            hints = notification.get("hints", {})
            if isinstance(hints, str):
                import orjson as json

                try:
                    hints = json.loads(hints)
                except Exception:
                    hints = {}

            app_icon = notification.get("app_icon", "")
            app_name = notification.get("app_name", "")

            # Priority: If app_icon is a valid local path (our cached PNG)
            if app_icon and self.is_valid_path(app_icon):
                return Gtk.Image.new_from_file(app_icon)

            # Handle raw image data (for live popups)
            img_data = hints.get("image-data") or hints.get("icon_data")
            if img_data:
                data = img_data.value if hasattr(img_data, "value") else img_data
                if isinstance(data, (list, tuple)) and len(data) >= 5:
                    w, h, rs, alpha = data[0], data[1], data[2], data[3]
                    px = data[4] if len(data) == 5 else data[6]
                    pixbuf = self.create_pixbuf_from_pixels(w, h, rs, alpha, px)
                    if pixbuf:
                        return Gtk.Image.new_from_pixbuf(pixbuf)

            # Handle standard icon names or file:// paths
            if app_icon:
                clean_path = app_icon.replace("file://", "")
                if self.is_valid_path(clean_path):
                    return Gtk.Image.new_from_file(clean_path)
                return Gtk.Image.new_from_icon_name(app_icon)

            # Fallback
            icon_name = CUSTOM_ICON.get(
                app_name.lower(), app_name.lower().replace(" ", "-")
            )
            return Gtk.Image.new_from_icon_name(icon_name)

        except Exception:
            return Gtk.Image.new_from_icon_name("message-new-symbolic")

    def save_pixbuf_to_cache(
        self, pixbuf: GdkPixbuf.Pixbuf, notification_id: int
    ) -> str:
        """Saves a Pixbuf to the local cache directory and returns the path."""
        cache_dir = self.path_handler.get_data_path("cache/notifications")
        os.makedirs(cache_dir, exist_ok=True)

        file_path = os.path.join(cache_dir, f"icon_{notification_id}.png")
        pixbuf.savev(file_path, "png", [], [])
        return file_path

    def sanitize_for_db(self, data: Any, notification_id: int = 0) -> Any:
        if hasattr(data, "value"):
            return self.sanitize_for_db(data.value, notification_id)

        if isinstance(data, dict):
            # Special check for image-data to extract and save it
            if "image-data" in data or "icon_data" in data:
                raw_data = data.get("image-data") or data.get("icon_data")
                unpacked = raw_data.value if hasattr(raw_data, "value") else raw_data
                if isinstance(unpacked, (list, tuple)) and len(unpacked) >= 7:
                    pixbuf = self.create_pixbuf_from_pixels(
                        unpacked[0], unpacked[1], unpacked[2], unpacked[3], unpacked[6]
                    )
                    if pixbuf:
                        # Save to disk and return the path to store in the DB hints
                        return self.save_pixbuf_to_cache(pixbuf, notification_id)

            return {
                k: self.sanitize_for_db(v, notification_id) for k, v in data.items()
            }

        if isinstance(data, (list, tuple)):
            return [self.sanitize_for_db(i, notification_id) for i in data]

        if isinstance(data, (bytes, bytearray)):
            if len(data) > 1024:
                return "<binary_removed>"  # Fallback for other random byte blobs
            return base64.b64encode(data).decode("utf-8")

        return data
