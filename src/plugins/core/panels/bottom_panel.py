def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.bottom_panel",
        "name": "Bottom Panel",
        "version": "1.0.0",
        "enabled": True,
        "priority": 10,
        "container": "bottom-panel",
        "deps": ["event_manager"],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class BottomPanelPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self._setup_boxes()
            self.add_css_class()

        def _setup_boxes(self):
            self.obj.bottom_panel_box_left = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 6
            )
            self.obj.bottom_panel_box_center = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 6
            )
            self.obj.bottom_panel_box_right = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 6
            )
            self.obj.bottom_panel_box_left.set_hexpand(False)
            self.obj.bottom_panel_box_right.set_hexpand(False)
            self.obj.bottom_panel_box_center.set_hexpand(True)
            self.obj.bottom_panel_box_center.set_halign(self.gtk.Align.FILL)
            self.obj.bottom_panel_box_left.set_halign(self.gtk.Align.START)
            self.obj.bottom_panel_box_right.set_halign(self.gtk.Align.END)
            self.obj.bottom_panel_box_full = self.gtk.Grid()
            self.obj.bottom_panel_box_full.set_column_homogeneous(False)
            self.obj.bottom_panel_box_full.set_hexpand(True)
            self.obj.bottom_panel_box_full.set_halign(self.gtk.Align.FILL)
            self.obj.bottom_panel_box_full.attach(
                self.obj.bottom_panel_box_left, 0, 0, 1, 1
            )
            self.obj.bottom_panel_box_full.attach_next_to(
                self.obj.bottom_panel_box_center,
                self.obj.bottom_panel_box_left,
                self.gtk.PositionType.RIGHT,
                1,
                1,
            )
            self.obj.bottom_panel_box_full.attach_next_to(
                self.obj.bottom_panel_box_right,
                self.obj.bottom_panel_box_center,
                self.gtk.PositionType.RIGHT,
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
                    self.obj.bottom_panel_box_left.add_css_class,
                    "bottom-panel-box-left",
                )
                self.update_widget_safely(
                    self.obj.bottom_panel_box_center.add_css_class,
                    "bottom-panel-box-center",
                )
                self.update_widget_safely(
                    self.obj.bottom_panel_box_right.add_css_class,
                    "bottom-panel-box-right",
                )
                self.update_widget_safely(
                    self.obj.bottom_panel_box_full.add_css_class,
                    "bottom-panel-box-full",
                )
                return False
            else:
                self.glib.timeout_add(100, self.add_css_class)
                return True

    return BottomPanelPlugin
