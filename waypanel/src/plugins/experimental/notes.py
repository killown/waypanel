import aiosqlite
import datetime
import re
import asyncio
from pathlib import Path
from typing import List, Tuple
from gi.repository import Gio, Gtk, GLib, Pango

from waypanel.src.plugins.core._base import BasePlugin


# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 1
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        notes = MenuNotes(panel_instance)
        notes.create_popover_menu_notes()
        return notes


class NotesManager:
    def __init__(self):
        self.db_path = self._default_db_path()

    def _default_db_path(self):
        return str(Path.home() / ".config" / "waypanel" / "notes.db")

    async def initialize_db(self):
        """Create notes table if it doesn't exist"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def get_notes(self) -> list[tuple[int, str]]:
        """Returns all notes as (id, content) tuples"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, content FROM notes ORDER BY timestamp DESC"
            )
            return await cursor.fetchall()

    async def add_note(self, content: str):
        """Add a new note"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO notes (content) VALUES (?)", (content,))
            await db.commit()

    async def delete_note(self, note_id: int):
        """Delete a note by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            await db.commit()

    async def clear_notes(self):
        """Delete all notes"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM notes")
            await db.commit()


def get_notes_sync() -> List[Tuple[int, str]]:
    """Sync wrapper for getting notes"""

    async def _fetch_notes():
        manager = NotesManager()
        await manager.initialize_db()
        return await manager.get_notes()

    return asyncio.run(_fetch_notes())


class MenuNotes(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_notes = None
        self.find_text_using_button = {}
        self.row_content = None
        self.listbox = None

    def delete_button_icon(self):
        return (
            self.config.get("panel", {})
            .get("top", {})
            .get("notes_icon_delete", "edit-delete")
        )
        return

    def clear_notes(self, *_):
        """Handle clearing all notes with a GTK4 confirmation dialog"""
        dialog = Gtk.AlertDialog(
            message="Clear all notes?",
            detail="This will permanently delete all your notes. Are you sure?",
            buttons=["_Cancel", "_Clear All"],  # GTK4 uses underscores for mnemonics
        )

        # Set the default destructive action (makes "Clear All" stand out in some DEs)
        dialog.set_default_button(1)  # Index 1 = "Clear All"
        dialog.set_cancel_button(0)  # Index 0 = "Cancel"

        # Show the dialog and handle response asynchronously
        dialog.choose(
            callback=self.on_clear_confirmation_response,
        )

    def on_clear_confirmation_response(self, dialog, result, *_):
        """Callback for the AlertDialog response"""
        try:
            response = dialog.choose_finish(result)
            if response == 1:
                """Handle clearing all notes"""
                asyncio.run(self.async_clear_notes())
                self.update_notes_list()
                self.scrolled_window.set_min_content_height(50)
        except Exception as e:
            self.log_error(f"Dialog error: {e}")

    def update_notes_list(self):
        """Update the list of notes in the popover"""
        if self.listbox is not None:
            self.listbox.remove_all()

        notes = get_notes_sync()

        # Calculate dynamic height
        line_height = 40
        padding = 20
        notes_count = len(notes)
        dynamic_height = min(notes_count * line_height + padding, 600)
        self.scrolled_window.set_min_content_height(dynamic_height)

        button_icon = self.utils.get_nearest_icon_name(self.delete_button_icon())
        for note_id, content in notes:
            if not content:
                continue

            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)

            # Add delete button
            delete_button = Gtk.Button()
            delete_button.add_css_class("notes_button_delete")
            delete_button.set_icon_name(button_icon)

            delete_button.connect("clicked", self.on_delete_note)

            spacer = Gtk.Label(label="    ")
            row_hbox.append(spacer)

            # Store note ID in the row's data
            row_hbox.MYTEXT = f"{note_id} {content.strip()}"  # pyright: ignore
            row_hbox.note_id = note_id  # pyright: ignore

            # Add note content
            note_label = Gtk.Label.new()
            note_label.set_wrap(True)
            timestamp = content[:16]  # Extract "YYYY-MM-DD HH:MM"
            message = content[19:]  # Skip " — "

            if timestamp and message:
                markup = f"{timestamp} — {message}"
            else:
                markup = content

            note_label.set_markup(f'<span font="DejaVu Sans Mono">{markup}</span>')
            note_label.props.margin_end = 10
            note_label.props.hexpand = True
            note_label.set_wrap(True)
            note_label.set_ellipsize(Pango.EllipsizeMode.NONE)  # Prevent truncation
            note_label.set_halign(Gtk.Align.FILL)  # Fill horizontal space
            note_label.set_hexpand(True)  # Expand horizontally
            note_label.set_valign(Gtk.Align.CENTER)  # Vertically center text
            note_label.set_vexpand(False)  # Don't expand vertically
            note_label.set_xalign(0)  # Left-aligned text
            note_label.set_yalign(0.5)
            note_label.set_margin_end(5)
            note_label.set_halign(Gtk.Align.START)
            row_hbox.append(note_label)
            row_hbox.append(delete_button)

            self.listbox.append(row_hbox)  # pyright: ignore
            self.find_text_using_button[delete_button] = row_hbox

    def create_popover_menu_notes(self):
        """Create the notes button in the panel"""
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
        )
        self.menubutton_notes = Gtk.Button.new()
        self.main_widget = (self.menubutton_notes, "append")
        self.menubutton_notes.connect("clicked", self.open_popover_notes)

        notes_icon = (
            self.config.get("panel", {})
            .get("top", {})
            .get("notes_icon", "accessories-notes")
        )
        self.menubutton_notes.set_icon_name(
            self.utils.get_nearest_icon_name(notes_icon)
        )

    def create_popover_notes(self):
        """Create the notes popover content"""
        self.popover_notes = Gtk.Popover.new()
        self.popover_notes.set_has_arrow(False)
        self.popover_notes.connect("closed", self.popover_is_closed)
        self.popover_notes.connect("notify::visible", self.popover_is_open)

        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(600)
        self.scrolled_window.set_min_content_height(600)

        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_bottom(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)

        # Search bar
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.set_placeholder_text("Search notes...")
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.main_box.append(self.searchbar)

        # Add note entry
        self.entry_add_note = Gtk.Entry.new()
        self.entry_add_note.set_placeholder_text("Add new note...")
        self.entry_add_note.connect("activate", self.on_add_note)
        self.main_box.append(self.entry_add_note)

        # Buttons box
        buttons_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)

        self.button_add = Gtk.Button.new_with_label("Add")
        self.button_add.add_css_class("notes_button_add")
        self.button_add.connect("clicked", self.on_add_note)
        buttons_box.append(self.button_add)

        self.button_clear = Gtk.Button.new_with_label("Clear All")
        self.button_clear.add_css_class("notes_button_clear")
        self.button_clear.connect("clicked", self.clear_notes)
        buttons_box.append(self.button_clear)

        self.main_box.append(buttons_box)

        # Notes list
        self.listbox = Gtk.ListBox.new()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.listbox.set_filter_func(self.on_filter_invalidate)

        self.scrolled_window.set_child(self.listbox)
        self.main_box.append(self.scrolled_window)

        self.popover_notes.set_child(self.main_box)
        self.update_notes_list()
        self.popover_notes.set_parent(self.menubutton_notes)

        return self.popover_notes

    async def async_add_note(self, content):
        """Async helper to add a note"""
        manager = NotesManager()
        await manager.initialize_db()
        await manager.add_note(content)

    def on_add_note(self, *_):
        """Handle adding a new note with timestamp"""
        content = self.entry_add_note.get_text().strip()
        if content:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            content_with_time = f"{now} — {content}"
            asyncio.run(self.async_add_note(content_with_time))
            self.entry_add_note.set_text("")
            self.update_notes_list()

    async def async_delete_note(self, note_id):
        """Async helper to delete a note"""
        manager = NotesManager()
        await manager.initialize_db()
        await manager.delete_note(note_id)

    def on_delete_note(self, button):
        """Handle deleting a note"""
        if button not in self.find_text_using_button:
            self.logger.info("Note delete button not found")
            return

        row = self.find_text_using_button[button]
        note_id = row.note_id  # Get the ID stored on the row

        if note_id:
            asyncio.run(self.async_delete_note(note_id))
            self.update_notes_list()

    async def async_clear_notes(self):
        """Async helper to clear all notes"""
        manager = NotesManager()
        await manager.initialize_db()
        await manager.clear_notes()

    def open_popover_notes(self, *_):
        """Handle opening the notes popover"""
        if self.popover_notes and self.popover_notes.is_visible():
            self.popover_notes.popdown()
        elif self.popover_notes and not self.popover_notes.is_visible():
            self.update_notes_list()
            self.popover_notes.popup()
        else:
            self.popover_notes = self.create_popover_notes()
            GLib.timeout_add(100, self.popover_notes.popup)

    def popover_is_open(self, *_):
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
        )

    def popover_is_closed(self, *_):
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.NONE
        )

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(True)

    def on_search_entry_changed(self, searchentry):
        self.listbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        search_text = self.searchbar.get_text().strip().lower()
        if not self.utils.validate_string(row, "row from on_filter_invalidate"):
            row_text = row.get_child().MYTEXT.lower()
            return search_text in row_text
        return False
