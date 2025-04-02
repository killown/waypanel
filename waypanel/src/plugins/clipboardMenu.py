import asyncio
import io
import mimetypes
import os
import subprocess
from pathlib import Path
from typing import List, Tuple
import toml
import aiosqlite
import gi
import pyperclip
from gi.repository import Adw, GdkPixbuf, Gio, Gtk, GLib
from gi.repository import Gtk4LayerShell as LayerShell
from gi.repository import Pango
from PIL import Image

from ..core.utils import Utils
from .clipboard_server import AsyncClipboardServer
from .icons import get_nearest_icon_name


def run_server_in_background():
    """Start the clipboard server without blocking main thread"""

    async def _run_server():
        server = AsyncClipboardServer()
        await server.start()
        print("🖥️ Clipboard server running in background")
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


async def show_clipboard_popover():
    server = AsyncClipboardServer()
    items = await server.get_items()
    # Display items in Waypanel's popover UI
    for item_id, content in items:
        print(f"{item_id}: {content[:50]}...")


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
        print(f"Debug: Fetched {len(history)} items")  # Optional logging
        return history  # <- Explicit return
    finally:
        await manager.server.stop()


def get_clipboard_items_sync() -> List[Tuple[int, str]]:
    """One-line sync access to clipboard history"""
    return asyncio.run(_fetch_items())


