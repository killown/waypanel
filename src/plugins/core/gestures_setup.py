def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.gestures_setup",
        "name": "Gestures",
        "version": "1.0.1",
        "enabled": True,
    }


def get_plugin_class():
    import gi

    from gi.repository import Gtk, GLib  # pyright: ignore
    from src.shared.data_helpers import DataHelpers
    from typing import Callable

    gi.require_version("Gtk", "4.0")

    class GesturePlugin:
        def __init__(self, panel_instance):
            """Initialize the GesturePlugin."""
            self.obj = panel_instance
            self.logger = panel_instance.logger
            self.data_helper = DataHelpers()
            self.gestures = {}  # Store gesture references
            self.appended_actions = {}  # Store additional actions for each gesture

        def on_start(self):
            self.setup_gestures()

        def setup_gestures(self) -> None:
            """Set up gestures for the top panel."""
            GLib.idle_add(self.check_panel_boxes_ready)

        def check_panel_boxes_ready(self) -> bool:
            """Check if the required panel boxes are ready."""
            if (
                self.data_helper.validate_method(self.obj, "top_panel_box_left")
                and self.data_helper.validate_method(self.obj, "top_panel_box_center")
                and self.data_helper.validate_method(self.obj, "top_panel_box_full")
                and self.data_helper.validate_method(self.obj, "top_panel_box_right")
            ):
                self.logger.info("Panel boxes are ready. Setting up gestures...")
                self._setup_panel_gestures()
                return False
            else:
                self.logger.debug("Panel boxes not yet ready. Retrying...")
                return True

        def _setup_panel_gestures(self) -> None:
            """Set up gestures for the top panel (left, center, and right)."""
            # Gestures for the left section
            self.create_gesture(
                self.obj.top_panel_box_left,
                1,
                self.pos_left_left_click,
                self.pos_left_left_double_click,
            )
            self.create_gesture(
                self.obj.top_panel_box_left, 2, self.pos_left_middle_click
            )
            self.create_gesture(
                self.obj.top_panel_box_left, 3, self.pos_left_right_click
            )

            # Gestures for the center section
            self.create_gesture(
                self.obj.top_panel_box_center,
                1,
                self.pos_center_left_click,
                self.pos_center_left_double_click,
            )
            self.create_gesture(
                self.obj.top_panel_box_center, 2, self.pos_center_middle_click
            )
            self.create_gesture(
                self.obj.top_panel_box_center, 3, self.pos_center_right_click
            )

            # Gestures for the full section
            # Note: These are fallback handlers, but we also call them manually
            # from L/C/R to ensure 'Full' logic works everywhere.
            self.create_gesture(
                self.obj.top_panel_box_full, 2, self.pos_full_middle_click
            )
            self.create_gesture(
                self.obj.top_panel_box_full, 3, self.pos_full_right_click
            )

            # Gestures for the right section
            self.create_gesture(
                self.obj.top_panel_box_right,
                1,
                self.pos_right_left_click,
                self.pos_right_left_double_click,
            )
            self.create_gesture(
                self.obj.top_panel_box_right, 2, self.pos_right_middle_click
            )
            self.create_gesture(
                self.obj.top_panel_box_right, 3, self.pos_right_right_click
            )

        def create_gesture(
            self,
            widget: Gtk.Widget,
            mouse_button: int,
            callback: Callable,
            double_click_callback: Callable | None = None,
        ) -> None:
            """
            Create a gesture for a widget.
            Handles differentiating single and double clicks more robustly.
            """
            gesture = Gtk.GestureClick.new()
            gesture.set_exclusive(True)
            gesture.set_button(mouse_button)

            def pressed_handler(gesture, n_press, x, y):
                if n_press == 2 and double_click_callback:
                    self.logger.debug(f"Double-click detected on {widget.get_name()}")
                    self.execute_callback(double_click_callback)
                elif n_press > 2:
                    self.logger.debug(f"Multi-click ({n_press}) ignored")

            def released_handler(gesture, n_press, x, y):
                # Only execute single-click callback if it was actually a single press.
                # This prevents the single-click action from firing after the double-click.
                if n_press == 1:
                    self.execute_callback(callback)

            gesture.connect("pressed", pressed_handler)
            gesture.connect("released", released_handler)

            widget.add_controller(gesture)
            self.gestures[widget] = gesture

        def remove_gesture(self, widget) -> None:
            if widget in self.gestures:
                gesture = self.gestures[widget]
                widget.remove_controller(gesture)
                del self.gestures[widget]

        def execute_callback(self, callback: Callable, event=None) -> None:
            """Execute the callback and any appended actions."""
            callback(event)

            if callback.__name__ in self.appended_actions:
                for action in self.appended_actions[callback.__name__]:
                    action()

        def append_action(self, callback_name: str, action: Callable) -> None:
            if callback_name not in self.appended_actions:
                self.appended_actions[callback_name] = []

            current_ids = [id(a) for a in self.appended_actions[callback_name]]
            if id(action) not in current_ids:
                self.appended_actions[callback_name].append(action)

        # --- Callbacks ---

        def pos_left_left_double_click(self, *_):
            pass

        def pos_center_left_double_click(self, *_):
            pass

        def pos_right_left_double_click(self, *_):
            pass

        def pos_left_left_click(self, *_):
            pass

        def pos_left_middle_click(self, *_):
            self.pos_full_middle_click()

        def pos_left_right_click(self, *_):
            self.pos_full_right_click()

        def pos_center_left_click(self, *_):
            pass

        def pos_center_middle_click(self, *_):
            self.pos_full_middle_click()

        def pos_center_right_click(self, *_):
            self.pos_full_right_click()

        def pos_full_right_click(self, *_):
            pass

        def pos_full_middle_click(self, *_):
            pass

        def pos_right_left_click(self, *_):
            pass

        def pos_right_middle_click(self, *_):
            self.pos_full_middle_click()

        def pos_right_right_click(self, *_):
            self.pos_full_right_click()

        def about(self):
            return "Centralized gesture handling system with bubbling support."

        def code_explanation(self):
            return "Manages panel inputs, propagating specific zone clicks to global handlers."

    return GesturePlugin
