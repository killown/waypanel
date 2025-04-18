import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "right"  # Can be "left", "right", or "center"
    order = 10  # Lower numbers have higher priority
    return position, order


def initialize_plugin(panel_instance):
    """
    Initialize the plugin.
    Args:
        panel_instance: The main panel object from panel.py
    """
    if ENABLE_PLUGIN:
        plugin = GesturePlugin(panel_instance)
        plugin.setup_gestures()
        return plugin


class GesturePlugin:
    def __init__(self, panel_instance):
        """Initialize the GesturePlugin."""
        self.obj = panel_instance
        self.gestures = {}  # Store gesture references
        self.appended_actions = {}  # Store additional actions for each gesture

    def setup_gestures(self):
        """Set up gestures for the top panel (left, center, and right)."""
        # Gestures for the left section of the top panel
        self.create_gesture(self.obj.top_panel_box_left, 1, self.pos_left_left_click)
        self.create_gesture(self.obj.top_panel_box_left, 2, self.pos_left_middle_click)
        self.create_gesture(self.obj.top_panel_box_left, 3, self.pos_left_right_click)

        # Gestures for the center section of the top panel
        self.create_gesture(
            self.obj.top_panel_box_center, 1, self.pos_center_left_click
        )
        self.create_gesture(
            self.obj.top_panel_box_center, 2, self.pos_center_middle_click
        )
        self.create_gesture(
            self.obj.top_panel_box_center, 3, self.pos_center_right_click
        )

        # Gestures for the full section of the top panel
        self.create_gesture(self.obj.top_panel_box_full, 3, self.pos_full_right_click)

        # Gestures for the right section of the top panel
        self.create_gesture(self.obj.top_panel_box_right, 1, self.pos_right_left_click)
        self.create_gesture(
            self.obj.top_panel_box_right, 2, self.pos_right_middle_click
        )
        self.create_gesture(self.obj.top_panel_box_right, 3, self.pos_right_right_click)

    def create_gesture(self, widget, mouse_button, callback):
        """
        Create a gesture for a widget and attach it to the specified callback.
        Args:
            widget: The widget to attach the gesture to.
            mouse_button: The mouse button to trigger the gesture (e.g., 1 for left click).
            callback: The function to call when the gesture is triggered.
        """
        gesture = Gtk.GestureClick.new()
        gesture.connect("released", lambda *_: self.execute_callback(callback))
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        self.gestures[widget] = gesture

    def execute_callback(self, callback):
        """
        Execute the callback and any appended actions.
        Args:
            callback: The primary callback function to execute.
        """
        # Execute the primary callback
        callback()

        # Execute any appended actions for this callback
        if callback.__name__ in self.appended_actions:
            for action in self.appended_actions[callback.__name__]:
                action()

    def append_action(self, callback_name, action):
        """
        Append an additional action to a specific gesture callback.
        Args:
            callback_name: The name of the callback function to append the action to.
            action: The additional action to append (a callable function).
        """
        if callback_name not in self.appended_actions:
            self.appended_actions[callback_name] = []
        self.appended_actions[callback_name].append(action)

    # Gesture Handlers
    def pos_left_left_click(self, *_):
        """Callback for left-click on the left section."""
        pass

    def pos_left_middle_click(self, *_):
        """Callback for middle-click on the left section."""
        self.obj.sock.toggle_expo()

    def pos_left_right_click(self, *_):
        """Callback for right-click on the left section."""
        pass

    def pos_center_left_click(self, *_):
        """Callback for left-click on the center section."""

    def pos_center_middle_click(self, *_):
        """Callback for middle-click on the center section."""

    def pos_center_right_click(self, *_):
        """Callback for right-click on the center section."""
        pass

    def pos_full_right_click(self, *_):
        """Callback for right-click on the full section."""

    def pos_right_left_click(self, *_):
        """Callback for left-click on the right section."""
        pass

    def pos_right_middle_click(self, *_):
        """Callback for middle-click on the right section."""

    def pos_right_right_click(self, *_):
        """Callback for right-click on the right section."""
