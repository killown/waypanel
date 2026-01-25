def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.bottom_panel",
        "name": "Bottom Panel",
        "version": "1.0.1",
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
            # Left, Center, and Right Containers
            self.obj.bottom_panel_box_left = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 6
            )
            self.obj.bottom_panel_box_center = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 0
            )
            self.obj.bottom_panel_box_right = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 6
            )

            self.obj.bottom_panel_center_box = self.gtk.CenterBox()
            self.obj.bottom_panel_center_box.set_start_widget(
                self.obj.bottom_panel_box_left
            )
            self.obj.bottom_panel_center_box.set_center_widget(
                self.obj.bottom_panel_box_center
            )
            self.obj.bottom_panel_center_box.set_can_focus(False)
            self.obj.bottom_panel_center_box.set_end_widget(
                self.obj.bottom_panel_box_right
            )

            self.obj.bottom_panel_scrolled_window = self.gtk.ScrolledWindow()
            self.obj.bottom_panel_scrolled_window.set_policy(
                self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.NEVER
            )
            self.obj.bottom_panel_scrolled_window.set_child(
                self.obj.bottom_panel_center_box
            )

            self.obj.bottom_panel_scrolled_window.set_focus_on_click(False)
            self.obj.bottom_panel_center_box.set_focus_on_click(False)

            self.main_widget = (self.obj.bottom_panel_scrolled_window, "set_child")

        def add_css_class(self):
            """Add CSS classes once widgets are ready."""
            widgets = [
                self.obj.bottom_panel_box_left,
                self.obj.bottom_panel_box_center,
                self.obj.bottom_panel_box_right,
                self.obj.bottom_panel_center_box,
                self.obj.bottom_panel_scrolled_window,
            ]

            if all(self.is_widget_ready(w) for w in widgets):
                self.obj.bottom_panel_box_left.add_css_class("bottom-panel-box-left")
                self.obj.bottom_panel_box_center.add_css_class(
                    "bottom-panel-box-center"
                )
                self.obj.bottom_panel_box_right.add_css_class("bottom-panel-box-right")
                self.obj.bottom_panel_center_box.add_css_class(
                    "bottom-panel-center-box"
                )
                self.obj.bottom_panel_scrolled_window.add_css_class(
                    "bottom-panel-scrolled-window"
                )
                return False
            else:
                self.glib.timeout_add(100, self.add_css_class)
                return True

    return BottomPanelPlugin
