def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.top_panel",
        "name": "Top Panel",
        "version": "1.0.0",
        "enabled": True,
        "priority": 10,
        "container": "top-panel",
        "deps": ["event_manager"],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class TopPanelPlugin(BasePlugin):
        def __init__(self, panel_instance):
            """
            Initialize the TopPanelPlugin and prepare its UI structure.
            """
            super().__init__(panel_instance)
            self._deferred_widgets_attached = False
            self.is_top_panel_ready = False
            self._setup_panel_boxes()
            self.add_css_class()
            self.plugins["css_generator"].install_css("top-panel.css")

        def _attach_widget_to_grid_next_to(
            self, grid, widget_to_attach, relative_widget, position_type, width, height
        ):
            if widget_to_attach.get_parent() is None:
                grid.attach_next_to(
                    widget_to_attach,
                    relative_widget,
                    position_type,
                    width,
                    height,
                )

        def _setup_panel_boxes(self):
            # Left Box Setup
            self.obj.top_panel_box_widgets_left = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 6
            )
            self.obj.top_panel_box_left = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 0
            )
            self.obj.top_panel_box_widgets_left.set_homogeneous(True)
            self.obj.top_panel_box_left.append(self.obj.top_panel_box_widgets_left)

            # Right Box & Systray Setup
            self.obj.top_panel_box_systray = self.gtk.Box()
            self.obj.top_panel_box_for_buttons = self.gtk.Box()
            self.obj.top_panel_box_right = self.gtk.Box()

            self.spacer = self.gtk.Separator(
                orientation=self.gtk.Orientation.HORIZONTAL
            )
            self.spacer.set_hexpand(True)
            self.spacer.add_css_class("right-box-spacer")
            self.obj.top_panel_box_right.append(self.spacer)

            self.obj.top_panel_grid_right = self.gtk.Grid()
            self.obj.top_panel_grid_right.attach(
                self.obj.top_panel_box_right, 1, 0, 1, 2
            )

            self._attach_widget_to_grid_next_to(
                self.obj.top_panel_grid_right,
                self.obj.top_panel_box_systray,
                self.obj.top_panel_box_right,
                self.gtk.PositionType.RIGHT,
                1,
                2,
            )
            self._attach_widget_to_grid_next_to(
                self.obj.top_panel_grid_right,
                self.obj.top_panel_box_for_buttons,
                self.obj.top_panel_box_systray,
                self.gtk.PositionType.RIGHT,
                1,
                2,
            )

            # Center Box Setup
            self.obj.top_panel_box_center = self.gtk.Box()
            self.obj.top_panel_box_center.set_halign(self.gtk.Align.CENTER)
            self.obj.top_panel_box_center.set_valign(self.gtk.Align.CENTER)
            self.obj.top_panel_box_center.set_hexpand(False)

            # Main Grid Assembly
            self.obj.top_panel_box_full = self.gtk.Grid()
            self.obj.top_panel_box_full.set_column_homogeneous(True)
            self.obj.top_panel_box_full.attach(self.obj.top_panel_box_left, 1, 0, 1, 2)

            self._attach_widget_to_grid_next_to(
                self.obj.top_panel_box_full,
                self.obj.top_panel_box_center,
                self.obj.top_panel_box_left,
                self.gtk.PositionType.RIGHT,
                1,
                2,
            )
            self._attach_widget_to_grid_next_to(
                self.obj.top_panel_box_full,
                self.obj.top_panel_grid_right,
                self.obj.top_panel_box_center,
                self.gtk.PositionType.RIGHT,
                1,
                3,
            )

            # Scrolled Window Wrapper
            self.obj.top_panel_scrolled_window = self.gtk.ScrolledWindow()
            self.obj.top_panel_scrolled_window.set_policy(
                self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.NEVER
            )
            self.obj.top_panel_scrolled_window.set_child(self.obj.top_panel_box_full)

            # Prevent the scrolled window from trapping clicks
            self.obj.top_panel_scrolled_window.set_focus_on_click(False)

            self.main_widget = (self.obj.top_panel_scrolled_window, "set_child")
            self.is_top_panel_ready = True

        def add_css_class(self):
            widgets = [
                self.obj.top_panel_box_left,
                self.obj.top_panel_box_widgets_left,
                self.obj.top_panel_box_right,
                self.obj.top_panel_box_systray,
                self.obj.top_panel_box_center,
                self.obj.top_panel_box_full,
                self.obj.top_panel_scrolled_window,
            ]

            if all(self.is_widget_ready(w) for w in widgets):
                self.obj.top_panel_box_left.add_css_class("top-panel-box-left")
                self.obj.top_panel_box_widgets_left.add_css_class(
                    "top-panel-box-widgets-left"
                )
                self.obj.top_panel_box_right.add_css_class("top-panel-box-right")
                self.obj.top_panel_box_systray.add_css_class("top-panel-box-systray")
                self.obj.top_panel_box_center.add_css_class("top-panel-box-center")
                self.obj.top_panel_box_full.add_css_class("top-panel-box-full")
                self.obj.top_panel_scrolled_window.add_css_class(
                    "top-panel-scrolled-window"
                )
                return False
            else:
                self.glib.timeout_add(100, self.add_css_class)
                return True

    return TopPanelPlugin
