# FILE: ~/.config/waypanel/user_plugins/calendar_notes.py

import asyncio
import aiosqlite
import os
from datetime import datetime

from gi.repository import Gtk, GLib
from src.plugins.core._base import BasePlugin


ENABLE_PLUGIN = True
DEPS = ["calendar"]  # Only depend on calendar plugin


def get_plugin_placement(panel_instance):
    return "background", 0, 0  # No UI of its own; modifies calendar UI


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

        # Schedule attaching to calendar after it's initialized
        GLib.timeout_add_seconds(1, self.attach_notes_to_calendar)

    async def load_note_dates(self):
        dates = await self.get_all_note_dates()
        self.note_dates = set(dates)
        self.mark_days_with_notes()

    def on_calendar_visibility_changed(self, popover, param):
        """Callback when the calendar popover visibility changes."""
        if popover.get_visible():
            # Get current date and reload notes
            date_time = self.calendar.calendar.get_date()
            year = date_time.get_year()
            month = date_time.get_month()  # 1-based
            day = date_time.get_day_of_month()

            selected_date = f"{year}-{month:02d}-{day:02d}"
            self.load_and_display_notes(selected_date)
            self.mark_days_with_notes()  # Optional: re-mark days with notes

    def mark_days_with_notes(self):
        calendar = self.plugins["calendar"].calendar

        # Unmark all days first
        for day in range(1, 32):  # Days 1–31
            calendar.unmark_day(day)

        # Only mark current month/year's matching days
        for date_str in self.note_dates:
            try:
                year, month, day = map(int, date_str.split("-"))
                # Only mark if the date matches the currently displayed month/year
                cal_year = calendar.get_date().get_year()
                cal_month = calendar.get_date().get_month()  # 1-based
                if year == cal_year and month == cal_month:
                    calendar.mark_day(day)
            except Exception as e:
                self.logger.warning(f"Failed to parse date {date_str}: {e}")

    def attach_notes_to_calendar(self):
        """Attach notes display to the calendar popover"""
        if "calendar" not in self.plugins:
            self.logger.warning("Calendar plugin not loaded yet. Retrying...")
            return True  # Keep retrying
        asyncio.run(self.load_note_dates())

        if (
            not hasattr(self.calendar, "popover_calendar")
            or not self.calendar.popover_calendar
        ):
            self.logger.warning("Calendar popover not initialized yet.")
            return True  # Retry

        # Get calendar widget from the plugin
        self.grid = self.plugins["calendar"].grid

        # Add label to show selected date
        self.selected_date_label = Gtk.Label()
        self.selected_date_label.set_halign(Gtk.Align.START)
        self.selected_date_label.set_margin_top(10)
        self.grid.attach(self.selected_date_label, 0, 2, 2, 1)  # Row below calendar

        # Create box for notes
        self.notes_box = Gtk.ListBox()
        self.notes_box.set_margin_top(10)
        self.notes_box.set_margin_start(10)
        self.notes_box.set_margin_end(10)
        self.grid.attach(self.notes_box, 0, 2, 2, 1)

        # Load today’s notes by default
        today = datetime.now().strftime("%Y-%m-%d")
        self.load_and_display_notes(today)

        return False  # Stop repeating

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
        # Clear previous notes
        if self.notes_box is not None:
            if hasattr(self.notes_box, "remove_all"):
                self.notes_box.remove_all()

        # Fetch notes for this date
        try:
            notes = asyncio.run(self.fetch_notes_by_date(date_str))
        except Exception as e:
            self.logger.error(f"Error fetching notes: {e}")
            return

        if not notes:
            no_notes_label = Gtk.Label(label="No notes found for this day.")
            no_notes_label.set_halign(Gtk.Align.START)
            self.notes_box.append(no_notes_label)
            return

        for note_id, content in notes:
            content = " ".join(content.split()[1:])  # skip the date

            # Create label for the note
            note_label = Gtk.Label()
            note_label.set_markup(
                f'<span font="DejaVu Sans Mono">{GLib.markup_escape_text(content)}</span>'
            )
            note_label.set_wrap(True)
            note_label.set_halign(Gtk.Align.START)
            note_label.set_margin_bottom(5)

            # Wrap the label in a ListBoxRow
            row = Gtk.ListBoxRow()
            row.set_child(note_label)

            # Append the row to the listbox
            self.notes_box.append(row)
