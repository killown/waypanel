def get_plugin_metadata(_):
    about = (
        "This plugin adds a calendar popover to the panel, which is "
        "displayed when the user clicks on the clock widget. "
    )

    return {
        "id": "org.waypanel.plugin.calendar",
        "name": "Calendar",
        "version": "1.0.0",
        "enabled": True,
        "priority": 1,
        "deps": ["clock", "css_generator"],
        "description": about,
    }


def get_plugin_class():
    """
    The main plugin class entry point. ALL imports are deferred here
    to comply with the Waypanel loading architecture.
    Returns:
        type: The CalendarPlugin class.
    """
    from src.plugins.core._base import BasePlugin

    class CalendarPlugin(BasePlugin):
        """
        Plugin to integrate a calendar popover with the clock plugin.
        """

        def __init__(self, panel_instance):
            """
            Initialize the plugin.
            Args:
                panel_instance: The main panel instance provided by the framework.
            """
            super().__init__(panel_instance)
            self.popover_calendar = None
            self.calendar = None
            self.add_hint(
                [
                    "Settings controlling the layout, spacing, and margins of the Calendar popover's internal grid."
                ],
                ["layout"],
            )
            self.layout_row_spacing = self.get_plugin_setting(
                ["layout", "row_spacing"], 10
            )
            self.add_hint(
                ["Vertical spacing (in pixels) between rows in the calendar grid."],
                ["layout", "row_spacing"],
            )
            self.layout_column_spacing = self.get_plugin_setting(
                ["layout", "column_spacing"], 10
            )
            self.add_hint(
                [
                    "Horizontal spacing (in pixels) between columns in the calendar grid."
                ],
                ["layout", "column_spacing"],
            )
            self.layout_margin_top = self.get_plugin_setting(
                ["layout", "margin_to_top"], 10
            )
            self.add_hint(
                ["Top margin (in pixels) for the calendar grid content."],
                ["layout", "margin_to_top"],
            )
            self.layout_margin_bottom = self.get_plugin_setting(
                ["layout", "margin_to_bottom"], 10
            )
            self.add_hint(
                ["Bottom margin (in pixels) for the calendar grid content."],
                ["layout", "margin_to_bottom"],
            )
            self.layout_margin_start = self.get_plugin_setting(
                ["layout", "margin_from_start"], 10
            )
            self.add_hint(
                ["Start (left) margin (in pixels) for the calendar grid content."],
                ["layout", "margin_from_start"],
            )
            self.layout_margin_end = self.get_plugin_setting(
                ["layout", "margin_from_end"], 10
            )
            self.add_hint(
                ["End (right) margin (in pixels) for the calendar grid content."],
                ["layout", "margin_from_end"],
            )

        def setup_calendar(self):
            """Setup the calendar popover."""
            if "clock" not in self.plugin_loader.plugins:
                self.logger.error("Clock plugin is not loaded. Cannot append calendar.")
                return
            clock_plugin = self.plugin_loader.plugins["clock"]
            clock_button = clock_plugin.clock_button
            self.popover_calendar = self._gtk_helper.create_popover(
                clock_button, "calender-popover", has_arrow=False, offset=(0, 5)
            )
            self.grid = self.gtk.Grid()
            self.grid.set_row_spacing(self.layout_row_spacing)
            self.grid.set_column_spacing(self.layout_column_spacing)
            self.grid.set_margin_top(self.layout_margin_top)
            self.grid.set_margin_bottom(self.layout_margin_bottom)
            self.grid.set_margin_start(self.layout_margin_start)
            self.grid.set_margin_end(self.layout_margin_end)
            self.calendar = self.gtk.Calendar()
            self.calendar.add_css_class("calendar-widget")
            self.grid.attach(self.calendar, 0, 0, 1, 1)
            self.popover_calendar.set_child(self.grid)
            clock_button.connect("clicked", self.toggle_calendar)

        def on_start(self):
            """
            The primary activation method for the plugin.
            """
            self.setup_calendar()
            self.plugins["css_generator"].install_css("calendar.css")

        def toggle_calendar(self, *_) -> None:
            """Toggle the calendar popover."""
            if self.popover_calendar and self.popover_calendar.is_visible():
                self.popover_calendar.popdown()
            else:
                self.popover_calendar.popup()  # pyright: ignore

    return CalendarPlugin
