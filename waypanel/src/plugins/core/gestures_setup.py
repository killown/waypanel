# ==== FILE: waypanel/src/plugins/gesture_plugin.py ====
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


class GesturePlugin:
    def __init__(self, obj, app):
        """
        Initialize the GesturePlugin.

        Args:
            obj: The main panel object from panel.py
            app: The main application instance
        """
        self.obj = obj
        self.app = app
        self.gestures = {}  # Store gesture references

    def create_gesture(self, widget, mouse_button, callback, arg=None):
        """
        Create a gesture for a widget.

        Args:
            widget: The widget to attach the gesture to.
            mouse_button: The mouse button to trigger the gesture (e.g., 1 for left click).
            callback: The function to call when the gesture is triggered.
            arg: Optional argument to pass to the callback.
        """
        gesture = Gtk.GestureClick.new()
        if arg is None:
            gesture.connect("released", callback)
        else:
            gesture.connect("released", lambda gesture, arg=arg: callback(arg))
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        self.gestures[widget] = gesture
        return widget

    def setup_gestures(self):
        """
        Set up gestures for the top panel (left, center, and right).
        """
        # Gestures for top panel left
        self.create_gesture(
            self.obj.top_panel_box_left, 1, self.top_panel_left_gesture_lclick
        )
        self.create_gesture(
            self.obj.top_panel_box_left, 2, self.top_panel_left_gesture_mclick
        )
        self.create_gesture(
            self.obj.top_panel_box_left, 3, self.top_panel_left_gesture_rclick
        )

        # Gestures for top panel center
        self.create_gesture(
            self.obj.top_panel_box_center, 1, self.top_panel_center_gesture_lclick
        )
        self.create_gesture(
            self.obj.top_panel_box_center, 2, self.top_panel_center_gesture_mclick
        )
        self.create_gesture(
            self.obj.top_panel_box_center, 3, self.top_panel_center_gesture_rclick
        )

        self.create_gesture(
            self.obj.top_panel_box_full, 3, self.top_panel_full_gesture_rclick
        )

        # Gestures for top panel right
        self.create_gesture(
            self.obj.top_panel_box_right, 1, self.top_panel_right_gesture_lclick
        )
        self.create_gesture(
            self.obj.top_panel_box_right, 2, self.top_panel_right_gesture_mclick
        )
        self.create_gesture(
            self.obj.top_panel_box_right, 3, self.top_panel_right_gesture_rclick
        )

    # Gesture Handlers
    def top_panel_left_gesture_lclick(self, *_):
        return

    def top_panel_left_gesture_rclick(self, *_):
        return

    def top_panel_left_gesture_mclick(self, *_):
        self.obj.sock.toggle_expo()

    def top_panel_center_gesture_lclick(self, *_):
        self.obj.sock.toggle_expo()

    def top_panel_center_gesture_mclick(self, *_):
        self.obj.sock.toggle_expo()

    def top_panel_center_gesture_rclick(self, *_):
        return

    def top_panel_full_gesture_rclick(self, *_):
        self.obj.wf_utils.go_next_workspace_with_views()

    def top_panel_right_gesture_lclick(self, *_):
        return

    def top_panel_right_gesture_rclick(self, *_):
        self.obj.sock.toggle_expo()

    def top_panel_right_gesture_mclick(self, *_):
        self.obj.sock.toggle_expo()


def position():
    """
    Define the plugin's position and order.
    """
    position = "right"  # Can be "left", "right", or "center"
    order = 10  # Lower numbers have higher priority
    return position, order


def initialize_plugin(obj, app):
    """
    Initialize the plugin.

    Args:
        obj: The main panel object from panel.py
        app: The main application instance
    """
    if ENABLE_PLUGIN:
        print("Initializing Gesture Plugin.")
        gesture_plugin = GesturePlugin(obj, app)
        gesture_plugin.setup_gestures()
        print("Gesture Plugin initialized and gestures added.")
