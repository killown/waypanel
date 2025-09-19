import os
import orjson as json
from gi.repository import Gtk, GLib
from src.plugins.core._base import BasePlugin
from src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

# Enable or disable the plugin
ENABLE_PLUGIN = True

# disabled for sway compositor
if not os.getenv("WAYFIRE_SOCKET"):
    ENABLE_PLUGIN = False


DEPS = ["event_manager", "gestures_setup", "on_output_connect"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "bottom-panel-center"
    order = 5
    priority = 99
    return position, order, priority


def initialize_plugin(panel_instance):
    """Initialize the Taskbar plugin."""
    if ENABLE_PLUGIN:
        return TaskbarPlugin(panel_instance)


class TaskbarPlugin(BasePlugin):
    """
    Manages and displays a dynamic taskbar for an active desktop session.
    """

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """
        Initializes the Taskbar plugin and its core components.

        This constructor sets up the initial state and subscribes to the necessary IPC events.
        It depends on the `event_manager` plugin, and if that is not ready, it will
        wait for it.
        """

        self._subscribe_to_events()
        # will hide until scale plugin is toggled if False
        self.layer_always_exclusive = False
        self.last_toplevel_focused_view = None
        self.taskbar_list = []
        self.buttons_id = {}

        # --- DEBOUNCE VARIABLES ---
        # Flag to track if a debounced update is scheduled
        self._debounce_pending = False
        # Timer ID for the scheduled update
        self._debounce_timer_id = None
        # Minimum time interval between updates (in milliseconds)
        self._debounce_interval = 10
        # --------------------------

        self.allow_move_view_scroll = True
        self.is_scale_active = {}
        self.create_gesture = self.plugins["gestures_setup"].create_gesture
        self.remove_gesture = self.plugins["gestures_setup"].remove_gesture
        # Scrolled window setup
        self.scrolled_window = Gtk.ScrolledWindow()

        # New: Initialize button pool and an in-use dictionary
        self.button_pool = []
        self.in_use_buttons = {}  # Maps view_id to button object

        self._setup_taskbar()
        self._initialize_button_pool(10)  # Create 10 reusable buttons

        # The `main_widget` must always be defined after the main widget is created.
        # For example, if the main widget is `self.scrolled_window`, setting `main_widget` before `scrolled_window`
        # could result in `None` being assigned instead. This may cause the plugin to malfunction
        # or prevent `set_content`/`append` from working properly.
        self.main_widget = (self.scrolled_window, "append")

    def set_layer_exclusive(self, exclusive) -> None:
        """
        Sets the taskbar's layer to be exclusive, making it visible above other windows.

        This method is primarily used to ensure the taskbar is clickable when the Wayfire
        "scale" plugin is active. It uses `set_layer_position_exclusive` to make the panel
        occupy a dedicated layer and a specific height, preventing other windows from
        covering it.

        Args:
            exclusive (bool): `True` to make the layer exclusive, `False` to revert.
        """
        if exclusive:
            self.update_widget_safely(
                set_layer_position_exclusive, self.bottom_panel, 48
            )
        else:
            self.update_widget_safely(unset_layer_position_exclusive, self.bottom_panel)

    def _setup_taskbar(self) -> None:
        """
        Creates and configures the Gtk widgets for the taskbar panel.

        This method initializes the main `Gtk.FlowBox` widget that holds the buttons,
        sets up a `Gtk.ScrolledWindow` to contain it, and adds the launcher button.
        It also reads the environment variables to dynamically size the taskbar based on
        the monitor's width, if available.
        """
        self.taskbar = Gtk.FlowBox()
        self.taskbar.set_selection_mode(Gtk.SelectionMode.NONE)
        self.logger.debug("Setting up bottom panel.")
        if self.layer_always_exclusive:
            self.layer_shell.set_layer(self.bottom_panel, self.layer_shell.Layer.TOP)
            self.layer_shell.auto_exclusive_zone_enable(self.bottom_panel)
            self.bottom_panel.set_size_request(10, 10)

        # Add launcher button
        self.add_launcher = Gtk.Button()
        icon = self.utils.get_nearest_icon_name("tab-new")
        self.add_launcher.set_icon_name(icon)

        output = os.getenv("waypanel")
        output_name = None
        output_id = None
        geometry = None

        if output:
            try:
                output_data = json.loads(output)
                output_name = output_data.get("output_name")
                output_id = output_data.get("output_id")
            except (json.JSONDecodeError, TypeError):
                self.log_error("Could not parse waypanel environment variable.")

        if output_name:
            output_id = self.ipc.get_output_id_by_name(output_name)
            if output_id:
                geometry = self.ipc.get_output_geometry(output_id)

        if geometry:
            monitor_width = geometry["width"]
            self.scrolled_window.set_size_request(monitor_width / 1.2, 64)

        # Taskbar setup
        self.taskbar.set_halign(Gtk.Align.CENTER)
        self.taskbar.set_valign(Gtk.Align.CENTER)
        self.scrolled_window.set_child(self.taskbar)
        self.taskbar.add_css_class("taskbar")

        # Start the taskbar list for the bottom panel
        self.Taskbar()
        self.logger.info("Bottom panel setup completed.")

    def _subscribe_to_events(self) -> bool:
        """
        Subscribes to all relevant Wayfire IPC events using the event manager.

        This is a critical function that ensures the taskbar receives real-time updates
        about window state changes. It waits for the `event_manager` plugin to be
        ready before attempting to subscribe. It subscribes to events such as
        `view-focused`, `view-mapped`, `view-unmapped`, `view-title-changed`, and
        `plugin-activation-state-changed`.
        """
        if "event_manager" not in self.obj.plugin_loader.plugins:
            self.logger.debug("Taskbar is waiting for EventManagerPlugin.")
            return True
        else:
            event_manager = self.obj.plugin_loader.plugins["event_manager"]
            self.logger.info("Subscribing to events for Taskbar Plugin.")

            # Subscribe to necessary events
            event_manager.subscribe_to_event(
                "view-focused",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-mapped",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-unmapped",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-title-changed",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "plugin-activation-state-changed",
                self.handle_plugin_event,
                plugin_name="taskbar",
            )
        return False

    def _initialize_button_pool(self, count):
        """
        Initializes a pool of reusable Gtk.Button widgets.

        This method pre-creates a specified number of hidden buttons to be reused by the taskbar.
        This approach is highly performant as it avoids the overhead of creating and
        destroying Gtk widgets every time a window is opened or closed. Instead, buttons
        are simply hidden and shown as needed.

        Each button is created with a Gtk.Box child containing a Gtk.Image (for the icon)
        and a Gtk.Label (for the title). This setup is done once, and references to
        the icon and label widgets are stored as custom attributes on the button (`button.icon`,
        `button.label`) for quick and easy access during updates.

        Args:
            count (int): The number of Gtk.Button widgets to pre-create and add to the pool.
        """
        for _ in range(count):
            button = Gtk.Button()
            # Create a box to hold icon and label
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

            button.icon = Gtk.Image()
            button.label = Gtk.Label()

            box.append(button.icon)
            box.append(button.label)
            button.set_child(box)
            button.add_css_class("taskbar-button")
            # Hide the button initially
            button.set_visible(False)
            self.taskbar.append(button)
            self.button_pool.append(button)

    def _get_or_create_button(self):
        """
        Retrieves a Gtk.Button from the reusable pool or creates a new one as a fallback.

        This method is the core of the button-pooling strategy. It first checks if there
        are any available buttons in the `self.button_pool`.

        1.  **If the pool is not empty:** It pops the first button from the pool, effectively
            reusing an existing widget. This is the most efficient path, as it avoids
            the performance overhead of widget creation and destruction.

        2.  **If the pool is exhausted:** This method dynamically creates a new `Gtk.Button`
            widget. It sets up the button with the standard child widgets (Gtk.Image, Gtk.Label)
            and custom attributes (`button.icon`, `button.label`) needed for the taskbar,
            then appends it to the taskbar and returns it. This ensures the taskbar can
            scale to any number of running applications, a key feature of this design.

        Returns:
            Gtk.Button: A Gtk.Button object, either a reused one from the pool or a newly
                        created one.
        """
        if self.button_pool:
            button = self.button_pool.pop(0)
            self.logger.debug("Reusing a button from the pool.")
            return button
        else:
            # Fallback: create a new button if the pool is exhausted
            self.logger.info("Button pool is exhausted, creating a new button.")
            button = Gtk.Button()
            button.add_css_class("taskbar-button")
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

            button.icon = Gtk.Image()
            button.label = Gtk.Label()

            box.append(button.icon)
            box.append(button.label)
            button.set_child(box)
            # Make sure the new button is appended to the taskbar
            self.taskbar.append(button)
            return button

    def update_taskbar_button(self, view):
        """
        Updates a Gtk.Button widget on the taskbar with the latest view information.

        This method is a crucial part of the taskbar's real-time updating mechanism. It takes
        a view object (a dictionary containing window details) and uses it to refresh the
        corresponding taskbar button.

        The process involves:
        1.  **Retrieving the Button**: It finds the specific button associated with the `view_id`
            from the `self.in_use_buttons` map. A warning is logged if the button doesn't
            exist, preventing a crash.
        2.  **Icon and Title Logic**: It uses helper functions (`self.utils.get_icon` and
            `self.utils.get_nearest_icon_name`) to determine the correct icon for the
            application. The window title is also processed: it's filtered for any invalid
            characters and then intelligently shortened to a more manageable length for
            display on the button.
        3.  **Updating the Widgets**: The method then efficiently updates the icon and label
            of the button by directly accessing the custom `button.icon` and `button.label`
            attributes. This direct access is faster and cleaner than searching the widget
            hierarchy for the sub-widgets.

        Args:
            view (dict): A dictionary representing the view (window) whose button needs to
                         be updated. It is expected to contain 'id', 'app-id', and 'title'.
        """
        view_id = view.get("id")
        if view_id not in self.in_use_buttons:
            self.logger.warning(
                f"Button for view ID {view_id} not found in in_use_buttons."
            )
            return

        button = self.in_use_buttons[view_id]

        app_id = view.get("app-id")
        title = view.get("title")
        initial_title = title.split()[0]

        if not title or not view_id:
            return

        icon_name = self.utils.get_icon(app_id, initial_title, title)
        if icon_name is None:
            return

        title = self.utils.filter_utf_for_gtk(view.get("title", ""))
        if not title:
            return

        words = title.split()
        shortened_words = [w[:50] + "…" if len(w) > 50 else w for w in words]
        title = " ".join(shortened_words)
        use_this_title = (
            title[:30] if len(title.split()[0]) <= 13 else title.split()[0][:30]
        )

        # This is where the error happens if button.icon has not been created
        button.icon.set_from_icon_name(icon_name)
        button.label.set_label(use_this_title)

    def remove_button(self, view_id):
        """
        Clears, hides, and returns a Gtk.Button to the reusable pool.

        This method is responsible for cleaning up a taskbar button when its
        corresponding window is closed or unmapped. It is a critical part of
        the button-pooling and resource management strategy. The process is as follows:
        1.  Safety Check: It first checks if the `view_id` exists in the `self.in_use_buttons` map.
        2.  Removal from Use: The button is popped from the `in_use_buttons` map, making it
            available for future use.
        3.  Cleanup: It sets the button to be invisible, removes any special CSS classes
            (like "focused"), and disconnects all gesture controllers to prevent
            memory leaks and unexpected behavior.
        4.  Reset Widgets: The custom `button.icon` and `button.label` widgets are cleared
            to ensure they don't display stale information.
        5.  Return to Pool: Finally, the button is appended back to the `self.button_pool`
            list, ready to be reused for a new window.
        This entire process ensures that the UI remains efficient and responsive without
        the need to create new buttons from scratch.
        Args:
            view_id (int): The unique ID of the view (window) whose button needs to be removed.
        """
        if view_id not in self.in_use_buttons:
            return

        button = self.in_use_buttons.pop(view_id)
        if not self.utils.widget_exists(button):
            return

        # Clean up the button
        button.set_visible(False)
        button.remove_css_class("focused")
        self.remove_gesture(button)

        # Clear icon and label
        button.icon.set_from_icon_name(None)
        button.label.set_label("")

        # Return to pool
        self.button_pool.append(button)
        self.logger.debug(f"Button for view ID {view_id} returned to pool.")

    def Taskbar(self):
        """
        Reconciles the taskbar buttons with the current list of open windows.

        This method is the core reconciliation loop for the taskbar. It synchronizes
        the buttons with the live state of all toplevel windows on the desktop.
        The process is optimized to reuse button objects from a pool rather than
        creating and destroying them, which improves performance and reduces memory
        churn. The reconciliation process is as follows:
        1.  **Get Current Views**: It queries the IPC to get a list of all current
            toplevel windows.
        2.  **Remove Stale Buttons**: It identifies buttons corresponding to windows
            that have been closed and returns them to the button pool for reuse.
        3.  **Clean Layout**: It clears the entire layout of the Gtk.FlowBox to ensure
            buttons can be re-added in the correct order. This prevents visual fragmentation
            where buttons are scattered across multiple rows.
        4.  **Add/Update Buttons**: It iterates through the current views and for each
            view, it either updates an existing button from the `in_use_buttons`
            dictionary or adds a new one from the pool.
        5.  **Rebuild Layout**: Finally, it appends all the active buttons back to the
            Gtk.FlowBox in a consistent order, ensuring a clean, unbroken layout.
        This approach guarantees that the taskbar is always synchronized with the
        desktop, providing a reliable and visually consistent user experience.
        """
        self.logger.debug("Reconciling taskbar views.")

        current_views = self.ipc.list_views()
        current_view_ids = {v.get("id") for v in current_views if self.is_valid_view(v)}

        # Identify and remove buttons for views that no longer exist
        views_to_remove = list(self.in_use_buttons.keys() - current_view_ids)
        for view_id in views_to_remove:
            self.remove_button(view_id)

        # Add or update buttons for existing views, and build a list for layout
        buttons_for_layout = []
        # Add a temporary set to track processed IDs in this run
        processed_view_ids = set()
        for view in current_views:
            view_id = view.get("id")
            if view_id in current_view_ids:
                # Check if this ID has already been processed in this cycle.
                if view_id in processed_view_ids:
                    self.logger.warning(
                        f"Duplicate view ID detected: {view_id}. Skipping this entry."
                    )
                    continue

                if view_id in self.in_use_buttons:
                    button = self.in_use_buttons[view_id]
                    self.update_button(button, view)
                else:
                    button = self.add_button_to_taskbar(view)
                buttons_for_layout.append(button)
                processed_view_ids.add(view_id)

        # Clear and rebuild the flowbox to fix the layout
        self.taskbar.remove_all()
        for button in buttons_for_layout:
            self.taskbar.append(button)

        self.logger.info("Taskbar reconciliation completed.")

    def update_button(self, button, view):
        """
        Updates a taskbar button with the information of a specific view.
        """
        MAX_TITLE_LENGTH = 25
        title = view.get("title")
        if len(title) > MAX_TITLE_LENGTH:
            truncated_title = title[:MAX_TITLE_LENGTH] + "..."
        else:
            truncated_title = title
        button.view_id = view.get("id")
        button.set_tooltip_text(title)
        button.icon.set_from_icon_name(view.get("app-id"))
        button.label.set_label(truncated_title)

    def add_button_to_taskbar(self, view):
        """
        Adds a taskbar button for a new view (window), using the button pool.

        This method prepares and configures a button for a new toplevel window.
        It manages the button's internal state and connects all necessary gestures
        and event controllers for user interaction. The button is not immediately
        appended to the taskbar here; that is handled by the main `Taskbar()`
        reconciliation method to ensure correct layout and ordering.

        Args:
            view (dict): A dictionary containing the details of the view (window).
        Returns:
            Gtk.Button: The prepared and configured Gtk.Button widget for the view.
        """
        view_id = view.get("id")

        # Get a button from the pool or create a new one
        button = self._get_or_create_button()

        # Store the button in the in-use map
        self.in_use_buttons[view_id] = button
        self.taskbar_list.append(view_id)

        # Update button content and make it visible
        self.update_button(button, view)
        button.set_visible(True)

        # Connect gestures and motion controllers
        button.connect("clicked", lambda *_: self.set_view_focus(view))
        self.create_gesture(button.get_child(), 1, lambda *_: self.set_view_focus(view))
        self.create_gesture(
            button.get_child(), 2, lambda *_: self.ipc.close_view(view_id)
        )
        self.create_gesture(
            button.get_child(),
            3,
            lambda *_: self.send_view_to_empty_workspace(view_id),
        )
        self.add_scroll_gesture(button, view)

        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("enter", lambda *_: self.on_button_hover(view))
        motion_controller.connect("leave", lambda *_: self.on_button_hover_leave(view))
        button.add_controller(motion_controller)
        self.utils.add_cursor_effect(button)

        return button

    def add_scroll_gesture(self, widget, view):
        """
        Adds a vertical scroll gesture controller to a given widget.

        This method enhances the interactivity of a widget, typically a taskbar button,
        by allowing it to respond to scroll wheel events. It creates a `Gtk.EventControllerScroll`
        configured to capture only vertical scrolling. When a scroll event occurs, it
        triggers the `self.on_scroll` method, passing the unique ID of the associated
        view (window) to it.

        This is a key component for enabling advanced user interactions like
        moving a window between displays by scrolling on its taskbar button.

        Args:
            widget (Gtk.Widget): The widget to which the scroll controller will be added.
            view (dict): The view (window) object associated with the widget. Its unique
                         'id' is used to identify the window during the scroll event.
        """
        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        scroll_controller.connect("scroll", self.on_scroll, view.get("id"))
        widget.add_controller(scroll_controller)

    def is_view_in_focused_output(self, view_id):
        """
        Checks if a view (window) is located on the currently focused display output.

        This function is used to determine the spatial relationship between a specific
        window and the user's active display. It is a critical step for functions
        that need to perform actions only on windows visible on the current screen,
        such as toggling fullscreen state or moving a window to a different display.

        The method retrieves the view object using its unique ID and the currently focused
        output from the IPC. It then compares the `output-id` of the view to the `id`
        of the focused output to determine if they are on the same display.

        Args:
            view_id (int): The unique ID of the view (window) to check.

        Returns:
            bool:
                - `True` if the view is on the currently focused output.
                - `False` otherwise (e.g., the view is on another output or does not exist).
        """
        view = self.ipc.get_view(view_id)
        if not view:
            return False
        view_output_id = view.get("output-id")
        focused_output = self.ipc.get_focused_output()
        if not focused_output:
            return False
        if view_output_id != focused_output.get("id"):
            return False
        else:
            return True

    def set_fullscreen_after_move(self, view_id):
        """
        Attempts to set a view (window) to fullscreen and then focuses it.

        This method is designed to be called after a view has been moved, such as
        between displays or workspaces. Its primary purpose is to ensure the user's
        attention is brought back to the view by both making it fullscreen and
        giving it keyboard focus. It uses a `try...except` block to gracefully
        handle any potential errors during the IPC calls, logging them to prevent
        application crashes.

        Args:
            view_id (int): The unique ID of the view (window) to set to fullscreen and focus.
        """
        try:
            self.ipc.set_view_fullscreen(view_id, True)
            self.set_view_focus(view_id)
        except Exception as e:
            self.log_error(f"Error setting fullscreen after move: {e}")

    def choose_fullscreen_state(self, view_id):
        """
        Toggles a view's fullscreen state based on its current location.

        This function is used as a callback in a `GLib.timeout_add` loop and is
        designed to toggle a window's fullscreen state. Its logic is based on whether
        the view is on the currently focused output. If the view is on the focused
        output, it will be set to non-fullscreen (`False`). If it is not on the
        focused output (e.g., it was just moved to a different monitor), it will be
        set to fullscreen (`True`).

        This logic is particularly useful for workflows where windows are moved
        between displays, ensuring the view becomes fullscreen on its new destination.

        Args:
            view_id (int): The unique ID of the view (window) whose fullscreen state to toggle.

        Returns:
            bool: Returns `False` to signal the `GLib.timeout_add` loop to stop repeating
                  the function call.
        """
        if self.is_view_in_focused_output(view_id):
            self.ipc.set_view_fullscreen(view_id, False)
        else:
            self.ipc.set_view_fullscreen(view_id, True)
        return False  # stop the glib loop

    def set_allow_move_view_scroll(self):
        """
        Resets the flag that controls whether a view can be moved via scrolling.

        This method is used as a callback in a `GLib.timeout_add` loop. It resets
        `self.allow_move_view_scroll` to `True` after a brief delay. This mechanism
        acts as a debounce timer, preventing the scroll gesture from triggering a
        "move window" action multiple times in rapid succession, which could lead
        to erratic behavior and unintended window movements.

        Returns:
            bool: Returns `False` to signal the `GLib.timeout_add` loop to stop repeating
                  the function call.
        """
        self.allow_move_view_scroll = True
        return False

    def on_scroll(self, controller, dx, dy, view_id):
        """
        Handles scroll wheel events on a taskbar button to move a window between displays.

        This is a core interactive function that uses vertical scroll gestures to
        move a window to an adjacent display (output). It is implemented with a
        debounce mechanism to prevent unintended, rapid window movements from a single
        scroll action.

        The logic is as follows:
        1.  **Debounce Check**: It first checks `self.allow_move_view_scroll`. If `False`,
            it means a move was just executed, and the function exits to prevent
            consecutive moves.
        2.  **Move Logic**: Based on the scroll direction (`dy`):
            -   `dy > 0` (scroll down): It attempts to move the window to the **right**-
                most available output.
            -   `dy < 0` (scroll up): It attempts to move the window to the **left**-
                most available output.
        3.  **Preventing Loops**: Before moving, it checks if the view is already on the
            target output. This prevents an infinite loop where the window is repeatedly
            sent to the same display.
        4.  **Debounce Timer**: A `GLib.timeout_add` is scheduled to call
            `self.set_allow_move_view_scroll` after a delay (300ms). This resets the
            flag, re-enabling the move function for the next scroll action.
        5.  **Fullscreen Toggling**: After moving the window, another `GLib.timeout_add`
            is scheduled to call `self.choose_fullscreen_state`, which ensures the
            window's fullscreen state is toggled appropriately for its new display.

        Args:
            controller (Gtk.EventControllerScroll): The scroll controller instance.
            dx (float): The horizontal scroll delta (not used in this implementation).
            dy (float): The vertical scroll delta. A positive value indicates scrolling
                        down, and a negative value indicates scrolling up.
            view_id (int): The unique ID of the view (window) associated with the scroll event.
        """
        try:
            view = self.ipc.get_view(view_id)
            if not view:
                return
            view_output_id = view.get("output-id")
            if not view_output_id:
                return

            if self.allow_move_view_scroll:
                # for 100 ms not allowed to send the view again
                self.allow_move_view_scroll = False
                if dy > 0:
                    GLib.timeout_add(300, self.set_allow_move_view_scroll)
                    output_from_right = self.utils.get_output_from("right")
                    # do not allow scroll up send the view back to left
                    # this should only be done by `dy < 0`
                    if view_output_id != output_from_right:
                        # Scrolling down
                        # Perform action for scroll down (e.g., switch to next workspace)
                        self.utils.send_view_to_output(view_id, "right")
                        GLib.timeout_add(100, self.choose_fullscreen_state, view_id)

                elif dy < 0:
                    GLib.timeout_add(300, self.set_allow_move_view_scroll)
                    output_from_left = self.utils.get_output_from("left")
                    # do not allow scroll up send the view back to right
                    # this should only be done by `dy > 0`
                    if view_output_id != output_from_left:
                        # Scrolling up
                        # Perform action for scroll up (e.g., switch to previous workspace)
                        self.utils.send_view_to_output(view_id, "left")
                        GLib.timeout_add(100, self.choose_fullscreen_state, view_id)

        except Exception as e:
            GLib.timeout_add(300, self.set_allow_move_view_scroll)
            self.log_error(
                message=f"Error handling scroll event {e}",
            )

    def send_view_to_empty_workspace(self, view_id):
        """
        Sends a view (window) to an available empty workspace.

        This method provides a robust way to move a window to a new, unoccupied workspace.
        It first attempts to locate an empty workspace using the `find_empty_workspace`
        utility.

        The logic is designed to handle different scenarios, particularly in multi-monitor
        setups:
        1.  **Safety Checks**: It verifies that the target view exists and that the
            necessary IPC data (like `wset-index` and `output-id`) is available to
            prevent crashes.
        2.  **Cross-Output Handling**: It checks if the view is on the same workspace set
            as the currently focused output. If they are different (e.g., the window
            is on another monitor), it first moves the view to the focused output's
            workspace, then focuses the view. This is a crucial step to prevent the
            view from "disappearing" from the user's workspace layout.
        3.  **Moving to Empty Workspace**: If an empty workspace is found and the view
            is on the same output, it focuses the view and then moves it to the
            coordinates of the empty workspace.

        Args:
            view_id (int): The unique ID of the view (window) to move.
        """
        view = self.ipc.get_view(view_id)
        if not view:
            self.log_error(
                f"Cannot send view {view_id} to empty workspace: view not found."
            )
            return

        empty_workspace = self.utils.find_empty_workspace()
        geo = view.get("geometry")
        wset_index_focused = self.ipc.get_focused_output().get("wset-index")
        wset_index_view = view.get("wset-index")
        output_id = self.ipc.get_focused_output().get("id")

        if wset_index_focused is None or wset_index_view is None or output_id is None:
            self.log_error(
                f"Cannot send view {view_id} to empty workspace: IPC data is incomplete."
            )
            return

        # this will prevent from trying to move the view from another output to an empty workspace
        # because it's necessary to bring the view to the current output and then move it to a empty ws
        if wset_index_focused != wset_index_view:
            if geo:
                self.ipc.configure_view(
                    view_id,
                    geo.get("x", 0),
                    geo.get("y", 0),
                    geo.get("width", 0),
                    geo.get("height", 0),
                    output_id,
                )
                self.set_view_focus(view)
            else:
                self.log_error(
                    f"Cannot send view {view_id} to empty workspace: geometry data is missing."
                )
        else:
            if empty_workspace:
                x, y = empty_workspace
                # if set_workspace from an empty workspace before the view is focused
                # the view may disappear from the workspaces layout and will not be able to get focus
                self.set_view_focus(view)
                # now move the view to an empty workspace
                self.ipc.set_workspace(x, y, view_id)

    def on_button_hover(self, view):
        """
        Applies a visual effect to a view (window) when its taskbar button is hovered over.

        This method is a callback for the `Gtk.EventControllerMotion`'s `enter` signal. It
        uses a utility function to apply a visual effect, such as a subtle highlight or
        shadow, to the corresponding window. This provides immediate visual feedback to the
        user, linking the taskbar button to the active window on the desktop.

        Args:
            view (dict): The view object associated with the hovered button.
        """
        self.utils.view_focus_effect_selected(view, 0.80, True)

    def on_button_hover_leave(self, view):
        """
        Removes the visual effect from a view when the mouse cursor leaves its button.

        This method is a callback for the `Gtk.EventControllerMotion`'s `leave` signal. It
        reverts the visual effect applied by `on_button_hover`, restoring the window's
        normal appearance. This ensures a clean and responsive user experience.

        Args:
            view (dict): The view object associated with the button that is no longer hovered.
        """
        self.utils.view_focus_effect_selected(view, False)

    def on_view_focused(self, view):
        """
        Handles the `view-focused` IPC event, updating the taskbar's state.

        This method is triggered when a window gains focus. It first checks if the
        focused view is a "toplevel" window, which is a standard window that should
        be tracked by the taskbar. It then stores a reference to this view and calls
        `update_focused_button_style` to apply a special visual style to its
        corresponding taskbar button.

        Args:
            view (dict): The view object that has just gained focus.
        """
        try:
            if view and view.get("role") == "toplevel":
                self.last_toplevel_focused_view = view
                view_id = view.get("id")
                if view_id:
                    self.update_focused_button_style(view_id)
        except Exception as e:
            self.logger.error(f"Error handling 'view-focused' event: {e}")

    def update_focused_button_style(self, focused_view_id):
        """
        Adds a special style class to the taskbar button of the focused window.

        This method iterates through all the buttons currently in use on the taskbar.
        It adds a "focused" CSS class to the button that corresponds to the
        `focused_view_id` and removes this class from all other buttons. This provides
        a clear visual indicator of the currently active window.

        Args:
            focused_view_id (int): The ID of the view that currently has focus.
        """
        for view_id, button in self.in_use_buttons.items():
            if view_id == focused_view_id:
                button.add_css_class("focused")
            else:
                button.remove_css_class("focused")

    def on_view_created(self, view):
        """
        Initiates a debounced update of the taskbar when a new view is created.

        To prevent rapid, redundant updates from a series of events (e.g., a window
        being mapped, focused, and having its title changed in quick succession), this
        method uses a debouncing mechanism. When a new view is created, it schedules a
        single update to occur after a short delay. If another view event happens
        within that delay, the timer is not reset, ensuring only one update is performed.

        Args:
            view (dict): The view object that has just been created.
        """
        if not self._debounce_pending:
            self._debounce_pending = True
            # Schedule the update to run after the debounce interval
            self._debounce_timer_id = GLib.timeout_add(
                self._debounce_interval, self._perform_debounced_update
            )

    def on_view_destroyed(self, view):
        """
        Handles the destruction of a view by removing its taskbar button.

        This method is a straightforward handler for when a window is closed or unmapped.
        It retrieves the view's ID and calls the `remove_button` method, which cleans
        up the corresponding taskbar button and returns it to the reusable pool.

        Args:
            view (dict): The view object that is being destroyed.
        """
        view_id = view.get("id")
        if view_id:
            self.remove_button(view_id)

    def on_title_changed(self, view):
        """
        Handles title changes for a view by updating its taskbar button.

        This method is triggered by the `view-title-changed` IPC event. It is
        responsible for ensuring that the title displayed on a taskbar button
        remains in sync with the window's actual title. It calls `update_taskbar_button`
        to refresh the button's label with the new title.

        Args:
            view (dict): The view object whose title has changed.
        """
        self.logger.debug(f"Title changed for view: {view}")
        self.update_taskbar_button(view)

    def handle_plugin_event(self, msg):
        """
        Handles IPC events related to other plugins, specifically the 'scale' plugin.

        This method listens for `plugin-activation-state-changed` events to track
        whether the "scale" plugin is active on a given output. It updates the
        `self.is_scale_active` dictionary, which is used by other parts of the
        taskbar to modify behavior when a scaling view is active.

        Args:
            msg (dict): The event message containing details about the plugin state change.
        """
        prevent_infinite_loop_from_event_manager_idle_add = False
        if msg.get("event") == "plugin-activation-state-changed":
            if msg.get("state") is True:
                if msg.get("plugin") == "scale":
                    self.is_scale_active[msg.get("output")] = True
            if msg.get("state") is False:
                if msg.get("plugin") == "scale":
                    self.is_scale_active[msg.get("output")] = False
        return prevent_infinite_loop_from_event_manager_idle_add

    def set_view_focus(self, view):
        """
        Sets keyboard focus on a view, handling window sizing and scale plugin interaction.

        This is a comprehensive function that focuses a window and ensures it's in an
        appropriate state. The key steps are:
        1.  **Validation**: It first validates the view object to ensure it's a valid
            window to be focused.
        2.  **Sizing**: It checks the window's geometry and resizes it to a minimum
            size (400x400) if it's too small, preventing usability issues.
        3.  **Scale Plugin Interaction**: It intelligently toggles the "scale" plugin
            off if it's currently active on the view's output. This is a crucial
            step to bring the window out of the scaling grid and into focus.
        4.  **Cursor and Workspace**: Finally, it calls a helper method to ensure the
            correct workspace is focused and the cursor is centered on the window,
            providing a seamless user experience.

        Args:
            view (dict): The view object to focus.

        Returns:
            bool: Returns `True` if an unexpected error occurs, otherwise `None`.
        """
        try:
            if not view:
                return

            view_id = view.get("id")
            if not view_id:
                self.logger.debug("Invalid view object: missing 'id'.")
                return

            view = self.utils.is_view_valid(view_id)
            if not view:
                self.logger.debug(f"Invalid or non-existent view ID: {view_id}")
                return

            output_id = view.get("output-id")
            if not output_id:
                self.logger.debug(
                    f"Invalid view object for ID {view_id}: missing 'output-id'."
                )
                return

            # Resize the view if it's too small
            try:
                viewgeo = self.ipc.get_view_geometry(view_id)
                if viewgeo and (
                    viewgeo.get("width", 0) < 100 or viewgeo.get("height", 0) < 100
                ):
                    self.ipc.configure_view(
                        view_id, viewgeo.get("x", 0), viewgeo.get("y", 0), 400, 400
                    )
                    self.logger.debug(f"Resized view ID {view_id} to 400x400.")
            except Exception as e:
                self.log_error(
                    message=f"Failed to retrieve or resize geometry for view ID: {view_id} {e}",
                )

            # Handle scale activation
            if output_id in self.is_scale_active and self.is_scale_active[output_id]:
                try:
                    self.ipc.scale_toggle()
                    self.logger.debug("Scale toggled off.")
                except Exception as e:
                    self.log_error(message=f"Failed to toggle scale. {e}")
                finally:
                    # Ensure workspace focus and cursor centering even if scale toggle fails
                    self._focus_and_center_cursor(view_id)
            else:
                # Focus workspace and center cursor without scale handling
                self.ipc.scale_toggle()
                self._focus_and_center_cursor(view_id)

            # Apply focus indicator effect
            self.utils.view_focus_indicator_effect(view)

        except Exception as e:
            # Catch-all for unexpected errors
            self.log_error(
                message=f"Unexpected error while setting focus for view ID: {view['id']} {e}",
            )
            return True

    def _focus_and_center_cursor(self, view_id):
        """
        Focuses the workspace and centers the mouse cursor on the specified view.

        This private helper method is called after a view has been focused. It
        performs two key actions:
        1.  It instructs the IPC to switch to the workspace where the view is located.
        2.  It moves the mouse cursor to the center of the view's window.
        This combination provides a smooth and intuitive transition for the user.

        Args:
            view_id (int): The ID of the view to focus and center the cursor on.
        """
        try:
            self.ipc.go_workspace_set_focus(view_id)
            self.ipc.center_cursor_on_view(view_id)
        except Exception as e:
            self.log_error(
                message=f"Failed to focus workspace or center cursor for view ID: {view_id} {e}",
            )

    def update_taskbar_on_scale(self) -> None:
        """
        Triggers a taskbar update during scale plugin activation.

        This method is used as a handler for the scale plugin's activation. It iterates
        through the current list of open views and calls the main `Taskbar()`
        reconciliation method. This ensures the taskbar accurately reflects the state of
        all windows, which can be critical when the display layout changes due to scaling.
        """
        self.logger.debug("Updating taskbar buttons during scale plugin activation.")
        list_views = self.ipc.list_views()
        if list_views:
            for view in list_views:
                self.Taskbar()

    def on_scale_activated(self):
        """
        Handles the activation of the Wayfire 'scale' plugin.

        When the scale plugin is activated, this method sets the taskbar's layer to
        "exclusive." This is a crucial step that makes the panels clickable, allowing
        the user to interact with the buttons even when the scale grid is active. The
        layer is only set if the focused output matches the panel's configured output
        and if the `layer_always_exclusive` setting is not enabled.
        """
        # set layer exclusive so the panels becomes clickable
        focused_output = self.ipc.get_focused_output()
        focused_output_name = focused_output.get("name") if focused_output else None
        on_output = self.plugins.get("on_output_connect")
        if not on_output:
            return

        layer_set_on_output_name = on_output.current_output_name
        if not layer_set_on_output_name:
            layer_set_on_output_name = on_output.primary_output_name
        # only set layer if the focused output is the same as the defined in panel creation
        if (
            layer_set_on_output_name == focused_output_name
            and not self.layer_always_exclusive
        ):
            self.set_layer_exclusive(True)

    def on_scale_desactivated(self):
        """
        Handles the deactivation of the Wayfire 'scale' plugin.

        This method is the counterpart to `on_scale_activated`. When the scale plugin
        is deactivated, it reverts the taskbar's layer from "exclusive" back to its
        normal state. This ensures that the panels do not interfere with other
        windows when the scaling view is no longer active.
        """
        if not self.layer_always_exclusive:
            self.set_layer_exclusive(False)

    def view_exist(self, view_id):
        """
        Checks if a view exists and meets the criteria for being displayed on the taskbar.

        This is a utility function used for various validation purposes. It performs
        a list comprehension to quickly check if a given `view_id` is present in the
        current list of views. It then performs a more detailed check using
        `is_valid_view` to confirm that the window meets all the necessary criteria
        (e.g., it's a toplevel window, it's mapped, and has a valid `app-id`).

        Args:
            view_id (int): The unique ID of the view to check.

        Returns:
            bool: `True` if the view exists and is valid for the taskbar, `False` otherwise.
        """
        try:
            view_id_list = {
                view.get("id")
                for view in self.ipc.list_views()
                if view and view.get("id")
            }
            if view_id not in view_id_list:
                return False
            view = self.ipc.get_view(view_id)
            if not self.is_valid_view(view):
                return False

            return True
        except Exception as e:
            self.log_error(
                message=f"Error checking view existence {e}",
            )
            return False

    def is_valid_view(self, view):
        """
        A simple helper function that checks if a view should be displayed on the taskbar.

        This method defines the filtering criteria for a valid taskbar view. A view must
        meet all of the following conditions to be considered valid:
        -   It must be a "toplevel" window (`view.get("role") == "toplevel"`).
        -   It must be in the "workspace" layer (`view.get("layer") == "workspace"`).
        -   It must be mapped (visible) (`view.get("mapped") is True`).
        -   It must have a valid application ID (`view.get("app-id") not in ("nil", None)`).
        -   It must have a valid process ID (`view.get("pid") != -1`).

        Args:
            view (dict): The view object to validate.

        Returns:
            bool: `True` if the view is a valid taskbar candidate, `False` otherwise.
        """
        if not view:
            return False
        return (
            view.get("layer") == "workspace"
            and view.get("role") == "toplevel"
            and view.get("mapped") is True
            and view.get("app-id") not in ("nil", None)
            and view.get("pid") != -1
        )

    def handle_view_event(self, msg):
        """
        The main event handler for all view-related IPC events.

        This method acts as a central dispatcher for events such as `view-mapped`,
        `view-unmapped`, `view-focused`, and `view-title-changed`. It performs a
        series of checks to filter out irrelevant events (e.g., those from a window
        with an invalid process ID or role) and then calls the appropriate, specific
        handler method (e.g., `on_view_created` or `on_view_destroyed`). This design
        centralizes event handling logic and keeps the individual handler methods
        clean and focused.
        """
        event = msg.get("event")
        view = msg.get("view")

        if event == "view-wset-changed":
            return
        if event == "view-unmapped":
            if view:
                self.on_view_destroyed(view)
            return

        if not view:
            return

        if view.get("pid", -1) == -1:
            return

        if view.get("role") != "toplevel":
            return

        if view.get("app-id") in ("", "nil"):
            return

        if event == "output-gain-focus":
            return
        if event == "view-title-changed":
            self.on_title_changed(view)
        if event == "view-tiled" and view:
            pass
        if event == "app-id-changed":
            return
        if event == "view-focused":
            self.on_view_focused(view)
            return
        if event == "view-mapped":
            self.on_view_created(view)
        if event == "view-unmapped":
            self.on_view_destroyed(view)

    def _perform_debounced_update(self):
        """
        Performs the main taskbar update after the debounce delay.
        This function acts as the final step in the debouncing process,
        calling the main Taskbar reconciliation method.
        """
        try:
            # Call the existing Taskbar method to synchronize buttons with views.
            self.Taskbar()
        finally:
            # Reset the debounce flag regardless of success or failure.
            self._debounce_pending = False

        # Return GLib.SOURCE_REMOVE as required by GLib.timeout_add for a one-time timeout.
        return GLib.SOURCE_REMOVE

    def about(self):
        """
        Taskbar Plugin
        ==============

        Purpose
        -------
        Provides a dynamic, scrollable taskbar for Wayfire/Waypanel desktops.
        It displays a button for every mapped (visible) toplevel window, allowing
        quick focus, movement, and management of running applications.
        """
        return self.about.__doc__
