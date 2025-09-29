import asyncio
import io
import mimetypes
import subprocess
from pathlib import Path
import aiosqlite
import pyperclip
from gi.repository import GdkPixbuf, Gio, Gtk, GLib  # pyright: ignore
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore
from PIL import Image
import re
from src.plugins.core._base import BasePlugin
from .clipboard_server import AsyncClipboardServer

ENABLE_PLUGIN = True
DEPS = ["top_panel", "clipboard_server"]


def get_plugin_placement(panel_instance):
    return "top-panel-systray", 2


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return ClipboardClient(panel_instance)
    return None


class ClipboardManager:
    def __init__(self, panel_instance):
        self.server = AsyncClipboardServer(panel_instance)
        self.db_path = self._default_db_path()

    def _default_db_path(self):
        return str(Path.home() / ".config" / "waypanel" / "clipboard_server.db")

    async def initialize(self):
        await self.server.start()

    async def get_history(self) -> list[tuple[int, str]]:
        """Returns all items as (id, content) tuples"""
        return await self.server.get_items()  # pyright: ignore

    async def get_item_by_id(self, target_id: int) -> tuple[int, str] | None:
        """Get specific item by its database ID (first tuple element)"""
        items = await self.get_history()
        for item_id, content in items:
            if item_id == target_id:
                return (item_id, content)
        return None

    async def clear_history(self):
        await self.server.clear_all()

    async def reset_ids(self):
        """Properly rebuild the table with sequential IDs"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE new_clipboard_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                INSERT INTO new_clipboard_items (content, timestamp)
                SELECT content, timestamp FROM clipboard_items
                ORDER BY timestamp DESC
            """)
            await db.execute("DROP TABLE clipboard_items")
            await db.execute(
                "ALTER TABLE new_clipboard_items RENAME TO clipboard_items"
            )
            await db.commit()

    async def delete_item(self, item_id: int):
        await self.server.delete_item(item_id)

    def get_item_by_id_sync(self, target_id: int) -> tuple[int, str] | None:
        """Blocking version for non-async contexts"""
        return asyncio.run(self.get_item_by_id(target_id))


