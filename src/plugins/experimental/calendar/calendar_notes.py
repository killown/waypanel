import asyncio
import aiosqlite
import os
from datetime import datetime
from gi.repository import Gtk, GLib  # pyright: ignore
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = False
DEPS = ["calendar"]


def get_plugin_placement(panel_instance):
    return "background", 0, 0


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return CalendarNotesPlugin(panel_instance)


class CalendarNotesPlugin(BasePlugin):
    DB_PATH = os.path.expanduser("~/.config/waypanel/notes.db")

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.notes_box = None
        self.selected_date_label = None
        self.calendar = self.plugins["calendar"]
        self.calendar.calendar.connect("day-selected", self.on_day_selected)
        self.calendar.popover_calendar.connect(
            "notify::visible", self.on_calendar_visibility_changed
        )
        self.note_dates = set()
        GLib.timeout_add_seconds(1, self.attach_notes_to_calendar)

    async def load_note_dates(self):
        dates = await self.get_all_note_dates()
        self.note_dates = set(dates)
        self.mark_days_with_notes()

    def on_calendar_visibility_changed(self, popover, param):
        """Callback when the calendar popover visibility changes."""
        if popover.get_visible():
            date_time = self.calendar.calendar.get_date()
            year = date_time.get_year()
            month = date_time.get_month()
            day = date_time.get_day_of_month()
            selected_date = f"{year}-{month:02d}-{day:02d}"
            self.load_and_display_notes(selected_date)
            self.mark_days_with_notes()

    def mark_days_with_notes(self):
        calendar = self.plugins["calendar"].calendar
        for day in range(1, 32):
            calendar.unmark_day(day)
        for date_str in self.note_dates:
            try:
                year, month, day = map(int, date_str.split("-"))
                cal_year = calendar.get_date().get_year()
                cal_month = calendar.get_date().get_month()
                if year == cal_year and month == cal_month:
                    calendar.mark_day(day)
            except Exception as e:
                self.logger.warning(f"Failed to parse date {date_str}: {e}")

    def attach_notes_to_calendar(self):
        """Attach notes display to the calendar popover"""
        if "calendar" not in self.plugins:
            self.logger.warning("Calendar plugin not loaded yet. Retrying...")
            return True
        asyncio.run(self.load_note_dates())
        if (
            not hasattr(self.calendar, "popover_calendar")
            or not self.calendar.popover_calendar
        ):
            self.logger.warning("Calendar popover not initialized yet.")
            return True
        self.grid = self.plugins["calendar"].grid
        self.selected_date_label = Gtk.Label()
        self.selected_date_label.set_halign(Gtk.Align.START)
        self.selected_date_label.set_margin_top(10)
        self.grid.attach(self.selected_date_label, 0, 2, 2, 1)
        self.notes_box = Gtk.ListBox()
        self.notes_box.set_margin_top(10)
        self.notes_box.set_margin_start(10)
        self.notes_box.set_margin_end(10)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_child(self.notes_box)
        self.grid.attach(scrolled_window, 0, 3, 2, 1)
        today = datetime.now().strftime("%Y-%m-%d")
        self.load_and_display_notes(today)
        return False

    def on_day_selected(self, calendar):
        """Handle day selection in calendar and display notes."""
        date_time = calendar.get_date()
        year = date_time.get_year()
        month = date_time.get_month()
        day = date_time.get_day_of_month()
        selected_date = f"{year}-{month:02d}-{day:02d}"
        self.load_and_display_notes(selected_date)

    async def get_all_note_dates(self):
        try:
            async with aiosqlite.connect(self.DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT DATE(timestamp) FROM notes GROUP BY DATE(timestamp)"
                )
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to fetch note dates: {e}")
            return []

    async def fetch_notes_by_date(self, date_str):
        """Fetch notes from SQLite DB for given date"""
        try:
            async with aiosqlite.connect(self.DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT id, content FROM notes WHERE DATE(timestamp) = ? ORDER BY timestamp ASC",
                    (date_str,),
                )
                return await cursor.fetchall()
        except Exception as e:
            self.logger.error(f"Failed to fetch notes: {e}")
            return []

    def clear_container(self, container):
        """Remove all children from a Gtk.Container"""
        while container.get_first():
            container.remove(container.get_first())

    def load_and_display_notes(self, date_str):
        """Load and display notes for the given date"""
        if self.notes_box is not None:
            self.notes_box.remove_all()
        try:
            notes = asyncio.run(self.fetch_notes_by_date(date_str))
        except Exception as e:
            self.logger.error(f"Error fetching notes: {e}")
            return
        if not notes:
            no_notes_label = Gtk.Label(label="No notes found for this day.")
            no_notes_label.set_halign(Gtk.Align.START)
            self.notes_box.append(no_notes_label)
            self.notes_box.show_all()
            return
        for note_id, content in notes:
            first_space = content.find(" ")
            if first_space != -1:
                content = content[first_space + 1 :]
            note_label = Gtk.Label()
            note_label.set_max_width_chars(79)
            note_label.set_wrap(True)
            note_label.set_halign(Gtk.Align.START)
            note_label.set_margin_bottom(5)
            note_label.set_markup(
                f'<span font="DejaVu Sans Mono">{GLib.markup_escape_text(content)}</span>'
            )
            row = Gtk.ListBoxRow()
            row.set_child(note_label)
            self.notes_box.append(row)
        self.notes_box.show_all()

    def about(self):
        """
        This plugin extends the calendar with a notes feature, allowing
        users to view and manage notes associated with specific dates
        using a persistent SQLite database.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this plugin is based on an architectural
        pattern of dependency injection and asynchronous data
        handling. Its key principles are:
        1.  **UI Augmentation**: This plugin operates as a dependent
            component. It does not create its own top-level window or
            button but instead dynamically attaches a notes display
            (`Gtk.ListBox`) to the existing calendar popover, enhancing
            its functionality.
        2.  **Asynchronous Data Persistence**: All note data is stored
            in a local SQLite database managed by the `aiosqlite`
            library. This allows for non-blocking database operations,
            which is essential for keeping the application responsive
            while fetching or saving notes.
        3.  **Cross-Event Loop Communication**: The plugin connects
            synchronous GTK UI events, such as a day being selected, to
            its asynchronous data fetching routines by using `asyncio.run`.
            This is a crucial pattern for bridging the gap between GTK's
            main loop and `asyncio`'s event loop.
        4.  **Dynamic UI and Data Mapping**: The plugin provides a visual
            cue to the user by marking days on the calendar that have
            associated notes. It dynamically loads and displays the notes
            in a listbox, ensuring the UI accurately reflects the data
            for the currently selected date.
        """
        return self.code_explanation.__doc__
