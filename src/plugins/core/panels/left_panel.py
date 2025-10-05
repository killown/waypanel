from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "left-panel"
    return position, 1, 1


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return LeftPanelPlugin(panel_instance)


class LeftPanelPlugin(BasePlugin):
    def __init__(self, panel_instance):
        """Initialize the LeftPanelPlugin and set up its UI components.
        This plugin creates the structure for the left panel by setting up
        the necessary boxes (top, center, bottom, full) and attaching them to
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
        """Setup top, center, bottom boxes for vertical alignment."""
        self.obj.left_panel_box_top = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
        self.obj.left_panel_box_center = self.gtk.Box.new(
            self.gtk.Orientation.VERTICAL, 0
        )
        self.obj.left_panel_box_bottom = self.gtk.Box.new(
            self.gtk.Orientation.VERTICAL, 0
        )
        self.obj.left_panel_box_full = self.gtk.Box.new(
            self.gtk.Orientation.VERTICAL, 0
        )
        self.obj.left_panel_box_full.set_spacing(10)
        self.obj.left_panel_box_center.set_vexpand(True)
        self.obj.left_panel_box_center.set_valign(self.gtk.Align.CENTER)
        self.obj.left_panel_box_full.append(self.obj.left_panel_box_top)
        self.obj.left_panel_box_full.append(self.obj.left_panel_box_center)
        self.obj.left_panel_box_full.append(self.obj.left_panel_box_bottom)
        self.main_widget = (self.obj.left_panel_box_full, "set_content")

    def add_css_class(self):
        """Add CSS classes once widgets are ready."""
        boxes = [
            self.obj.left_panel_box_top,
            self.obj.left_panel_box_center,
            self.obj.left_panel_box_bottom,
            self.obj.left_panel_box_full,
        ]
        if all(self.gtk_helper.is_widget_ready(box) for box in boxes):
            self.update_widget_safely(
                self.obj.left_panel_box_top.add_css_class, "left-panel-box-top"
            )
            self.update_widget_safely(
                self.obj.left_panel_box_center.add_css_class, "left-panel-box-center"
            )
            self.update_widget_safely(
                self.obj.left_panel_box_bottom.add_css_class, "left-panel-box-bottom"
            )
            self.update_widget_safely(
                self.obj.left_panel_box_full.add_css_class, "left-panel-box-full"
            )
            return False
        else:
            self.glib.timeout_add(100, self.add_css_class)
            return True