class ClipboardClient(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.manager = ClipboardManager(panel_instance)
        self.popover_clipboard = None
        self.find_text_using_button = {}
        self.row_content = None
        self.listbox = None
        self.client_config = self.config_data.get("plugins", "").get("clipboard")
        self.popover_min_width = self.client_config.get("client_popover_min_width", 500)
        self.popover_max_height = self.client_config.get(
            "client_popover_max_height", 600
        )
        self.thumbnail_size = self.client_config.get("client_thumbnail_size", 128)
        self.preview_text_length = self.client_config.get(
            "client_preview_text_length", 50
        )
        self.image_row_height = self.client_config.get("client_image_row_height", 60)
        self.text_row_height = self.client_config.get("client_text_row_height", 38)
        self.item_spacing = self.client_config.get("client_item_spacing", 5)
        self.create_popover_menu_clipboard()

    def is_image_content(self, content):
        """
        Detect both image files AND raw image data.
        Args:
            content: The clipboard content to check (can be str or bytes).
        Returns:
            bool: True if the content represents an image, False otherwise.
        """
        if isinstance(content, str) and self.data_helper.validate_string(
            content, "content from is_image_content"
        ):
            if len(content) < 256 and Path(content).exists():
                mime = mimetypes.guess_type(content)[0]
                return mime and mime.startswith("image/")
        elif isinstance(content, bytes) and self.data_helper.validate_bytes(
            content, name="bytes from is_image_content"
        ):
            magic_numbers = {
                b"\x89PNG": "PNG",
                b"\xff\xd8": "JPEG",
                b"GIF87a": "GIF",
                b"GIF89a": "GIF",
                b"BM": "BMP",
                b"RIFF....WEBP": "WEBP",
            }
            return any(content.startswith(magic) for magic in magic_numbers.keys())
        elif isinstance(content, str) and self.data_helper.validate_string(
            content, "content from is_image_content"
        ):
            if content.startswith(("data:image/png", "data:image/jpeg")):
                return True
        return False

    def on_paste_clicked(self, manager: ClipboardManager, item_id: int):
        """Standalone version requiring manager instance"""
        if item := self.manager.get_item_by_id_sync(item_id):
            _, content = item
            self.copy_to_clipboard(content)
            return True
        return False

    def create_thumbnail(self, image_path, size=128):
        """Generate larger GdkPixbuf thumbnail"""
        try:
            with Image.open(image_path) as img:
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                bio = io.BytesIO()
                img.save(bio, format="PNG", quality=95)
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(bio.getvalue())
                loader.close()
                return loader.get_pixbuf()
        except Exception as e:
            self.logger.error(f"Thumbnail generation failed: {e}")
            return None

    def copy_to_clipboard(self, content):
        """Universal copy function that handles both text and images"""
        if self.is_image_content(content):
            if Path(content).exists():
                try:
                    subprocess.run(
                        ["wl-copy", "-t", "image/png"],
                        stdin=open(content, "rb"),
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    self.logger.error(f"Failed to copy image: {content}")
            elif self.data_helper.validate_bytes(
                content, name="bytes from copy_to_clipboard"
            ):
                try:
                    subprocess.run(
                        ["wl-copy", "-t", "image/png"],
                        input=content,
                        check=True,
                    )
                except Exception as e:
                    self.logger.error(f"Failed to copy raw image data {e}")
        else:
            try:
                pyperclip.copy(content)
            except Exception as e:
                self.logger.error(f"Failed to copy text: {e}")

    def clear_and_calculate_height(self):
        """
        Clear the existing list and calculate the required height for the scrolled window.
        Returns:
            int: The calculated total height.
        """
        try:
            if self.listbox is not None:
                row = self.listbox.get_first_child()
                while row:
                    next_row = row.get_next_sibling()
                    self.listbox.remove(row)
                    row = next_row
            asyncio.run(self.manager.initialize())
            items = asyncio.run(self.manager.get_history())
            asyncio.run(self.manager.server.stop())
            IMAGE_EXTENSIONS = (
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".bmp",
                ".webp",
                ".svg",
            )
            total_height = 0
            for item in items:
                if any(
                    item.lower().endswith(ext)
                    for ext in IMAGE_EXTENSIONS
                    if isinstance(item, str)
                ) or not isinstance(item, bytes):
                    total_height += self.image_row_height
                else:
                    total_height += self.text_row_height
                total_height += self.item_spacing
            total_height = max(total_height, 100)
            total_height = min(total_height, self.popover_max_height)
            return total_height
        except Exception as e:
            self.logger.error(
                message=f"Error clearing list or calculating height in clear_and_calculate_height. {e}",
            )
            return 100

    def populate_listbox(self):
        """
        Populate the ListBox with clipboard history items.
        """
        try:
            asyncio.run(self.manager.initialize())
            clipboard_history = asyncio.run(self.manager.get_history())
            asyncio.run(self.manager.server.stop())
            for i in clipboard_history:
                if not i:
                    continue
                row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
                image_button = Gtk.Button()
                icon_name = self.gtk_helper.set_widget_icon_name(None, ["tag-delete"])
                image_button.set_icon_name(icon_name)
                image_button.connect("clicked", self.on_delete_selected)
                spacer = Gtk.Label(label="    ")
                self.update_widget_safely(row_hbox.append, image_button)
                self.update_widget_safely(row_hbox.append, spacer)
                item_id = i[0]
                item = i[1]
                if len(item) > self.preview_text_length:
                    item = item[: self.preview_text_length]
                row_hbox.MYTEXT = f"{item_id} {item.strip()}"  # pyright: ignore
                self.update_widget_safely(self.listbox.append, row_hbox)  # pyright: ignore
                if self.is_image_content(item):
                    thumb = self.create_thumbnail(item, size=self.thumbnail_size)
                    if thumb:
                        image_box = Gtk.Box(
                            orientation=Gtk.Orientation.VERTICAL, spacing=5
                        )
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
                line.set_tooltip_markup(i[1])
                escaped_text = GLib.markup_escape_text(item)
                escaped_text = self.format_color_text(item)
                line.set_markup(
                    f'<span font="DejaVu Sans Mono">{item_id} {escaped_text}</span>'
                )
                line.props.margin_end = 5
                line.props.hexpand = True
                line.set_halign(Gtk.Align.START)
                self.update_widget_safely(row_hbox.append, line)
                self.find_text_using_button[image_button] = line
        except Exception as e:
            self.logger.error(
                message=f"Error populating ListBox in populate_listbox. {e}",
            )

    def update_clipboard_list(self):
        """
        Update the clipboard list by clearing, calculating height, and populating the ListBox.
        """
        try:
            total_height = self.clear_and_calculate_height()
            if total_height > 0:
                self.scrolled_window.set_min_content_height(total_height)
            self.populate_listbox()
        except Exception as e:
            self.logger.error(
                message=f"Error updating clipboard list in update_clipboard_list. {e}",
            )

    def create_popover_menu_clipboard(self):
        LayerShell.set_keyboard_mode(
            self.obj.top_panel, LayerShell.KeyboardMode.ON_DEMAND
        )
        self.menubutton_clipboard = Gtk.Button.new()
        self.main_widget = (self.menubutton_clipboard, "append")
        self.menubutton_clipboard.connect("clicked", self.open_popover_clipboard)
        self.gtk_helper.add_cursor_effect(self.menubutton_clipboard)

    def create_popover_clipboard(self, *_):
        self.popover_clipboard = Gtk.Popover.new()
        self.popover_clipboard.set_has_arrow(False)
        self.popover_clipboard.connect("closed", self.popover_is_closed)
        self.popover_clipboard.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(self.popover_min_width)
        self.scrolled_window.set_min_content_height(self.popover_max_height)
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
        item_id = int(selected_text.split()[0])
        self.on_paste_clicked(self.manager, item_id)
        if self.popover_clipboard:
            self.popover_clipboard.popdown()

    def is_color_code(self, text):
        """
        Returns True ONLY if the input is EXACTLY:
        - A 3/6-digit hex color (with or without
        - An RGB color, e.g., "rgb(255,0,0)"
        - An RGBA color, e.g., "rgba(255,0,0,0.5)"
        Returns False for partial matches (e.g., "x#FF0000", "123abc").
        """
        if self.data_helper.validate_string(
            text, "text from is_color_code"
        ) and re.fullmatch(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", text):
            return True
        if self.data_helper.validate_string(text, "text from is_color_code"):
            if re.fullmatch(
                r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", text
            ):
                r, g, b = map(int, re.findall(r"\d+", text))
                return all(0 <= c <= 255 for c in (r, g, b))
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
        if self.data_helper.validate_string(color, "color from get_contrast_color"):
            hex_color = color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = "".join([c * 2 for c in hex_color])
            rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        elif (
            self.data_helper.validate_list(color, element_type=(tuple, list))
            and len(color) == 3
        ):
            rgb = tuple(color)
        else:
            raise ValueError(
                "Input must be a hex string (e.g., '#FF0000') or RGB tuple (e.g., (255, 0, 0))"
            )
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return "#000000" if luminance > 0.5 else "#ffffff"

    def format_color_text(self, text):
        """Wrap color codes in markup with proper background/foreground colors."""
        text = GLib.markup_escape_text(text)
        color_pattern = re.compile(r"(?<!\w)(#?[0-9a-fA-F]{3}|#?[0-9a-fA-F]{6})(?!\w)")

        def replace_color(match):
            color = match.group(1)
            if not color.startswith("#"):
                color = f"#{color}"
            fg_color = self.get_contrast_color(color)
            return f'<span background="{color}" foreground="{fg_color}">{match.group(1)}</span>'

        return color_pattern.sub(replace_color, text)

    def clear_clipboard(self, *_):
        asyncio.run(self.manager.clear_history())
        asyncio.run(self.manager.reset_ids())
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
        asyncio.run(self.manager.delete_item(item_id))
        self.update_clipboard_list()

    def run_app_from_launcher(self, x):
        selected_text, filename = x.get_child().MYTEXT
        cmd = "gtk-launch {}".format(filename)
        self.cmd.run(cmd)
        self.popover_launcher.popdown()  # pyright: ignore

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
        self.searchbar.set_search_mode(True)  # pyright: ignore

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()  # pyright: ignore
        self.logger.info(
            "search entry is focused: {}".format(self.searchentry.is_focus())  # pyright: ignore
        )

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        self.listbox.invalidate_filter()  # pyright: ignore

    def on_filter_invalidate(self, row):
        """
        Filter function for the Gtk.ListBox.
        Args:
            row (Gtk.ListBoxRow): The row to validate.
        Returns:
            bool: True if the row matches the search criteria, False otherwise.
        """
        try:
            if not isinstance(row, Gtk.ListBoxRow):
                self.logger.error(
                    f"Invalid row type: {type(row).__name__}. Expected Gtk.ListBoxRow."
                )
                return False
            child = row.get_child()
            if not child:
                self.logger.error(
                    message="Row child widget is missing in on_filter_invalidate.",
                )
                return False
            if not hasattr(child, "MYTEXT"):
                self.logger.error(
                    message="Row child is missing the required 'MYTEXT' attribute.",
                )
                return False
            row_text = child.MYTEXT  # pyright: ignore
            if not isinstance(row_text, str):
                self.logger.error(
                    f"Invalid row text type: {type(row_text).__name__}. Expected str."
                )
                return False
            text_to_search = self.searchbar.get_text().strip().lower()
            return text_to_search in row_text.lower()
        except Exception as e:
            self.logger.error(
                message="Unexpected error occurred in on_filter_invalidate.",
            )
            return False

    def about(self):
        """
        This plugin serves as the graphical user interface (GUI) for the
        asynchronous clipboard history server. It allows users to view,
        search, and manage their clipboard history through a pop-up menu.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This code is the front-end client for a backend clipboard
        history service. Its core logic is designed around a decoupled
        architecture and robust content handling:
        1.  **Client-Server Decoupling**: The plugin acts as a client to a
            separate clipboard server. It does not handle clipboard events
            directly; instead, it uses a dedicated manager to fetch, delete,
            and clear data via an API-like interface. This separation keeps
            the UI responsive and allows the server to run independently.
        2.  **Synchronous-Asynchronous Integration**: The GTK-based UI
            operates synchronously. The code bridges this with the
            asynchronous backend using `asyncio.run()`. This allows
            the UI to request data from the asynchronous clipboard
            manager without blocking its main thread for extended periods.
        3.  **Universal Content Handling**: The plugin is designed to
            handle both text and image data. It includes functions to
            intelligently detect images based on file paths, raw data
            signatures, or Base64 encoding. It also creates visual
            thumbnails for images, providing a rich user experience
            beyond simple text display.
        4.  **Dynamic UI and Filtering**: The interface dynamically
            populates its list with content from the history. A search
            function is provided to filter the list in real-time. This
            dynamic behavior ensures the UI is always up-to-date and
            user-friendly, even with a large history.
        """
        return self.code_explanation.__doc__
