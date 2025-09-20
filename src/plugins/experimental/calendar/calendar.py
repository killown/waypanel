import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True

# Load the plugin only after essential plugins are loaded
DEPS = ["clock"]


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    """Initialize the calendar plugin."""
    if ENABLE_PLUGIN:
        calendar_plugin = CalendarPlugin(panel_instance)
        calendar_plugin.setup_calendar()
        return calendar_plugin


class CalendarPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_calendar = None
        self.calendar = None

    def setup_calendar(self):
        """Setup the calendar popover."""
        # Ensure the clock plugin is loaded
        if "clock" not in self.obj.plugins:
            self.log_error("Clock plugin is not loaded. Cannot append calendar.")
            return

        # Get the clock button from the clock plugin
        clock_plugin = self.obj.plugins["clock"]
        clock_button = clock_plugin.clock_button

        # Create the calendar popover
        self.popover_calendar = Gtk.Popover.new()
        self.popover_calendar.set_parent(clock_button)
        self.popover_calendar.set_has_arrow(False)

        # Create a self.grid to hold the calendar
        self.grid = Gtk.Grid()
        self.grid.set_row_spacing(10)
        self.grid.set_column_spacing(10)
        self.grid.set_margin_top(10)
        self.grid.set_margin_bottom(10)
        self.grid.set_margin_start(10)
        self.grid.set_margin_end(10)

        # Create calendar widget
        self.calendar = Gtk.Calendar()
        self.calendar.add_css_class("calendar-widget")

        # Add calendar to self.grid
        self.grid.attach(self.calendar, 0, 0, 1, 1)

        # Set self.grid as the child of the popover
        self.popover_calendar.set_child(self.grid)

        # Connect toggle behavior
        clock_button.connect("clicked", self.toggle_calendar)

    def toggle_calendar(self, *_):
        """Toggle the calendar popover."""
        if self.popover_calendar and self.popover_calendar.is_visible():
            self.popover_calendar.popdown()
        else:
            self.popover_calendar.popup()

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
            plugin and attaches its `Gtk.Popover` to the clock's button.
            This approach creates a cohesive user experience where two
            logically related components are visually and functionally
            integrated.

        2.  **Modular UI Construction**: The calendar interface is built
            by composing several standard GTK widgets: a `Gtk.Grid` for
            layout, a `Gtk.Calendar` widget for the core functionality,
            and a `Gtk.Popover` to serve as a floating, temporary window
            for the entire structure.

        3.  **Event-Driven Interaction**: The plugin's primary interaction
            is handled by connecting the `clicked` signal of the clock
            button to the `toggle_calendar` method. This simple event
            handler controls the visibility of the popover, adhering
            to a standard user interaction model.
        """
        return self.code_explanation.__doc__
