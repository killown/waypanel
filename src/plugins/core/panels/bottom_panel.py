from gi.repository import Gtk, GLib  # pyright: ignore
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "bottom-panel"
    return position, 1, 1


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return BottomPanelPlugin(panel_instance)


class BottomPanelPlugin(BasePlugin):
    def __init__(self, panel_instance):
        """Initialize the BottomPanelPlugin and set up its UI components.

        This plugin creates the structure for the bottom panel by setting up
        the necessary boxes (left, center, right, full) and attaching them to
        the main grid. It also ensures that CSS classes are applied once the
        widgets are ready.

        Args:
            panel_instance: The main panel object that provides access to shared resources
                            like configuration, logger, and widget containers.
        """
        super().__init__(panel_instance)
        self._setup_boxes()
        self.add_css_class()

    def _setup_boxes(self):
        """Setup left, center, right boxes and the main grid."""
        self.obj.bottom_panel_box_left = Gtk.Box()
        self.obj.bottom_panel_box_center = Gtk.Box()
        self.obj.bottom_panel_box_right = Gtk.Box()

        self.obj.bottom_panel_box_full = Gtk.Grid()
        self.obj.bottom_panel_box_full.set_column_homogeneous(True)

        # Arrange boxes in the grid
        self.obj.bottom_panel_box_full.attach(
            self.obj.bottom_panel_box_left, 0, 0, 1, 1
        )
        self.obj.bottom_panel_box_full.attach_next_to(
            self.obj.bottom_panel_box_center,
            self.obj.bottom_panel_box_left,
            Gtk.PositionType.RIGHT,
            1,
            1,
        )
        self.obj.bottom_panel_box_full.attach_next_to(
            self.obj.bottom_panel_box_right,
            self.obj.bottom_panel_box_center,
            Gtk.PositionType.RIGHT,
            1,
            1,
        )

        self.main_widget = (self.obj.bottom_panel_box_full, "set_content")

    def add_css_class(self):
        """Add CSS classes once widgets are ready."""
        if all(
            self.gtk_helper.is_widget_ready(box)
            for box in [
                self.obj.bottom_panel_box_left,
                self.obj.bottom_panel_box_center,
                self.obj.bottom_panel_box_right,
                self.obj.bottom_panel_box_full,
            ]
        ):
            self.update_widget_safely(
                self.obj.bottom_panel_box_left.add_css_class, "bottom-panel-box-left"
            )
            self.update_widget_safely(
                self.obj.bottom_panel_box_center.add_css_class,
                "bottom-panel-box-center",
            )
            self.update_widget_safely(
                self.obj.bottom_panel_box_right.add_css_class, "bottom-panel-box-right"
            )
            self.update_widget_safely(
                self.obj.bottom_panel_box_full.add_css_class, "bottom-panel-box-full"
            )
            return False
        else:
            GLib.timeout_add(100, self.add_css_class)
            return True
