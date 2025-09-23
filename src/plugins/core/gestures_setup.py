import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
from src.shared.data_helpers import DataHelpers

ENABLE_PLUGIN = True

DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    return


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
        """Initialize the GesturePlugin.

        Sets up core components for managing gestures on UI elements within the panel,
        including storage for gesture references and associated actions.

        Args:
            panel_instance: The main panel object providing access to shared resources
                            such as logger, utilities, and UI components.
        """
        self.obj = panel_instance
        self.logger = panel_instance.logger
        self.data_helper = DataHelpers()
        self.gestures = {}  # Store gesture references
        self.appended_actions = {}  # Store additional actions for each gesture

    def setup_gestures(self) -> None:
        """Set up gestures for the top panel.
        Wait until the required panel boxes are ready."""
        GLib.idle_add(self.check_panel_boxes_ready)

    def check_panel_boxes_ready(self) -> bool:
        """Check if the required panel boxes are ready.
        If ready, proceed with gesture setup; otherwise, retry."""
        if (
            self.data_helper.validate_method(self.obj, "top_panel_box_left")
            and self.data_helper.validate_method(self.obj, "top_panel_box_center")
            and self.data_helper.validate_method(self.obj, "top_panel_box_full")
            and self.data_helper.validate_method(self.obj, "top_panel_box_right")
        ):
            self.logger.info("Panel boxes are ready. Setting up gestures...")
            self._setup_panel_gestures()
            return False  # Stop the idle loop
        else:
            self.logger.debug("Panel boxes not yet ready. Retrying...")
            return True  # Continue retrying

    def _setup_panel_gestures(self) -> None:
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

    def create_gesture(self, widget, mouse_button, callback) -> None:
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

    def remove_gesture(self, widget) -> None:
        if widget in self.gestures:
            gesture = self.gestures[widget]
            widget.remove_controller(gesture)
            del self.gestures[widget]

    def execute_callback(self, callback, event=None) -> None:
        """
        Execute the callback and any appended actions.
        Args:
            callback: The primary callback function to execute.
        """
        # Execute the primary callback
        callback(event)

        # Execute any appended actions for this callback
        if callback.__name__ in self.appended_actions:
            for action in self.appended_actions[callback.__name__]:
                action()

    def append_action(self, callback_name, action) -> None:
        if callback_name not in self.appended_actions:
            self.appended_actions[callback_name] = []

        # Prevent duplicate actions
        current_ids = [id(a) for a in self.appended_actions[callback_name]]
        if id(action) not in current_ids:
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

    def about(self):
        """
        A core background plugin that provides a centralized gesture
        handling system for the panel. It allows other plugins to
        append their actions to specific mouse click events.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this plugin is a robust and extensible
        system for handling user input on the panel. Its key
        principles are:

        1.  **Deferred Initialization**: The plugin uses `GLib.idle_add`
            to continuously check if the panel's UI components are
            fully loaded and ready. This ensures that gestures are
            only attached to existing widgets, preventing errors
            in a potentially asynchronous UI startup environment.

        2.  **Extensible Action Appending**: The plugin implements a
            unique "append" mechanism. Instead of hardcoding all
            actions, it allows other plugins to attach their own
            functions to an existing gesture handler's name via
            `append_action`. The `execute_callback` method then
            executes both the primary handler and all appended
            actions, enabling a modular and flexible design.

        3.  **Centralized Gesture Creation**: The `create_gesture` method
            acts as a factory, providing a standardized way to
            attach a `Gtk.GestureClick` to any widget. It centralizes
            the logic for connecting the gesture's `released` signal
            to the primary `execute_callback` method, making the code
            more maintainable and predictable.
        """
        return self.code_explanation.__doc__
