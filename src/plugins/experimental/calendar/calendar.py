def get_plugin_metadata(_):
    return {        
        "id": "org.waypanel.plugin.calendar",
        "name": "Calendar",
        "version": "1.0.0",
        "enabled": True, "priority": 1, "deps": ["clock"]}


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class CalendarPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover_calendar = None
            self.calendar = None

        def setup_calendar(self):
            """Setup the calendar popover."""
            if "clock" not in self.obj.plugins:
                self.logger.error("Clock plugin is not loaded. Cannot append calendar.")
                return
            clock_plugin = self.obj.plugins["clock"]
            clock_button = clock_plugin.clock_button
            self.popover_calendar = self._gtk_helper.create_popover(
                clock_button, "calender-popover", has_arrow=False, offset=(0, 5)
            )
            self.grid = self.gtk.Grid()
            self.grid.set_row_spacing(10)
            self.grid.set_column_spacing(10)
            self.grid.set_margin_top(10)
            self.grid.set_margin_bottom(10)
            self.grid.set_margin_start(10)
            self.grid.set_margin_end(10)
            self.calendar = self.gtk.Calendar()
            self.calendar.add_css_class("calendar-widget")
            self.grid.attach(self.calendar, 0, 0, 1, 1)
            self.popover_calendar.set_child(self.grid)
            clock_button.connect("clicked", self.toggle_calendar)

        def on_start(self):
            self.setup_calendar()

        def toggle_calendar(self, *_):
            """Toggle the calendar popover."""
            if self.popover_calendar and self.popover_calendar.is_visible():
                self.popover_calendar.popdown()
            else:
                self.popover_calendar.popup()  # pyright: ignore

        def about(self):
            """
            This plugin adds a calendar popover to the panel, which is
            displayed when the user clicks on the clock widget.
            """
            return self.about.__doc__

        def code_explanation(self):
            """
            The core logic of this plugin is based on an architectural
            pattern of modular UI composition and event-driven behavior.
            Its design is based on these principles:
            1.  **Dependent UI Augmentation**: This plugin does not create its
                own panel button. Instead, it explicitly depends on the `clock`
                plugin and attaches its `self.gtk.Popover` to the clock's button.
                This approach creates a cohesive user experience where two
                logically related components are visually and functionally
                integrated.
            2.  **Modular UI Construction**: The calendar interface is built
                by composing several standard GTK widgets: a `self.gtk.Grid` for
                layout, a `self.gtk.Calendar` widget for the core functionality,
                and a `self.gtk.Popover` to serve as a floating, temporary window
                for the entire structure.
            3.  **Event-Driven Interaction**: The plugin's primary interaction
                is handled by connecting the `clicked` signal of the clock
                button to the `toggle_calendar` method. This simple event
                handler controls the visibility of the popover, adhering
                to a standard user interaction model.
            """
            return self.code_explanation.__doc__

    return CalendarPlugin
