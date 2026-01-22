class TaskbarGestures:
    """Handles Gtk Gestures and click event logic for taskbar items."""

    def __init__(self, plugin_instance):
        """Initializes the gesture handler.

        Args:
            plugin_instance: The TaskbarPlugin instance.
        """
        self.plugin = plugin_instance

    def setup_button_gestures(self, button):
        """Attaches right, middle, and motion controllers to a button."""
        from gi.repository import Gtk

        # Right Click Logic (Menu)
        rc = Gtk.GestureClick(button=3)
        rc.connect(
            "pressed",
            lambda g, n, x, y: self.plugin.menu_handler.show(g.get_widget(), x, y),
        )
        button.add_controller(rc)

        # Middle Click Logic (Restore Last Focused)
        mc = Gtk.GestureClick(button=2)
        mc.connect("pressed", self._on_middle_click_restore)
        button.add_controller(mc)

        # Motion Logic (Hover Effects)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_hover_enter)
        motion.connect("leave", self._on_hover_leave)
        button.add_controller(motion)

    def _on_middle_click_restore(self, gesture, n_press, x, y):
        """Triggers the restore logic from the view handler."""
        btn = gesture.get_widget()
        identifier = next(
            (k for k, v in self.plugin.in_use_buttons.items() if v == btn), None
        )
        if identifier:
            self.plugin.view_handler.restore_group_focus(identifier)

    def _on_hover_enter(self, controller, x, y):
        """Applies compositor focus effect on hover."""
        btn = controller.get_widget()
        view_id = getattr(btn, "view_id", None)
        if view_id:
            view = self.plugin.wf_helper.is_view_valid(view_id)
            if view:
                self.plugin.wf_helper.view_focus_effect_selected(view, 0.80, True)

    def _on_hover_leave(self, controller):
        """Removes compositor focus effect."""
        btn = controller.get_widget()
        view_id = getattr(btn, "view_id", None)
        if view_id:
            view = self.plugin.wf_helper.is_view_valid(view_id)
            if view:
                self.plugin.wf_helper.view_focus_effect_selected(view, False)