class MenuClipboard(Gtk.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_clipboard = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()
        self.utils = Utils(application_id="com.github.utils")
        self.find_text_using_button = {}
        self.row_content = None
        self.listbox = None

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.scripts = os.path.join(self.home, ".config/hypr/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.topbar_launcher_config = os.path.join(
            self.config_path, "topbar-launcher.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}

    def is_image_content(self, content):
        """Detect both image files AND raw image data"""
        # Case 1: It's a file path that exists
        if isinstance(content, str) and Path(content).exists():
            mime = mimetypes.guess_type(content)[0]
            return mime and mime.startswith("image/")

        # Case 2: It's raw image data (from wl-copy)
        if isinstance(content, bytes):
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
        if isinstance(content, str) and content.startswith(
            ("data:image/png", "data:image/jpeg")
        ):
            return True

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
            print(f"Thumbnail generation failed: {e}")
            return None

    def copy_to_clipboard(self, content):
        """Universal copy function that handles both text and images"""
        if self.is_image_content(content):
            # Handle image copy
            if Path(content).exists():  # It's a file path
                try:
                    # Use wl-copy for Wayland (most reliable)
                    subprocess.run(["wl-copy"], input=content.encode(), check=True)
                    subprocess.run(
                        ["wl-copy", "-t", "image/png"],
                        stdin=open(content, "rb"),
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    print(f"Failed to copy image: {content}")
        else:
            # Handle text copy
            pyperclip.copy(content)

    def update_clipboard_list(self):
        # Clear the existing list
        if self.listbox is not None:
            self.listbox.remove_all()

        # Get items from manager
        manager = ClipboardManager()
        asyncio.run(manager.initialize())
        items = asyncio.run(manager.get_history())
        asyncio.run(manager.server.stop())

        # Calculate needed height
        line_height = 40  # Approx. height per row in pixels
        padding = 20  # Additional padding
        item_count = len(items)

        # Calculate dynamic height (capped at 600px)
        dynamic_height = min(item_count * line_height + padding, 600)
        self.scrolled_window.set_min_content_height(dynamic_height)

        clipboard_history = get_clipboard_items_sync()
        for i in clipboard_history:
            if not i:
                continue
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            image_button = Gtk.Button()
            waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
            if os.path.exists(waypanel_config_path):
                with open(waypanel_config_path, "r") as f:
                    config = toml.load(f)
                    clipboard_icon_delete = (
                        config.get("panel", {})
                        .get("top", {})
                        .get("clipboard_icon_delete", "delete")
                    )
                    image_button.set_icon_name(
                        get_nearest_icon_name(clipboard_icon_delete)
                    )
            else:
                image_button.set_icon_name("delete")
            image_button.connect("clicked", self.on_delete_selected)
            spacer = Gtk.Label(label="    ")
            row_hbox.append(image_button)
            row_hbox.append(spacer)
            item_id = i[0]
            item = i[1]
            if len(item) > 50:
                item = item[:50]
            row_hbox.MYTEXT = f"{item_id} {item.strip()}"
            self.listbox.append(row_hbox)
            if self.is_image_content(item):
                # Create larger thumbnail (128px) with padding
                thumb = self.create_thumbnail(item, size=128)
                if thumb:
                    # Create container for image + text
                    image_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

                    # Bigger image display
                    image_widget = Gtk.Image.new_from_pixbuf(thumb)
                    image_widget.set_margin_end(10)
                    image_widget.set_size_request(128, 128)
                    image_box.append(image_widget)
                    row_hbox.append(image_box)
                    item = item.split("/")[-1]
                    row_hbox.set_size_request(-1, 150)
            line = Gtk.Label.new()
            escaped_text = GLib.markup_escape_text(item)
            line.set_markup(
                f'<span font="DejaVu Sans Mono">{item_id} {escaped_text}</span>'
            )
            line.props.margin_end = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            row_hbox.append(line)
            self.find_text_using_button[image_button] = line

    def create_popover_menu_clipboard(self, obj, app, *_):
        self.top_panel = obj.top_panel
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        self.app = app
        self.menubutton_clipboard = Gtk.Button.new()
        self.menubutton_clipboard.connect("clicked", self.open_popover_clipboard)
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
        if os.path.exists(waypanel_config_path):
            with open(waypanel_config_path, "r") as f:
                config = toml.load(f)
                clipboard_icon = (
                    config.get("panel", {})
                    .get("top", {})
                    .get("clipboard_icon", "edit-paste")
                )
                self.menubutton_clipboard.set_icon_name(
                    get_nearest_icon_name(clipboard_icon)
                )
        else:
            self.menubutton_clipboard.set_icon_name("edit-paste")
        obj.top_panel_box_systray.append(self.menubutton_clipboard)

    def create_popover_clipboard(self, *_):
        # Create a popover
        self.popover_clipboard = Gtk.Popover.new()  # Create a new popover menu
        self.popover_clipboard.set_has_arrow(False)
        self.popover_clipboard.connect("closed", self.popover_is_closed)
        self.popover_clipboard.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.app.add_action(show_searchbar_action)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(500)
        self.scrolled_window.set_min_content_height(600)
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.props.hexpand = True
        self.searchbar.props.vexpand = True

        self.main_box.append(self.searchbar)
        self.button_clear = Gtk.Button()
        self.button_clear.add_css_class("clipboard_clear_button")
        self.button_clear.set_label("Clear")
        self.button_clear.connect("clicked", self.clear_clipboard)
        self.button_clear.add_css_class("button_clear_from_clipboard")
        self.main_box.append(self.button_clear)
        self.listbox = Gtk.ListBox.new()
        self.listbox.connect(
            "row-selected", lambda widget, row: self.on_copy_clipboard(row)
        )
        self.searchbar.set_key_capture_widget(self.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)
        self.popover_clipboard.set_child(self.main_box)
        self.update_clipboard_list()
        self.listbox.set_filter_func(self.on_filter_invalidate)
        self.popover_clipboard.set_parent(self.menubutton_clipboard)
        self.popover_clipboard.popup()
        return self.popover_clipboard

    def on_copy_clipboard(self, x, *_):
        selected_text = x.get_child().MYTEXT
        manager = ClipboardManager()
        asyncio.run(manager.initialize())
        item_id = int(selected_text.split()[0])
        self.on_paste_clicked(manager, item_id)
        self.popover_clipboard.popdown()

    def clear_clipboard(self, *_):
        asyncio.run(ClipboardManager().clear_history())
        asyncio.run(ClipboardManager().reset_ids())
        self.update_clipboard_list()
        self.scrolled_window.set_min_content_height(50)

    def on_delete_selected(self, button):
        button = [i for i in self.find_text_using_button if button == i]
        print(button)
        if button:
            button = button[0]
        else:
            print("clipboard del button not found")
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
            self.popover_clipboard = self.create_popover_clipboard(self.app)

    def popover_is_open(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)

    def popover_is_closed(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.NONE)

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()
        print("search entry is focused: {}".format(self.searchentry.is_focus()))

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        # run filter (run self.on_filter_invalidate look at self.listbox.set_filter_func(self.on_filter_invalidate) )
        self.listbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        text_to_search = (
            self.searchbar.get_text().strip()
        )  # get text from searchentry and remove space from start and end
        if not isinstance(row, str):
            row = row.get_child().MYTEXT
        # row = row.lower().strip()
        if (
            text_to_search.lower() in row
        ):  # == row_hbox.MYTEXT (Gtk.ListBoxRow===>get_child()===>row_hbox.MYTEXT)
            return True  # if True Show row
        return False
