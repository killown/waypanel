def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.gestures_setup",
        "name": "Gestures",
        "version": "1.0.4",
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
            self.gestures = {}
            self.appended_actions = {}
            self._click_timeout_id = None

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
                self._setup_panel_gestures()
                return False
            return True

        def create_gesture(
            self,
            widget: Gtk.Widget,
            mouse_button: int,
            callback: Callable,
            double_click_callback: Callable | None = None,
            instant: bool = False,
        ) -> None:
            """
            Create a gesture for a widget.
            If instant=True, triggers on 'pressed' to eliminate software lag.
            """
            gesture = Gtk.GestureClick.new()
            gesture.set_exclusive(True)
            gesture.set_button(mouse_button)

            def on_pressed(gesture, n_press, x, y):
                if instant:
                    self.execute_callback(callback)
                    return

                if n_press == 2 and self._click_timeout_id:
                    GLib.source_remove(self._click_timeout_id)
                    self._click_timeout_id = None
                    if double_click_callback:
                        self.execute_callback(double_click_callback)

            def on_released(gesture, n_press, x, y):
                if instant:
                    return

                if n_press == 1:
                    if double_click_callback:
                        self._click_timeout_id = GLib.timeout_add(
                            200, self._handle_single_click, callback
                        )
                    else:
                        self.execute_callback(callback)

            gesture.connect("pressed", on_pressed)
            gesture.connect("released", on_released)
            widget.add_controller(gesture)
            self.gestures[widget] = gesture

        def remove_gesture(self, widget) -> None:
            """Remove gesture controller from widget."""
            if widget in self.gestures:
                gesture = self.gestures[widget]
                widget.remove_controller(gesture)
                del self.gestures[widget]

        def _handle_single_click(self, callback):
            self._click_timeout_id = None
            self.execute_callback(callback)
            return False

        def _setup_panel_gestures(self) -> None:
            """Configure panel sections with specific click behaviors."""
            # Left
            self.create_gesture(
                self.obj.top_panel_box_left,
                1,
                self.pos_left_left_click,
                self.pos_left_left_double_click,
            )
            self.create_gesture(
                self.obj.top_panel_box_left, 2, self.pos_left_middle_click, instant=True
            )
            self.create_gesture(
                self.obj.top_panel_box_left, 3, self.pos_left_right_click, instant=True
            )

            # Center
            self.create_gesture(
                self.obj.top_panel_box_center,
                1,
                self.pos_center_left_click,
                self.pos_center_left_double_click,
            )
            self.create_gesture(
                self.obj.top_panel_box_center,
                2,
                self.pos_center_middle_click,
                instant=True,
            )
            self.create_gesture(
                self.obj.top_panel_box_center,
                3,
                self.pos_center_right_click,
                instant=True,
            )

            # Full
            self.create_gesture(
                self.obj.top_panel_box_full, 2, self.pos_full_middle_click, instant=True
            )
            self.create_gesture(
                self.obj.top_panel_box_full, 3, self.pos_full_right_click, instant=True
            )

            # Right
            self.create_gesture(
                self.obj.top_panel_box_right,
                1,
                self.pos_right_left_click,
                self.pos_right_left_double_click,
            )
            self.create_gesture(
                self.obj.top_panel_box_right,
                2,
                self.pos_right_middle_click,
                instant=True,
            )
            self.create_gesture(
                self.obj.top_panel_box_right,
                3,
                self.pos_right_right_click,
                instant=True,
            )

        def execute_callback(self, callback: Callable, event=None) -> None:
            """Execute the callback and any appended actions."""
            callback(event)
            if callback.__name__ in self.appended_actions:
                for action in self.appended_actions[callback.__name__]:
                    action()

        def append_action(self, callback_name: str, action: Callable) -> None:
            if callback_name not in self.appended_actions:
                self.appended_actions[callback_name] = []
            if action not in self.appended_actions[callback_name]:
                self.appended_actions[callback_name].append(action)

        # --- Callbacks ---
        def pos_left_left_click(self, *_):
            pass

        def pos_left_left_double_click(self, *_):
            pass

        def pos_left_middle_click(self, *_):
            self.pos_full_middle_click()

        def pos_left_right_click(self, *_):
            self.pos_full_right_click()

        def pos_center_left_click(self, *_):
            pass

        def pos_center_left_double_click(self, *_):
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

        def pos_right_left_double_click(self, *_):
            pass

        def pos_right_middle_click(self, *_):
            self.pos_full_middle_click()

        def pos_right_right_click(self, *_):
            self.pos_full_right_click()

    return GesturePlugin
