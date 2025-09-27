import aiosqlite
import datetime
import asyncio
from pathlib import Path
from typing import List, Tuple
from gi.repository import Gio, Gtk, GLib, Pango  # pyright: ignore
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 1
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        notes = MenuNotes(panel_instance)
        return notes


class NotesManager:
    def __init__(self, path_handler):
        self.path_handler = path_handler
        self.db_path = self._default_db_path()

    def _default_db_path(self):
        config_dir = self.path_handler.get_config_dir()
        return str(config_dir / "notes.db")

    async def initialize_db(self):
        """Create notes table if it doesn't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
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
            return await cursor.fetchall()  # pyright: ignore

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


def get_notes_sync(path_handler) -> List[Tuple[int, str]]:
    """Sync wrapper for getting notes"""

    async def _fetch_notes():
        manager = NotesManager(path_handler)
        await manager.initialize_db()
        return await manager.get_notes()

    return asyncio.run(_fetch_notes())


class MenuNotes(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.notes_manager = NotesManager(self.path_handler)
        self.popover_notes = None
        self.find_text_using_button = {}
        self.row_content = None
        self.listbox = None
        self.menubutton_notes = Gtk.Button.new()
        self.main_widget = (self.menubutton_notes, "append")
        self.menubutton_notes.connect("clicked", self.open_popover_notes)
        self.gtk_helper.add_cursor_effect(self.menubutton_notes)
        self.menubutton_notes.set_icon_name(
            self.gtk_helper.set_widget_icon_name(
                "notes",
                [
                    "accessories-notes-symbolic",
                    "xapp-annotations-text-symbolic",
                    "accessories-notes",
                ],
            )
        )

    def delete_button_icon(self):
        return self.get_config(["notes", "notes_icon_delete"], "edit-delete")

    def clear_notes(self, *_):
        """Handle clearing all notes with a GTK4 confirmation dialog"""
        dialog = Gtk.AlertDialog(
            message="Clear all notes?",
            detail="This will permanently delete all your notes. Are you sure?",
            buttons=["_Cancel", "_Clear All"],
        )
        dialog.set_default_button(1)
        dialog.set_cancel_button(0)
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
            self.logger.error(f"Dialog error: {e}")

    def update_notes_list(self):
        """Update the list of notes in the popover"""
        if self.listbox is not None:
            self.listbox.remove_all()
        notes = get_notes_sync(self.path_handler)
        line_height = 40
        padding = 20
        notes_count = len(notes)
        dynamic_height = min(notes_count * line_height + padding, 600)
        self.scrolled_window.set_min_content_height(dynamic_height)
        button_icon = self.gtk_helper.set_widget_icon_name(
            None, [self.delete_button_icon(), "edit-delete"]
        )
        for note_id, content in notes:
            if not content:
                continue
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            delete_button = Gtk.Button()
            delete_button.add_css_class("notes_button_delete")
            delete_button.set_icon_name(button_icon)
            self.gtk_helper.add_cursor_effect(delete_button)
            delete_button.connect("clicked", self.on_delete_note)
            spacer = Gtk.Label(label="    ")
            row_hbox.append(spacer)
            row_hbox.MYTEXT = f"{note_id} {content.strip()}"  # pyright: ignore
            row_hbox.note_id = note_id  # pyright: ignore
            note_label = Gtk.Label.new()
            note_label.set_wrap(True)
            timestamp = content[:16]
            message = content[19:]
            if timestamp and message:
                markup = f"{timestamp} — {message}"
            else:
                markup = content
            note_label.set_markup(f'<span font="DejaVu Sans Mono">{markup}</span>')
            note_label.props.margin_end = 10
            note_label.props.hexpand = True
            note_label.set_wrap(True)
            note_label.set_ellipsize(Pango.EllipsizeMode.NONE)
            note_label.set_halign(Gtk.Align.FILL)
            note_label.set_hexpand(True)
            note_label.set_valign(Gtk.Align.CENTER)
            note_label.set_vexpand(False)
            note_label.set_xalign(0)
            note_label.set_yalign(0.5)
            note_label.set_margin_end(5)
            note_label.set_halign(Gtk.Align.START)
            row_hbox.append(note_label)
            row_hbox.append(delete_button)
            self.listbox.append(row_hbox)  # pyright: ignore
            self.find_text_using_button[delete_button] = row_hbox

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
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.set_placeholder_text("Search notes...")
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.main_box.append(self.searchbar)
        self.entry_add_note = Gtk.Entry.new()
        self.entry_add_note.set_placeholder_text("Add new note...")
        self.entry_add_note.connect("activate", self.on_add_note)
        self.main_box.append(self.entry_add_note)
        buttons_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)
        self.button_add = Gtk.Button.new_with_label("Add")
        self.button_add.add_css_class("notes_button_add")
        self.button_add.connect("clicked", self.on_add_note)
        self.gtk_helper.add_cursor_effect(self.button_add)
        buttons_box.append(self.button_add)
        self.button_clear = Gtk.Button.new_with_label("Clear All")
        self.button_clear.add_css_class("notes_button_clear")
        self.button_clear.connect("clicked", self.clear_notes)
        self.gtk_helper.add_cursor_effect(self.button_clear)
        buttons_box.append(self.button_clear)
        self.main_box.append(buttons_box)
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
        await self.notes_manager.initialize_db()
        await self.notes_manager.add_note(content)

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
        await self.notes_manager.initialize_db()
        await self.notes_manager.delete_note(note_id)

    def on_delete_note(self, button):
        """Handle deleting a note"""
        if button not in self.find_text_using_button:
            self.logger.info("Note delete button not found")
            return
        row = self.find_text_using_button[button]
        note_id = row.note_id
        if note_id:
            asyncio.run(self.async_delete_note(note_id))
            self.update_notes_list()

    async def async_clear_notes(self):
        """Async helper to clear all notes"""
        await self.notes_manager.initialize_db()
        await self.notes_manager.clear_notes()

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
        self.searchbar.set_search_mode(True)  # pyright: ignore

    def on_search_entry_changed(self, searchentry):
        self.listbox.invalidate_filter()  # pyright: ignore

    def on_filter_invalidate(self, row):
        search_text = self.searchbar.get_text().strip().lower()
        if not self.data_helper.validate_string(row, "row from on_filter_invalidate"):
            row_text = row.get_child().MYTEXT.lower()
            return search_text in row_text
        return False

    def about(self):
        """
        A plugin that provides a simple note-taking utility, allowing users
        to add, delete, and view notes directly from the panel. The notes are
        stored in an SQLite database.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin serves as a persistent note-taking tool that integrates
        seamlessly into the `waypanel` application.
        Its core logic is built around **asynchronous database management,
        dynamic UI manipulation, and user interaction**:
        1.  **Database Management**: The plugin uses `aiosqlite` to handle
            all database operations asynchronously, ensuring the UI remains
            responsive. It initializes a SQLite database file at
            `~/.config/waypanel/notes.db`, creates a `notes` table if it
            doesn't exist, and provides methods to add, retrieve, and delete
            notes.
        2.  **Dynamic UI**: The plugin creates a `Gtk.Popover` containing
            widgets for adding notes, searching, and displaying the list of
            existing notes. The list of notes is a `Gtk.ListBox` that is
            dynamically populated and updated by the `update_notes_list` method,
            which fetches notes from the database.
        3.  **User Interaction**: It handles various user actions: adding a
            new note via an entry field, deleting individual notes with a
            button, and clearing all notes via a confirmation dialog. It also
            implements a search function that filters the displayed notes
            in real-time as the user types, using `Gtk.ListBox.set_filter_func`.
        """
        return self.code_explanation.__doc__
