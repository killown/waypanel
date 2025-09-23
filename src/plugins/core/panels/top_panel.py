from gi.repository import Gtk, GLib
from src.plugins.core._base import BasePlugin

# Enable or disable the plugin
ENABLE_PLUGIN = True
DEPS = ["event_manager"]


def get_plugin_placement(panel_instance):
    position = "top-panel"
    return position, 1, 1


def initialize_plugin(panel_instance):
    """
    Initialize the plugin.
    Args:
        panel_instance: The main panel object from panel.py
    """
    if ENABLE_PLUGIN:
        return TopPanelPlugin(panel_instance)


class TopPanelPlugin(BasePlugin):
    def __init__(self, panel_instance):
        """
        Initialize the TopPanelPlugin and prepare its UI structure.

        Sets up the internal box layout for the top panel (left, systray, button container),
        applies CSS styling, and initializes a readiness flag to indicate when the panel
        is fully constructed and ready for use.

        Args:
            panel_instance: The main panel object from panel.py,
                            providing access to shared resources and widgets.
        """
        super().__init__(panel_instance)
        self._setup_panel_boxes()
        self.add_css_class()
        self.is_top_panel_ready = False

    def _setup_panel_boxes(self):
        """Setup panel boxes and related configurations."""
        self.obj.top_panel_box_left = Gtk.Box()
        self.obj.top_panel_box_systray = Gtk.Box()
        self.obj.top_panel_box_for_buttons = Gtk.Box()
        self.obj.top_panel_box_widgets_left = Gtk.Box()
        self.update_widget_safely(
            self.obj.top_panel_box_left.append, self.obj.top_panel_box_widgets_left
        )
        self.obj.top_panel_box_right = Gtk.Box()
        self.spacer = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)

        # will set position of new widgets Gtk.Align.END
        self.spacer.set_hexpand(True)
        self.spacer.add_css_class("right-box-spacer")
        self.update_widget_safely(self.obj.top_panel_box_right.append, self.spacer)
        self.obj.top_panel_grid_right = Gtk.Grid()
        self.obj.top_panel_grid_right.attach(self.obj.top_panel_box_right, 1, 0, 1, 2)
        self.obj.top_panel_grid_right.attach_next_to(
            self.obj.top_panel_box_systray,
            self.obj.top_panel_box_right,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )
        self.obj.top_panel_grid_right.attach_next_to(
            self.obj.top_panel_box_for_buttons,
            self.obj.top_panel_box_systray,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )

        self.obj.top_panel_box_center = Gtk.Box()
        self.obj.top_panel_box_full = Gtk.Grid()
        self.obj.top_panel_box_full.set_column_homogeneous(True)
        self.obj.top_panel_box_full.attach(self.obj.top_panel_box_left, 1, 0, 1, 2)
        self.obj.top_panel_box_full.attach_next_to(
            self.obj.top_panel_box_center,
            self.obj.top_panel_box_left,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )
        self.obj.top_panel_box_full.attach_next_to(
            self.obj.top_panel_grid_right,
            self.obj.top_panel_box_center,
            Gtk.PositionType.RIGHT,
            1,
            3,
        )
        self.obj.top_panel_box_center.set_halign(Gtk.Align.CENTER)
        self.obj.top_panel_box_center.set_valign(Gtk.Align.CENTER)
        self.obj.top_panel_box_center.set_hexpand(False)

        self.main_widget = (self.obj.top_panel_box_full, "set_content")
        self.is_top_panel_ready = True

    def add_css_class(self):
        if (
            self.gtk_helper.is_widget_ready(self.obj.top_panel_box_left)
            and self.gtk_helper.is_widget_ready(self.obj.top_panel_box_widgets_left)
            and self.gtk_helper.is_widget_ready(self.obj.top_panel_box_right)
            and self.gtk_helper.is_widget_ready(self.obj.top_panel_box_systray)
            and self.gtk_helper.is_widget_ready(self.obj.top_panel_box_center)
            and self.gtk_helper.is_widget_ready(self.obj.top_panel_box_full)
        ):
            # Apply CSS classes
            self.update_widget_safely(
                self.obj.top_panel_box_left.add_css_class, "top-panel-box-left"
            )
            self.update_widget_safely(
                self.obj.top_panel_box_widgets_left.add_css_class,
                "top-panel-box-widgets-left",
            )
            self.update_widget_safely(
                self.obj.top_panel_box_right.add_css_class, "top-panel-box-right"
            )
            self.update_widget_safely(
                self.obj.top_panel_box_systray.add_css_class, "top-panel-box-systray"
            )
            self.update_widget_safely(
                self.obj.top_panel_box_center.add_css_class, "top-panel-box-center"
            )
            self.update_widget_safely(
                self.obj.top_panel_box_full.add_css_class, "top-panel-box-full"
            )

            return False
        else:
            # Retry after a delay
            GLib.timeout_add(1, self.add_css_class)
            return True
