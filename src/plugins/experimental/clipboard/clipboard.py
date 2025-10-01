import io
import mimetypes
from pathlib import Path
import aiosqlite
import pyperclip
from PIL import Image
import re
from src.plugins.core._base import BasePlugin
from .clipboard_server import AsyncClipboardServer
from src.shared.path_handler import PathHandler

ENABLE_PLUGIN = True
DEPS = ["clipboard_server"]


def get_plugin_placement(panel_instance):
    return "top-panel-systray", 2


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return ClipboardClient(panel_instance)
    return None


class ClipboardManager:
    def __init__(self, panel_instance):
        self.server = AsyncClipboardServer(panel_instance)
        self.path_handler = PathHandler(panel_instance)
        self.db_path = self.path_handler.get_data_path(
            "db/clipboard/clipboard_server.db"
        )

    async def initialize(self):
        pass

    async def get_history(self) -> list[tuple[int, str, str | None, int]]:
        """Returns all items as (id, content, label, is_pinned) tuples (new feature)"""
        return await self.server.get_items()  # pyright: ignore

    async def get_item_by_id(
        self, target_id: int
    ) -> tuple[int, str, str | None, int] | None:
        """Get specific item by its database ID (first tuple element)"""
        items = await self.get_history()
        for item_id, content, label, is_pinned in items:
            if item_id == target_id:
                return (item_id, content, label, is_pinned)
        return None

    async def update_item_label(self, item_id: int, new_label: str | None):
        """NEW: Update the custom label for a specific item ID using the server API."""
        await self.server.update_label(item_id, new_label)

    async def update_item_pin_status(self, item_id: int, is_pinned: bool):
        """NEW: Update the pin status (0 or 1) for a specific item ID."""
        await self.server.update_pin_status(item_id, 1 if is_pinned else 0)

    async def clear_history(self):
        await self.server.clear_all()

    async def reset_ids(self):
        """Properly rebuild the table with sequential IDs (UPDATED for 'label' and 'is_pinned' column)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE new_clipboard_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    label TEXT DEFAULT NULL,
                    is_pinned INTEGER DEFAULT 0 -- NEW: Field for Pinning
                )
            """)
            await db.execute("""
                INSERT INTO new_clipboard_items (content, timestamp, label, is_pinned)
                SELECT content, timestamp, label, 0 FROM clipboard_items
                ORDER BY timestamp DESC
            """)
            await db.execute("DROP TABLE clipboard_items")
            await db.execute(
                "ALTER TABLE new_clipboard_items RENAME TO clipboard_items"
            )
            await db.commit()

    async def delete_item(self, item_id: int):
        await self.server.delete_item(item_id)

    def get_item_by_id_sync(
        self, target_id: int
    ) -> tuple[int, str, str | None, int] | None:
        """Blocking version for non-async contexts"""
        import asyncio

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

    def _create_menu_item_with_icon_and_label(self, label_text: str, icon_name: str):
        """Helper to create a self.gtk.Button that visually guarantees both icon and label are shown.
        This fixes the issue of buttons in popovers only showing icons."""
        button = self.gtk.Button.new()
        hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 10)
        hbox.set_margin_start(10)
        hbox.set_margin_end(10)
        icon = self.gtk.Image.new_from_icon_name(self.gtk_helper.icon_exist(icon_name))
        hbox.append(icon)
        label = self.gtk.Label.new(label_text)
        label.set_halign(self.gtk.Align.START)
        hbox.append(label)
        button.set_child(hbox)
        button.set_halign(self.gtk.Align.FILL)
        return button

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
            if (
                content.startswith(("data:image/png", "data:image/jpeg"))
                or content == "<image>"
            ):
                return True
        return False

    def on_paste_clicked(self, manager: ClipboardManager, item_id: int):
        """Standalone version requiring manager instance"""
        if item := self.manager.get_item_by_id_sync(item_id):
            _, content, _, _ = item
            self.copy_to_clipboard(content)
            return True
        return False

    def create_thumbnail(self, image_path, size=128):
        """Generate larger self.gdkpixbuf thumbnail"""
        try:
            if image_path == "<image>":
                return None
            with Image.open(image_path) as img:
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                bio = io.BytesIO()
                img.save(bio, format="PNG", quality=95)
                loader = self.gdkpixbuf.PixbufLoader.new_with_type("png")
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
                    self.subprocess.run(
                        ["wl-copy", "-t", "image/png"],
                        stdin=open(content, "rb"),
                        check=True,
                    )
                except self.subprocess.CalledProcessError:
                    self.logger.error(f"Failed to copy image: {content}")
            elif self.data_helper.validate_bytes(
                content, name="bytes from copy_to_clipboard"
            ):
                try:
                    self.subprocess.run(
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
        FIXED (GTK4/PyGObject Memory Leak): Implements the GTK4 iteration pattern and
        adds explicit cleanup for self.gtk.Popovers to resolve the "still has children left"
        warning and prevent the memory leak.
        Returns:
            int: The calculated total height.
        """
        try:
            if self.listbox is not None:
                row = self.listbox.get_first_child()
                while row:
                    next_row = row.get_next_sibling()
                    row_hbox = row.get_child()  # pyright: ignore
                    if row_hbox:
                        child = row_hbox.get_first_child()
                        while child:
                            if hasattr(child, "popover") and child.popover is not None:
                                try:
                                    child.popover.unparent()
                                    del child.popover
                                except Exception:
                                    pass
                            if child in self.find_text_using_button:
                                del self.find_text_using_button[child]
                            child = child.get_next_sibling()
                    if hasattr(row, "popover") and row.popover is not None:  # pyright: ignore
                        try:
                            row.popover.unparent()  # pyright: ignore
                            del row.popover  # pyright: ignore
                        except Exception:
                            pass
                    self.listbox.remove(row)
                    row = next_row
            self.asyncio.run(self.manager.initialize())
            items = self.asyncio.run(self.manager.get_history())
            self.asyncio.run(self.manager.server.stop())
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
            for item_id, content, label, is_pinned in items:
                if any(
                    content.lower().endswith(ext)
                    for ext in IMAGE_EXTENSIONS
                    if isinstance(content, str)
                ) or self.is_image_content(content):
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
        try:
            self.asyncio.run(self.manager.initialize())
            clipboard_history = self.asyncio.run(self.manager.get_history())
            self.asyncio.run(self.manager.server.stop())
            pinned_items = sorted(
                [item for item in clipboard_history if item[3] == 1],
                key=lambda x: x[0],
                reverse=True,
            )
            unpinned_items = sorted(
                [item for item in clipboard_history if item[3] == 0],
                key=lambda x: x[0],
                reverse=True,
            )
            sorted_history = pinned_items + unpinned_items
            for (
                item_id,
                item_content,
                item_label,
                is_pinned,
            ) in sorted_history:
                if not item_content:
                    continue
                row_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 5)
                delete_button = self.gtk.Button()
                delete_button.set_icon_name(self.gtk_helper.icon_exist("tag-delete"))
                delete_button.connect("clicked", self.on_delete_selected)
                self.update_widget_safely(row_hbox.append, delete_button)
                label_button = self.gtk.Button()
                label_icon = (
                    "document-edit-symbolic" if item_label else "list-add-symbolic"
                )
                label_button.set_icon_name(self.gtk_helper.icon_exist(label_icon))
                label_button.set_tooltip_text(f"Edit label for ID {item_id}")
                label_button.connect("clicked", self.on_edit_label_clicked)
                self.update_widget_safely(row_hbox.append, label_button)
                display_text = item_label if item_label else item_content
                if len(display_text) > self.preview_text_length and not item_label:
                    display_text = display_text[: self.preview_text_length] + "..."
                elif len(display_text) > 80:
                    display_text = display_text[:80] + "..."
                row_hbox.MYTEXT = f"{item_id} {item_content.strip()} {item_label.strip() if item_label else ''}"  # pyright: ignore
                row_hbox.ITEM_ID = item_id  # pyright: ignore
                row_hbox.IS_PINNED = is_pinned  # pyright: ignore
                list_box_row = self.gtk.ListBoxRow()
                list_box_row.set_child(row_hbox)
                gesture_right_click = self.gtk.GestureClick.new()
                gesture_right_click.set_button(3)
                gesture_right_click.connect("pressed", self.on_right_click_row)
                list_box_row.add_controller(gesture_right_click)
                if is_pinned:
                    pin_icon = self.gtk.Image.new_from_icon_name(
                        self.gtk_helper.icon_exist("object-locked-symbolic")
                    )
                    pin_icon.set_opacity(0.7)
                    self.update_widget_safely(row_hbox.append, pin_icon)
                self.update_widget_safely(self.listbox.append, list_box_row)  # pyright: ignore
                is_image = self.is_image_content(item_content)
                if is_image:
                    thumb = self.create_thumbnail(
                        item_content, size=self.thumbnail_size
                    )
                    if thumb:
                        image_box = self.gtk.Box(
                            orientation=self.gtk.Orientation.HORIZONTAL, spacing=5
                        )
                        image_widget = self.gtk.Image.new_from_pixbuf(thumb)
                        image_widget.set_margin_start(10)
                        image_widget.set_margin_end(10)
                        image_widget.set_margin_top(5)
                        image_widget.set_margin_bottom(5)
                        image_widget.set_valign(self.gtk.Align.CENTER)
                        self.update_widget_safely(image_box.append, image_widget)
                        image_box.set_valign(self.gtk.Align.CENTER)
                        self.update_widget_safely(row_hbox.append, image_box)
                        if not item_label:
                            display_text = (
                                Path(item_content).name
                                if Path(item_content).exists()
                                else "Image Content"
                            )
                line = self.gtk.Label.new()
                line.set_tooltip_markup(item_content)
                escaped_text = self.glib.markup_escape_text(display_text)
                escaped_text = self.format_color_text(display_text)
                markup_format = '<span font="DejaVu Sans Mono">{id} {text}</span>'
                if item_label or is_pinned:
                    markup_format = '<span background="#404040" foreground="#FFFFFF" font="DejaVu Sans Mono">{id} {text}</span>'
                line.set_markup(markup_format.format(id=item_id, text=escaped_text))
                line.props.margin_end = 5
                line.props.hexpand = True
                line.set_halign(self.gtk.Align.START)
                self.update_widget_safely(row_hbox.append, line)
                self.find_text_using_button[delete_button] = line
                self.find_text_using_button[label_button] = line
        except Exception as e:
            self.logger.error(
                message=f"Error populating ListBox in populate_listbox. {e}",
            )

    def on_right_click_row(self, gesture, n_press: int, x: float, y: float):
        """
        Handler for the right-click gesture. Creates and displays a context menu Popover.
        FIXED: Uses helper to ensure buttons display both icon and label text.
        """
        if gesture.get_button() != 3:
            return
        row: self.gtk.ListBoxRow = gesture.get_widget()  # pyright: ignore
        row_hbox = row.get_child()
        if not hasattr(row_hbox, "ITEM_ID") or not hasattr(row_hbox, "IS_PINNED"):
            self.logger.warning("Could not retrieve item data from row.")
            return
        item_id = row_hbox.ITEM_ID  # pyright: ignore
        is_pinned = row_hbox.IS_PINNED  # pyright: ignore
        menu = self.gtk.Popover.new()
        menu.set_parent(row)
        vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
        vbox.set_margin_start(5)
        vbox.set_margin_end(5)
        vbox.set_margin_top(5)
        vbox.set_margin_bottom(5)
        pin_label = "Unstick from Top" if is_pinned else "Stick to Top"
        pin_icon = "object-unlocked-symbolic" if is_pinned else "object-locked-symbolic"
        pin_button = self._create_menu_item_with_icon_and_label(pin_label, pin_icon)
        pin_button.connect(
            "clicked", self.on_pin_clicked, item_id, bool(is_pinned), menu
        )
        vbox.append(pin_button)
        menu.set_child(vbox)
        menu.popup()

    def on_menu_edit_label_clicked(self, button, item_id: int, menu):
        """
        Helper to close the context menu and then trigger the label editor Popover.
        """
        menu.popdown()
        item_data = self.manager.get_item_by_id_sync(item_id)
        if item_data:
            current_label = item_data[2]
            self.create_label_editor_popover(button, item_id, current_label)
        else:
            self.logger.warning(f"Item ID {item_id} not found for label editing.")

    def on_pin_clicked(
        self,
        button,
        item_id: int,
        current_status: bool,
        menu,
    ):
        """
        NEW: Handler for the 'Stick to Top' / 'Unstick from Top' button.
        """
        menu.popdown()
        new_status = not current_status
        self.asyncio.run(self.manager.update_item_pin_status(item_id, new_status))
        self.update_clipboard_list()

    def _save_label_popover_content(
        self,
        button,
        entry,
        item_id: int,
        popover,
    ):
        """Handles saving the new label from the Popover."""
        new_label = entry.get_text().strip()
        label_to_save = new_label if new_label else None
        self.asyncio.run(self.manager.update_item_label(item_id, label_to_save))
        popover.popdown()
        anchor_button = popover.get_parent()
        if anchor_button:
            try:
                popover.unparent()
                if hasattr(anchor_button, "_label_editor_popover"):
                    del anchor_button._label_editor_popover  # pyright: ignore
            except Exception:
                pass
        self.update_clipboard_list()

    def create_label_editor_popover(
        self, button_to_anchor, item_id: int, current_label: str | None
    ):
        """
        NEW: Creates and displays a Popover for editing the clipboard item's label,
        using a compact layout with a left-aligned save (tick) button.
        """
        popover = self.gtk.Popover.new()
        popover.set_parent(button_to_anchor)
        popover.set_has_arrow(True)
        button_to_anchor._label_editor_popover = popover  # pyright: ignore
        vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_size_request(300, -1)
        hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 5)
        hbox.set_halign(self.gtk.Align.FILL)
        save_button = self.gtk.Button.new()
        save_button.set_icon_name(self.gtk_helper.icon_exist("emblem-ok-symbolic"))
        save_button.set_tooltip_text("Save label (Enter)")
        save_button.set_valign(self.gtk.Align.CENTER)
        entry = self.gtk.Entry()
        entry.set_text(current_label if current_label else "")
        entry.set_placeholder_text(f"Label for ID {item_id} (empty to clear)")
        entry.props.hexpand = True
        save_button.connect(
            "clicked", self._save_label_popover_content, entry, item_id, popover
        )
        entry.connect(
            "activate",
            lambda *_: self._save_label_popover_content(
                save_button, entry, item_id, popover
            ),
        )
        hbox.append(save_button)
        hbox.append(entry)
        vbox.append(hbox)
        popover.set_child(vbox)
        popover.popup()

    def on_edit_label_clicked(self, button):
        """
        Handler for the original 'Edit Label' button on the row.
        UPDATED to use the new Popover editor.
        """
        if button in self.find_text_using_button:
            label_widget = self.find_text_using_button[button]
            full_text = label_widget.get_text()
            item_id = int(full_text.split()[0])
            item_data = self.manager.get_item_by_id_sync(item_id)
            if item_data:
                current_label = item_data[2]
                self.create_label_editor_popover(button, item_id, current_label)
            else:
                self.logger.warning(f"Item ID {item_id} not found for label editing.")
        else:
            self.logger.warning("Label button not mapped to a clipboard item.")

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
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
        )
        self.menubutton_clipboard = self.gtk.Button.new()
        self.main_widget = (self.menubutton_clipboard, "append")
        self.menubutton_clipboard.connect("clicked", self.open_popover_clipboard)
        self.gtk_helper.add_cursor_effect(self.menubutton_clipboard)

    def create_popover_clipboard(self, *_):
        self.popover_clipboard = self.gtk.Popover.new()
        self.popover_clipboard.set_has_arrow(False)
        self.popover_clipboard.connect("closed", self.popover_is_closed)
        self.popover_clipboard.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = self.gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)
        self.scrolled_window = self.gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(self.popover_min_width)
        self.scrolled_window.set_min_content_height(self.popover_max_height)
        self.main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_bottom(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.searchbar = self.gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.props.hexpand = True
        self.searchbar.props.vexpand = True
        self.update_widget_safely(self.main_box.append, self.searchbar)
        self.button_clear = self.gtk.Button()
        self.button_clear.set_label("Clear")
        self.button_clear.connect("clicked", self.clear_clipboard)
        self.listbox = self.gtk.ListBox.new()
        self.listbox.connect(
            "row-selected", lambda widget, row: self.on_copy_clipboard(row)
        )
        self.searchbar.set_key_capture_widget(self.obj.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(self.gtk.SelectionMode.SINGLE)
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
        row_hbox = x.get_child()
        selected_text = row_hbox.MYTEXT
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
            self.data_helper.validate_list(color, element_type=(tuple, list))  # pyright: ignore
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
        text = self.glib.markup_escape_text(text)
        color_pattern = re.compile(r"(?<!\w)(#?[0-9a-fA-F]{3}|#?[0-9a-fA-F]{6})(?!\w)")

        def replace_color(match):
            color = match.group(1)
            if not color.startswith("#"):
                color = f"#{color}"
            fg_color = self.get_contrast_color(color)
            return f'<span background="{color}" foreground="{fg_color}">{match.group(1)}</span>'

        return color_pattern.sub(replace_color, text)

    def clear_clipboard(self, *_):
        self.asyncio.run(self.manager.clear_history())
        self.asyncio.run(self.manager.reset_ids())
        self.update_clipboard_list()
        self.scrolled_window.set_min_content_height(50)

    def on_delete_selected(self, button):
        button_to_find = [i for i in self.find_text_using_button if button == i]
        if not button_to_find:
            self.logger.info("clipboard del button not found")
            return
        button_clicked = button_to_find[0]
        label = self.find_text_using_button[button_clicked]
        try:
            item_id = int(label.get_text().split()[0])
        except (ValueError, IndexError):
            self.logger.error("Could not parse item ID from label text for deletion.")
            return
        self.asyncio.run(self.manager.delete_item(item_id))
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
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
        )

    def popover_is_closed(self, *_):
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.NONE
        )

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(True)  # pyright: ignore

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()  # pyright: ignore
        self.logger.info(
            "search entry is focused: {}".format(self.searchentry.is_focus())  # pyright: ignore
        )

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`self.gtk`.ListBoxRow.changed])
        or when [method`self.gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        self.listbox.invalidate_filter()  # pyright: ignore

    def on_filter_invalidate(self, row):
        """
        Filter function for the self.gtk.ListBox.
        Args:
            row (self.gtk.ListBoxRow): The row to validate.
        Returns:
            bool: True if the row matches the search criteria, False otherwise.
        """
        try:
            if not isinstance(row, self.gtk.ListBoxRow):
                return False
            child = row.get_child()
            if not child or not hasattr(child, "MYTEXT"):
                return False
            row_text = child.MYTEXT  # pyright: ignore
            if not isinstance(row_text, str):
                return False
            text_to_search = self.searchbar.get_text().strip().lower()
            return text_to_search in row_text.lower()
        except Exception as e:
            self.logger.error(
                f"Unexpected error occurred in on_filter_invalidate. {e}",
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
            separate clipboard server. It uses a dedicated manager to fetch, delete,
            and clear data via an API-like interface, ensuring the UI remains
            responsive. The addition of the **`update_item_label`** method extends
            this API for permanent labeling of items, and **`update_item_pin_status`**
            adds support for persisting item pin status.
        2.  **Synchronous-Asynchronous Integration**: The GTK-based UI
            operates synchronously. The code bridges this with the
            asynchronous backend using `self.asyncio.run()`.
        3.  **UI for New Feature**: The **`populate_listbox`** method is updated
            to unpack and display the new `label` and **`is_pinned`** fields.
            A new **`self.gtk.GestureClick`** is added to each row to detect right-clicks,
            which triggers **`on_right_click_row`** to display a context **`self.gtk.Popover`**
        """
        return self.code_explanation.__doc__
