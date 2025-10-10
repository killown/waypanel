def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.notes",
        "name": "Notes",
        "version": "1.0.0",
        "enabled": True,
        "index": 1,
        "container": "top-panel-systray",
        "deps": ["top_panel"],
    }


def get_plugin_class():
    import aiosqlite
    import datetime
    import asyncio
    from typing import List, Tuple
    from gi.repository import Gio, Gtk, GLib  # pyright: ignore
    from src.plugins.core._base import BasePlugin

    class NotesManager:
        def __init__(self, path_handler, db_path):
            self.path_handler = path_handler
            self.db_path = db_path

        async def initialize_db(self):
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
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, content FROM notes ORDER BY timestamp DESC"
                )
                return await cursor.fetchall()  # pyright: ignore

        async def add_note(self, content: str):
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("INSERT INTO notes (content) VALUES (?)", (content,))
                await db.commit()

        async def delete_note(self, note_id: int):
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                await db.commit()

        async def edit_note(self, note_id: int, new_content: str):
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE notes SET content = ?, timestamp = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_content, note_id),
                )
                await db.commit()

        async def clear_notes(self):
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM notes")
                await db.commit()

    def get_notes_sync(path_handler, db_path) -> List[Tuple[int, str]]:
        async def _fetch_notes():
            manager = NotesManager(path_handler, db_path)
            await manager.initialize_db()
            return await manager.get_notes()

        return asyncio.run(_fetch_notes())

    class MenuNotes(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.db_path = self.path_handler.get_data_path("db/notes/notes.db")
            self.notes_manager = NotesManager(self.path_handler, self.db_path)
            self.popover_notes = None
            self.find_text_using_button = {}
            self.note_row_widgets = {}
            self.is_editing = False
            self.row_content = None
            self.listbox = None
            self.menubutton_notes = Gtk.Button.new()
            self.menubutton_notes.add_css_class("notes-menubutton")
            self.main_widget = (self.menubutton_notes, "append")
            self.menubutton_notes.connect("clicked", self.open_popover_notes)
            self.gtk_helper.add_cursor_effect(self.menubutton_notes)

        def create_popover_notes(self):
            self.popover_notes = Gtk.Popover.new()
            self.popover_notes.add_css_class("notes-popover")
            self.popover_notes.set_has_arrow(False)
            self.popover_notes.connect("closed", self.popover_is_closed)
            self.popover_notes.connect("notify::visible", self.popover_is_open)
            show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
            show_searchbar_action.connect(
                "activate", self.on_show_searchbar_action_actived
            )
            self.obj.add_action(show_searchbar_action)
            self.scrolled_window = Gtk.ScrolledWindow()
            self.scrolled_window.add_css_class("notes-scrolledwindow")
            self.scrolled_window.set_min_content_width(600)
            self.scrolled_window.set_min_content_height(600)
            self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
            self.main_box.add_css_class("notes-main-box")
            self.main_box.set_margin_top(10)
            self.main_box.set_margin_bottom(10)
            self.main_box.set_margin_start(10)
            self.main_box.set_margin_end(10)
            self.searchbar = Gtk.SearchEntry.new()
            self.searchbar.add_css_class("notes-searchbar")
            self.searchbar.set_placeholder_text("Search notes...")
            self.searchbar.connect("search_changed", self.on_search_entry_changed)
            self.main_box.append(self.searchbar)
            self.entry_add_note = Gtk.Entry.new()
            self.entry_add_note.add_css_class("notes-entry-add")
            self.entry_add_note.set_placeholder_text("Add new note...")
            self.entry_add_note.connect("activate", self.on_add_note)
            self.main_box.append(self.entry_add_note)
            buttons_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)
            buttons_box.add_css_class("notes-buttons-box")
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
            self.listbox.add_css_class("notes-listbox")
            self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            self.listbox.set_show_separators(True)
            self.listbox.set_filter_func(self.on_filter_invalidate)
            self.scrolled_window.set_child(self.listbox)
            self.main_box.append(self.scrolled_window)
            self.popover_notes.set_child(self.main_box)
            self.run_in_thread(self.update_notes_list)
            self.popover_notes.set_parent(self.menubutton_notes)
            return self.popover_notes

        def clear_notes(self, *_):
            dialog = Gtk.AlertDialog(
                message="Clear all notes?",
                detail="This will permanently delete all your notes. Are you sure?",
                buttons=["_Cancel", "_Clear All"],
            )
            dialog.add_css_class("notes-alertdialog")
            dialog.set_default_button(1)
            dialog.set_cancel_button(0)
            dialog.choose(
                callback=self.on_clear_confirmation_response,
            )

        def on_clear_confirmation_response(self, dialog, result, *_):
            try:
                response = dialog.choose_finish(result)
                if response == 1:
                    asyncio.run(self.async_clear_notes())
                    self.update_notes_list()
                    self.scrolled_window.set_min_content_height(50)
            except Exception as e:
                self.logger.error(f"Dialog error: {e}")

        def update_notes_list(self):
            if self.listbox is not None:
                self._gtk_helper.clear_listbox(self.listbox)
            self.is_editing = False
            self.note_row_widgets = {}
            notes = get_notes_sync(self.path_handler, self.db_path)
            line_height = 40
            padding = 20
            notes_count = len(notes)
            dynamic_height = min(notes_count * line_height + padding, 600)
            self.scrolled_window.set_min_content_height(dynamic_height)
            delete_icon_name = self.get_plugin_setting(["delete_icon"], "edit-delete")
            delete_button_icon = self.gtk_helper.icon_exist(
                delete_icon_name, ["edit-delete"]
            )
            edit_icon_name = self.get_plugin_setting(["edit_icon"], "document-edit")
            edit_button_icon = self.gtk_helper.icon_exist(
                edit_icon_name, ["document-edit"]
            )
            for note_id, content in notes:
                if not content:
                    continue
                row = Gtk.ListBoxRow()
                row.add_css_class("notes-listbox-row")
                row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)
                row_hbox.add_css_class("notes-row-hbox")
                row_hbox.set_margin_start(10)
                row_hbox.set_margin_end(10)
                row_hbox.note_id = note_id  # pyright: ignore
                row.set_child(row_hbox)
                spacer = Gtk.Label(label="  ")
                spacer.add_css_class("notes-spacer-label")
                row_hbox.append(spacer)
                note_label = Gtk.Label.new()
                note_label.add_css_class("notes-note-label")
                note_label.set_wrap(True)
                parts = content.split()
                if len(parts) >= 3:
                    timestamp_str = f"{parts[0]} {parts[1]}"
                    message = " ".join(parts[2:])
                    if message.strip():
                        markup = f'<span font="DejaVu Sans Mono"><b>{timestamp_str}</b> {message}</span>'
                        note_label.original_content = message  # pyright: ignore
                    else:
                        markup = f'<span font="DejaVu Sans Mono">{content}</span>'
                        note_label.original_content = content  # pyright: ignore
                else:
                    timestamp_str = ""
                    message = content
                    markup = f'<span font="DejaVu Sans Mono">{content}</span>'
                    note_label.original_content = content  # pyright: ignore
                note_label.set_markup(markup)
                note_label.set_halign(Gtk.Align.START)
                note_label.set_hexpand(True)
                note_label.set_valign(Gtk.Align.CENTER)
                note_label.set_xalign(0)
                row_hbox.append(note_label)
                edit_button = Gtk.Button()
                edit_button.add_css_class("notes_button_edit")
                edit_button.set_icon_name(edit_button_icon)
                self.gtk_helper.add_cursor_effect(edit_button)
                edit_button.connect("clicked", self.on_start_edit_note, note_id)
                row_hbox.append(edit_button)
                delete_button = Gtk.Button()
                delete_button.add_css_class("notes_button_delete")
                delete_button.set_icon_name(delete_button_icon)
                self.gtk_helper.add_cursor_effect(delete_button)
                delete_button.connect("clicked", self.on_delete_note)
                row_hbox.append(delete_button)
                self.listbox.append(row)  # pyright: ignore
                self.find_text_using_button[delete_button] = row_hbox
                self.note_row_widgets[note_id] = {
                    "row": row,
                    "hbox": row_hbox,
                    "label": note_label,
                    "edit_button": edit_button,
                    "delete_button": delete_button,
                }

        def on_start_edit_note(self, button, note_id):
            if self.is_editing:
                return
            if note_id not in self.note_row_widgets:
                self.logger.error(f"Cannot find widgets for note_id: {note_id}")
                return
            self.is_editing = True
            widgets = self.note_row_widgets[note_id]
            hbox = widgets["hbox"]
            old_label = widgets["label"]
            initial_text = old_label.original_content
            edit_entry = Gtk.Entry.new()
            edit_entry.add_css_class("notes-edit-entry")
            edit_entry.set_text(initial_text)
            edit_entry.set_hexpand(True)
            edit_entry.set_halign(Gtk.Align.FILL)
            edit_entry.connect("activate", self.on_finish_edit_note, note_id, widgets)
            hbox.remove(old_label)
            first_child = hbox.get_first_child()
            if (
                first_child
                and first_child.get_css_classes()
                and "notes-spacer-label" in first_child.get_css_classes()
            ):
                hbox.insert_child_after(edit_entry, first_child)
            else:
                hbox.prepend(edit_entry)
            edit_entry.grab_focus()
            edit_entry.select_region(0, -1)
            widgets["edit_button"].set_sensitive(False)
            widgets["delete_button"].set_sensitive(False)
            widgets["edit_entry"] = edit_entry

        def on_finish_edit_note(self, entry, note_id, widgets):
            new_content_message = entry.get_text().strip()
            if not new_content_message:
                self.is_editing = False
                self.update_notes_list()
                return
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_full_content = f"{now} {new_content_message}"
            asyncio.run(self.async_edit_note(note_id, new_full_content))
            self.is_editing = False
            self.update_notes_list()

        async def async_edit_note(self, note_id: int, new_content: str):
            await self.notes_manager.initialize_db()
            await self.notes_manager.edit_note(note_id, new_content)

        async def async_add_note(self, content):
            await self.notes_manager.initialize_db()
            await self.notes_manager.add_note(content)

        def on_add_note(self, *_):
            content = self.entry_add_note.get_text().strip()
            if content and not self.is_editing:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                content_with_time = f"{now} {content}"
                asyncio.run(self.async_add_note(content_with_time))
                self.entry_add_note.set_text("")
                self.update_notes_list()

        async def async_delete_note(self, note_id):
            await self.notes_manager.initialize_db()
            await self.notes_manager.delete_note(note_id)

        def on_delete_note(self, button):
            if self.is_editing:
                return
            if button not in self.find_text_using_button:
                self.logger.info("Note delete button not found")
                return
            row_hbox = self.find_text_using_button[button]
            note_id = row_hbox.note_id
            if note_id:
                asyncio.run(self.async_delete_note(note_id))
                self.update_notes_list()

        async def async_clear_notes(self):
            await self.notes_manager.initialize_db()
            await self.notes_manager.clear_notes()

        def open_popover_notes(self, *_):
            if self.popover_notes and self.popover_notes.is_visible():
                self.popover_notes.popdown()
            elif self.popover_notes and not self.popover_notes.is_visible():
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
            if not search_text:
                return True
            row_hbox = row.get_child()
            note_widget = None
            for child in row_hbox:
                if isinstance(child, Gtk.Label) and hasattr(child, "original_content"):
                    note_widget = child
                    break
                elif isinstance(child, Gtk.Entry):
                    note_widget = child
                    break
            if note_widget is None:
                return False
            if isinstance(note_widget, Gtk.Label):
                row_text = note_widget.original_content.lower()  # pyright: ignore
            elif isinstance(note_widget, Gtk.Entry):
                row_text = note_widget.get_text().lower()
            return search_text in row_text  # pyright: ignore

        def about(self):
            return self.about.__doc__

        def code_explanation(self):
            return self.code_explanation.__doc__

    return MenuNotes
