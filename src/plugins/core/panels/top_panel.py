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
            Sets up the internal box layout for the top panel (left, systray, button container),
            applies CSS styling, and initializes a readiness flag to indicate when the panel
            is fully constructed and ready for use.
            Args:
                panel_instance: The main panel object from panel.py,
                                providing access to shared resources and widgets.
            """
            super().__init__(panel_instance)
            # FIX: Flag to ensure deferred widgets are attached only once
            self._deferred_widgets_attached = False
            self._setup_panel_boxes()
            self.add_css_class()
            self.is_top_panel_ready = False

        def _attach_widget_to_grid_next_to(
            self, grid, widget_to_attach, relative_widget, position_type, width, height
        ):
            """
            A reusable internal method to attach a widget to a self.gtk.Grid next to another widget.
            This centralizes the self.gtk.Grid.attach_next_to call, allowing callers to easily
            specify any self.gtk.PositionType (LEFT, RIGHT, TOP, BOTTOM).
            """
            # FIX: Only attach if the widget does not have a parent yet.
            if widget_to_attach.get_parent() is None:
                grid.attach_next_to(
                    widget_to_attach,
                    relative_widget,
                    position_type,
                    width,
                    height,
                )

        def _setup_panel_boxes(self):
            """Setup panel boxes and related configurations."""
            self.obj.top_panel_box_widgets_left = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 0
            )
            self.obj.top_panel_box_left = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 0
            )
            self.obj.top_panel_box_widgets_left.set_homogeneous(True)
            self.obj.top_panel_box_widgets_left.set_spacing(6)
            self.update_widget_safely(
                self.obj.top_panel_box_left.append, self.obj.top_panel_box_widgets_left
            )
            self.obj.top_panel_box_systray = self.gtk.Box()
            self.obj.top_panel_box_for_buttons = self.gtk.Box()
            self.obj.top_panel_box_right = self.gtk.Box()
            self.spacer = self.gtk.Separator(
                orientation=self.gtk.Orientation.HORIZONTAL
            )
            self.spacer.set_hexpand(True)
            self.spacer.add_css_class("right-box-spacer")
            self.update_widget_safely(self.obj.top_panel_box_right.append, self.spacer)
            self.obj.top_panel_grid_right = self.gtk.Grid()

            if self.obj.top_panel_box_right.get_parent() is None:
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
            self.obj.top_panel_box_center = self.gtk.Box()
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
            self.obj.top_panel_scrolled_window = self.gtk.ScrolledWindow()
            self.obj.top_panel_scrolled_window.set_policy(
                self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.NEVER
            )
            self.obj.top_panel_scrolled_window.set_child(self.obj.top_panel_box_full)
            self.obj.top_panel_box_center.set_halign(self.gtk.Align.CENTER)
            self.obj.top_panel_box_center.set_valign(self.gtk.Align.CENTER)
            self.obj.top_panel_box_center.set_hexpand(False)
            self.main_widget = (self.obj.top_panel_scrolled_window, "set_content")
            self.is_top_panel_ready = True

        def add_css_class(self):
            if (
                self.is_widget_ready(self.obj.top_panel_box_left)
                and self.is_widget_ready(self.obj.top_panel_box_widgets_left)
                and self.is_widget_ready(self.obj.top_panel_box_right)
                and self.is_widget_ready(self.obj.top_panel_box_systray)
                and self.is_widget_ready(self.obj.top_panel_box_center)
                and self.is_widget_ready(self.obj.top_panel_box_full)
                and self.is_widget_ready(self.obj.top_panel_scrolled_window)
            ):
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
                    self.obj.top_panel_box_systray.add_css_class,
                    "top-panel-box-systray",
                )
                self.update_widget_safely(
                    self.obj.top_panel_box_center.add_css_class, "top-panel-box-center"
                )
                self.update_widget_safely(
                    self.obj.top_panel_box_full.add_css_class, "top-panel-box-full"
                )
                self.update_widget_safely(
                    self.obj.top_panel_scrolled_window.add_css_class,
                    "top-panel-scrolled-window",
                )
                return False
            else:
                self.glib.timeout_add(100, self.add_css_class)
                return True

    return TopPanelPlugin
