import asyncio
import io
import mimetypes
import subprocess
from pathlib import Path
from typing import List, Tuple
import aiosqlite
import pyperclip
from gi.repository import GdkPixbuf, Gio, Gtk, GLib
from gi.repository import Gtk4LayerShell as LayerShell
from PIL import Image
import re

from src.plugins.core._base import BasePlugin

from .clipboard_server import AsyncClipboardServer

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel", "clipboard_server"]


def get_plugin_placement(panel_instance):
    return "top-panel-systray", 2


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        clipboard = ClipboardClient(panel_instance)
        clipboard.create_popover_menu_clipboard()
        return clipboard


async def show_clipboard_popover():
    server = AsyncClipboardServer()
    items = await server.get_items()


# Call this when the popover opens
asyncio.run(show_clipboard_popover())


class ClipboardManager:
    def __init__(self):
        self.server = AsyncClipboardServer()
        self.db_path = self._default_db_path()

    def _default_db_path(self):
        return str(Path.home() / ".config" / "waypanel" / "clipboard_server.db")

    async def initialize(self):
        await self.server.start()

    async def get_history(self) -> list[tuple[int, str]]:
        """Returns all items as (id, content) tuples"""
        return await self.server.get_items()

    async def get_item_by_id(self, target_id: int) -> tuple[int, str] | None:
        """Get specific item by its database ID (first tuple element)"""
        items = await self.get_history()
        for item_id, content in items:
            if item_id == target_id:
                return (item_id, content)
        return None  # If ID not found

    async def clear_history(self):
        await self.server.clear_all()

    async def reset_ids(self):
        """Properly rebuild the table with sequential IDs"""
        async with aiosqlite.connect(self.db_path) as db:
            # Create new table with the same structure
            await db.execute("""
                CREATE TABLE new_clipboard_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Copy all content in timestamp order (maintaining history order)
            await db.execute("""
                INSERT INTO new_clipboard_items (content, timestamp)
                SELECT content, timestamp FROM clipboard_items 
                ORDER BY timestamp DESC
            """)

            # Replace old table
            await db.execute("DROP TABLE clipboard_items")
            await db.execute(
                "ALTER TABLE new_clipboard_items RENAME TO clipboard_items"
            )
            await db.commit()

    async def delete_item(self, item_id: int):
        await self.server.delete_item(item_id)

    # Synchronous version
    def get_item_by_id_sync(self, target_id: int) -> tuple[int, str] | None:
        """Blocking version for non-async contexts"""
        return asyncio.run(self.get_item_by_id(target_id))


async def _fetch_items():
    """Async helper that properly returns values"""
    manager = ClipboardManager()
    await manager.initialize()
    try:
        history = await manager.get_history()  # Get items
        return history  # <- Explicit return
    finally:
        await manager.server.stop()


def get_clipboard_items_sync() -> List[Tuple[int, str]]:
    """One-line sync access to clipboard history"""
    return asyncio.run(_fetch_items())


class ClipboardClient(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_clipboard = None
        self.find_text_using_button = {}
        self.row_content = None
        self.listbox = None

    def is_image_content(self, content):
        """
        Detect both image files AND raw image data.
        Args:
            content: The clipboard content to check (can be str or bytes).
        Returns:
            bool: True if the content represents an image, False otherwise.
        """
        # Case 1: It's a file path that exists (and is reasonably short)
        if isinstance(content, str) and self.utils.validate_string(
            content, "content from is_image_content"
        ):
            if len(content) < 256 and Path(content).exists():
                mime = mimetypes.guess_type(content)[0]
                return mime and mime.startswith("image/")

        # Case 2: It's raw image data (from wl-copy)
        elif isinstance(content, bytes) and self.utils.validate_bytes(
            content, name="bytes from is_image_content"
        ):
            # Check magic numbers for common image formats
            magic_numbers = {
                b"\x89PNG": "PNG",
                b"\xff\xd8": "JPEG",
                b"GIF87a": "GIF",
                b"GIF89a": "GIF",
                b"BM": "BMP",
                b"RIFF....WEBP": "WEBP",
            }
            return any(content.startswith(magic) for magic in magic_numbers.keys())

        # Case 3: It's a base64 encoded image (common in clipboard)
        elif isinstance(content, str) and self.utils.validate_string(
            content, "content from is_image_content"
        ):
            if content.startswith(("data:image/png", "data:image/jpeg")):
                return True

        # Default case: Not recognized as image content
        return False

    def on_paste_clicked(self, manager: ClipboardManager, item_id: int):
        """Standalone version requiring manager instance"""
        if item := manager.get_item_by_id_sync(item_id):
            _, content = item
            self.copy_to_clipboard(content)
            return True  # Success
        return False  # Item not found

    def create_thumbnail(self, image_path, size=128):
        """Generate larger GdkPixbuf thumbnail"""
        try:
            with Image.open(image_path) as img:
                # Maintain aspect ratio while increasing size
                img.thumbnail((size, size), Image.Resampling.LANCZOS)  # Better quality

                # Create high-quality PNG
                bio = io.BytesIO()
                img.save(bio, format="PNG", quality=95)

                # Load as Pixbuf
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(bio.getvalue())
                loader.close()
                return loader.get_pixbuf()
        except Exception as e:
            self.log_error(f"Thumbnail generation failed: {e}")
            return None

    def copy_to_clipboard(self, content):
        """Universal copy function that handles both text and images"""
        if self.is_image_content(content):
            # Handle image copy
            if Path(content).exists():  # It's a file path
                try:
                    # Use wl-copy for Wayland (most reliable)
                    subprocess.run(
                        ["wl-copy", "-t", "image/png"],
                        stdin=open(content, "rb"),
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    self.log_error(f"Failed to copy image: {content}")
            elif self.utils.validate_bytes(
                content, name="bytes from copy_to_clipboard"
            ):
                # Handle raw image data
                try:
                    subprocess.run(
                        ["wl-copy", "-t", "image/png"],
                        input=content,
                        check=True,
                    )
                except Exception as e:
                    self.log_error(f"Failed to copy raw image data {e}")
        else:
            # Handle text copy
            try:
                pyperclip.copy(content)
            except Exception as e:
                self.log_error(f"Failed to copy text: {e}")

    def clear_and_calculate_height(self):
        """
        Clear the existing list and calculate the required height for the scrolled window.
        Returns:
            int: The calculated total height.
        """
        try:
            # Clear the existing list
            if self.listbox is not None:
                row = self.listbox.get_first_child()
                while row:
                    next_row = (
                        row.get_next_sibling()
                    )  # Store the next row before removing
                    self.listbox.remove(row)
                    row = next_row

            # Get items from manager
            manager = ClipboardManager()
            asyncio.run(manager.initialize())
            items = asyncio.run(manager.get_history())
            asyncio.run(manager.server.stop())

            # Image extensions to check for
            IMAGE_EXTENSIONS = (
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".bmp",
                ".webp",
                ".svg",
            )

            # Calculate needed height
            total_height = 0

            for item in items:
                if any(
                    item.lower().endswith(ext)
                    for ext in IMAGE_EXTENSIONS
                    if isinstance(item, str)
                ) or not isinstance(item, bytes):
                    total_height += 60  # Image height
                else:
                    total_height += 38  # Text height

                # Add spacing between items (optional)
                total_height += 5

            # Calculate dynamic height (capped at 600px)
            total_height = max(total_height, 100)  # Minimum height of 100px
            total_height = min(total_height, 600)  # Maximum height of 600px

            return total_height

        except Exception as e:
            self.log_error(
                message=f"Error clearing list or calculating height in clear_and_calculate_height. {e}",
            )
            return 100  # Default height in case of error

    def populate_listbox(self):
        """
        Populate the ListBox with clipboard history items.
        """
        try:
            clipboard_history = get_clipboard_items_sync()

            for i in clipboard_history:
                if not i:
                    continue

                row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
                image_button = Gtk.Button()
                icon_name = self.utils.set_widget_icon_name(None, ["tag-delete"])
                image_button.set_icon_name(self.utils.get_nearest_icon_name(icon_name))
                image_button.connect("clicked", self.on_delete_selected)

                spacer = Gtk.Label(label="    ")
                self.update_widget_safely(row_hbox.append, image_button)
                self.update_widget_safely(row_hbox.append, spacer)

                item_id = i[0]
                item = i[1]
                if len(item) > 50:
                    item = item[:50]
                row_hbox.MYTEXT = f"{item_id} {item.strip()}"

                # Append the row to the ListBox
                self.update_widget_safely(self.listbox.append, row_hbox)

                if self.is_image_content(item):
                    # Create larger thumbnail (128px) with padding
                    thumb = self.create_thumbnail(item, size=128)
                    if thumb:
                        # Create container for image + text
                        image_box = Gtk.Box(
                            orientation=Gtk.Orientation.VERTICAL, spacing=5
                        )

                        # Bigger image display
                        image_widget = Gtk.Image.new_from_pixbuf(thumb)
                        image_widget.set_margin_end(10)
                        image_widget.set_size_request(96, 96)
                        self.update_widget_safely(image_box.append, image_widget)
                        self.update_widget_safely(row_hbox.append, image_box)

                        if not item:
                            item = "/image"
                        item = item.split("/")[-1]
                        row_hbox.set_size_request(96, 96)

                line = Gtk.Label.new()
                escaped_text = GLib.markup_escape_text(item)
                escaped_text = self.format_color_text(item)  # Don't escape again here
                line.set_markup(
                    f'<span font="DejaVu Sans Mono">{item_id} {escaped_text}</span>'
                )
                line.props.margin_end = 5
                line.props.hexpand = True
                line.set_halign(Gtk.Align.START)
                self.update_widget_safely(row_hbox.append, line)

                self.find_text_using_button[image_button] = line

        except Exception as e:
            self.log_error(
                message=f"Error populating ListBox in populate_listbox. {e}",
            )

    def update_clipboard_list(self):
        """
        Update the clipboard list by clearing, calculating height, and populating the ListBox.
        """
        try:
            # Step 1: Clear the list and calculate the height
            total_height = self.clear_and_calculate_height()

            # Step 2: Set the calculated height for the scrolled window
            if total_height > 0:
                self.scrolled_window.set_min_content_height(total_height)

            # Step 3: Populate the ListBox
            self.populate_listbox()

        except Exception as e:
            self.log_error(
                message=f"Error updating clipboard list in update_clipboard_list. {e}",
            )

    def create_popover_menu_clipboard(self):
        LayerShell.set_keyboard_mode(
            self.obj.top_panel, LayerShell.KeyboardMode.ON_DEMAND
        )
        self.menubutton_clipboard = Gtk.Button.new()
        # main_widget must be set always after the widget container is created
        self.main_widget = (self.menubutton_clipboard, "append")
        self.menubutton_clipboard.connect("clicked", self.open_popover_clipboard)
        clipboard_icon = (
            self.config.get("panel", {})
            .get("top", {})
            .get("clipboard_icon", "edit-paste")
        )
        self.menubutton_clipboard.set_icon_name(
            self.utils.set_widget_icon_name(
                "clipboard", ["edit-paste-symbolic", "edit-paste"]
            )
        )

        self.utils.add_cursor_effect(self.menubutton_clipboard)

    def create_popover_clipboard(self, *_):
        # Create a popover
        self.popover_clipboard = Gtk.Popover.new()  # Create a new popover menu
        self.popover_clipboard.set_has_arrow(False)
        self.popover_clipboard.connect("closed", self.popover_is_closed)
        self.popover_clipboard.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(500)
        self.scrolled_window.set_min_content_height(600)
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_bottom(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.props.hexpand = True
        self.searchbar.props.vexpand = True

        self.update_widget_safely(self.main_box.append, self.searchbar)
        self.button_clear = Gtk.Button()
        self.button_clear.set_label("Clear")
        self.button_clear.connect("clicked", self.clear_clipboard)
        self.listbox = Gtk.ListBox.new()
        self.listbox.connect(
            "row-selected", lambda widget, row: self.on_copy_clipboard(row)
        )
        self.searchbar.set_key_capture_widget(self.obj.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.update_widget_safely(self.main_box.append, self.scrolled_window)
        self.update_widget_safely(self.main_box.append, self.button_clear)
        self.scrolled_window.set_child(self.listbox)
        self.popover_clipboard.set_child(self.main_box)
        self.update_clipboard_list()
        self.listbox.set_filter_func(self.on_filter_invalidate)
        self.popover_clipboard.set_parent(self.menubutton_clipboard)
        self.popover_clipboard.popup()
        self.button_clear.add_css_class("clipboard_clear_button")
        self.button_clear.add_css_class("button_clear_from_clipboard")
        return self.popover_clipboard

    def on_copy_clipboard(self, x, *_):
        if x is None:
            return
        selected_text = x.get_child().MYTEXT
        manager = ClipboardManager()
        asyncio.run(manager.initialize())
        item_id = int(selected_text.split()[0])
        self.on_paste_clicked(manager, item_id)
        if self.popover_clipboard:
            self.popover_clipboard.popdown()

    def is_color_code(self, text):
        """
        Returns True ONLY if the input is EXACTLY:
        - A 3/6-digit hex color (with or without #), e.g., "FF0000", "#F00"
        - An RGB color, e.g., "rgb(255,0,0)"
        - An RGBA color, e.g., "rgba(255,0,0,0.5)"
        Returns False for partial matches (e.g., "x#FF0000", "123abc").
        """

        # Check for HEX color (3 or 6 digits, optional #)
        if self.utils.validate_string(text, "text from is_color_code") and re.fullmatch(
            r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", text
        ):
            return True

        # Check for RGB/RGBA color (strict format)
        if self.utils.validate_string(text, "text from is_color_code"):
            # RGB: "rgb(255, 0, 0)"
            if re.fullmatch(
                r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", text
            ):
                r, g, b = map(int, re.findall(r"\d+", text))
                return all(0 <= c <= 255 for c in (r, g, b))

            # RGBA: "rgba(255, 0, 0, 0.5)"
            if re.fullmatch(
                r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([01]?\.\d+)\s*\)$",
                text,
            ):
                r, g, b, a = map(float, re.findall(r"[\d.]+", text))
                return all(0 <= c <= 255 for c in (r, g, b)) and (0 <= a <= 1)

        return False

    def get_contrast_color(self, color):
        """
        Calculate contrasting color (black or white) for:
        - Hex strings (e.g., "#FF0000", "F00", "FF0000")
        - RGB tuples (e.g., (255, 0, 0))
        """
        # If input is a hex string
        if self.utils.validate_string(color, "color from get_contrast_color"):
            # Remove '#' if present and normalize to 6-digit hex
            hex_color = color.lstrip("#")

            # Expand 3-digit hex to 6-digit if needed
            if len(hex_color) == 3:
                hex_color = "".join([c * 2 for c in hex_color])

            # Convert hex to RGB
            rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

        # If input is an RGB tuple
        elif (
            self.utils.validate_list(color, element_type=(tuple, list))
            and len(color) == 3
        ):
            rgb = tuple(color)  # Ensure it's a tuple

        else:
            raise ValueError(
                "Input must be a hex string (e.g., '#FF0000') or RGB tuple (e.g., (255, 0, 0))"
            )

        # Calculate luminance (same for both hex and RGB)
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return "#000000" if luminance > 0.5 else "#ffffff"

    def format_color_text(self, text):
        """Wrap color codes in markup with proper background/foreground colors."""
        # First, escape the text to prevent markup injection
        text = GLib.markup_escape_text(text)

        # Improved regex to match:
        # 1. 3-digit hex with # (e.g., #f00)
        # 2. 6-digit hex with # (e.g., #ff0000)
        # 3. 3 or 6-digit hex without # (e.g., f00 or ff0000)
        color_pattern = re.compile(r"(?<!\w)(#?[0-9a-fA-F]{3}|#?[0-9a-fA-F]{6})(?!\w)")

        def replace_color(match):
            color = match.group(1)
            # Ensure color has # prefix
            if not color.startswith("#"):
                color = f"#{color}"

            # Get contrasting text color
            fg_color = self.get_contrast_color(color)

            # Return formatted span
            return f'<span background="{color}" foreground="{fg_color}">{match.group(1)}</span>'

        # Replace all color matches in the text
        return color_pattern.sub(replace_color, text)

    def clear_clipboard(self, *_):
        asyncio.run(ClipboardManager().clear_history())
        asyncio.run(ClipboardManager().reset_ids())
        self.update_clipboard_list()
        self.scrolled_window.set_min_content_height(50)

    def on_delete_selected(self, button):
        button = [i for i in self.find_text_using_button if button == i]
        self.logger.info(button)
        if button:
            button = button[0]
        else:
            self.logger.info("clipboard del button not found")
            return
        label = self.find_text_using_button[button]
        item_id = label.get_text().split()[0]
        label.set_label("")
        manager = ClipboardManager()
        asyncio.run(manager.delete_item(item_id))
        self.update_clipboard_list()

    def run_app_from_launcher(self, x):
        selected_text, filename = x.get_child().MYTEXT
        cmd = "gtk-launch {}".format(filename)
        self.utils.run_app(cmd)
        self.popover_launcher.popdown()

    def open_popover_clipboard(self, *_):
        if self.popover_clipboard and self.popover_clipboard.is_visible():
            self.popover_clipboard.popdown()
        if self.popover_clipboard and not self.popover_clipboard.is_visible():
            self.update_clipboard_list()
            self.popover_clipboard.popup()
        if not self.popover_clipboard:
            self.popover_clipboard = self.create_popover_clipboard()

    def popover_is_open(self, *_):
        LayerShell.set_keyboard_mode(
            self.obj.top_panel, LayerShell.KeyboardMode.ON_DEMAND
        )

    def popover_is_closed(self, *_):
        LayerShell.set_keyboard_mode(self.obj.top_panel, LayerShell.KeyboardMode.NONE)

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()
        self.logger.info(
            "search entry is focused: {}".format(self.searchentry.is_focus())
        )

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        # run filter (run self.on_filter_invalidate look at self.listbox.set_filter_func(self.on_filter_invalidate) )
        self.listbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        """
        Filter function for the Gtk.ListBox.
        Args:
            row (Gtk.ListBoxRow): The row to validate.
        Returns:
            bool: True if the row matches the search criteria, False otherwise.
        """
        try:
            # Ensure the input is a Gtk.ListBoxRow
            if not isinstance(row, Gtk.ListBoxRow):
                self.log_error(
                    f"Invalid row type: {type(row).__name__}. Expected Gtk.ListBoxRow."
                )
                return False

            # Get the child widget of the row
            child = row.get_child()
            if not child:
                self.log_error(
                    message="Row child widget is missing in on_filter_invalidate.",
                )
                return False

            # Ensure the child widget has the 'MYTEXT' attribute
            if not hasattr(child, "MYTEXT"):
                self.log_error(
                    message="Row child is missing the required 'MYTEXT' attribute.",
                )
                return False

            # Extract the text from the child widget
            row_text = child.MYTEXT
            if not isinstance(row_text, str):
                self.log_error(
                    f"Invalid row text type: {type(row_text).__name__}. Expected str."
                )
                return False

            # Perform the search
            text_to_search = self.searchbar.get_text().strip().lower()
            return text_to_search in row_text.lower()

        except Exception as e:
            self.log_error(
                message="Unexpected error occurred in on_filter_invalidate.",
            )
            return False
