import os
import subprocess
import gi
import toml
from collections.abc import Iterable
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from src.core.compositor.ipc import IPC
from typing import Dict, Any, Optional, Tuple, Callable, List, Union, Type, Iterable
import configparser
import importlib.util


gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


class Utils(Adw.Application):
    def __init__(self, panel_instance):
        """Initialize utility class with shared resources and configuration paths.

        Sets up commonly used components like logging, icon themes, configuration paths,
        and process-related utilities for use across the application.

        Args:
            panel_instance: The main panel object providing access to shared resources
                            such as logger, config, and UI containers.
        """
        self.obj = panel_instance
        self.logger = self.obj.logger
        self._setup_config_paths()
        self.psutil_store = {}
        self.icon_names = [icon for icon in Gtk.IconTheme().get_icon_names()]
        self.gio_icon_list = Gio.AppInfo.get_all()
        self.gestures = {}
        self.fd = None
        self.watch_id = None
        self.ipc = IPC()

        self.focused_view_id = None
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_path)

        self.terminal_emulators = [
            "kitty",
            "gnome-terminal",
            "terminator",
            "xterm",
            "konsole",
            "urxvt",
            "alacritty",
            "wezterm",
            "lxterminal",
            "xfce4-terminal",
            "tilix",
            "st",
            "rxvt",
        ]
        self.original_alpha_views_values = {
            view["id"]: self.ipc.get_view_alpha(view["id"])["alpha"]
            for view in self.ipc.list_views()
        }

    def send_view_to_output(self, view_id, direction):
        """
        Move a view to a different output based on the specified direction.

        This function retrieves the geometry and workspace index of the specified view and determines
        whether the view is currently on the focused output. If the view is not on the focused output,
        it moves the view to the focused output. Otherwise, it calculates the target output based on
        the provided direction (e.g., "left" or "right") and moves the view to that output.

        Args:
            view_id (int): The ID of the view to be moved.
            direction (str): The direction to move the view ("left" or "right").

        Steps:
            1. Retrieve the view's geometry and workspace index.
            2. Check if the view is on the same workspace index as the focused output.
            3. If not, move the view to the focused output.
            4. If yes, calculate the target output using `get_output_from(direction)` and move the view there.

        Dependencies:
            - `get_view(view_id)`: Fetches the view object containing its geometry and workspace index.
            - `get_focused_output()`: Retrieves the currently focused output.
            - `get_output_from(direction)`: Determines the target output ID based on the direction.
            - `configure_view(...)`: Configures the view's position and assigns it to a specific output.

        Example:
            # Move the view with ID 123 to the output on the left
            send_view_to_output(123, "left")

        Notes:
            - The `direction` argument must be a valid string ("left" or "right").
            - If the view is already on the focused output, the function uses `get_output_from(direction)`
              to determine the target output ID.
        """
        view = self.ipc.get_view(view_id)
        geo = view["geometry"]
        wset_index_focused = self.ipc.get_focused_output()["wset-index"]
        wset_index_view = view["wset-index"]
        focused_output_id = self.ipc.get_focused_output()["id"]
        if wset_index_focused != wset_index_view:
            self.ipc.configure_view(
                view_id,
                geo["x"],
                geo["y"],
                geo["width"],
                geo["height"],
                focused_output_id,
            )
        else:
            output_direction = self.get_output_from(direction)
            self.ipc.configure_view(
                view_id,
                geo["x"],
                geo["y"],
                geo["width"],
                geo["height"],
                output_direction,
            )

    def get_output_from(self, direction: str) -> int:
        """
        Determine the output adjacent to the currently focused output in the specified direction.

        This function calculates the closest output to the left or right of the currently focused output
        based on their geometries. It iterates through all connected outputs, computes their relative
        positions, and identifies the nearest output in the specified direction.

        Args:
            direction (str): The direction to search for an adjacent output. Must be one of:
                             - "left": Search for the closest output to the left of the focused output.
                             - "right": Search for the closest output to the right of the focused output.

        Returns:
            int or None:
                - The ID of the closest output in the specified direction if one exists.
                - `None` if no output is found in the specified direction.

        Raises:
            ValueError: If the `direction` argument is invalid (not "left" or "right").
            Exception: If an unexpected error occurs during execution, it is logged for debugging.

        Dependencies:
            - `self.ipc.list_outputs()`: Retrieves a list of all connected outputs and their geometries.
            - `self.ipc.get_focused_output()`: Retrieves the currently focused output and its geometry.
            - `self.logger.error(...)`: Logs errors with detailed context for troubleshooting.

        Example Usage:
            # Get the output to the left of the focused output
            left_output_id = self.get_output_from("left")
            if left_output_id:
                print(f"Output to the left: {left_output_id}")
            else:
                print("No output to the left.")

            # Get the output to the right of the focused output
            right_output_id = self.get_output_from("right")
            if right_output_id:
                print(f"Output to the right: {right_output_id}")
            else:
                print("No output to the right.")

        Notes:
            - The function uses horizontal distances (`x` coordinates) to determine adjacency.
            - Outputs are considered "to the left" if their right edge is to the left of the focused output's left edge.
            - Outputs are considered "to the right" if their left edge is to the right of the focused output's right edge.
            - If multiple outputs exist in the specified direction, the closest one is returned.
        """
        try:
            # Validate the direction argument
            if direction not in ["left", "right"]:
                raise ValueError(
                    f"Invalid direction: {direction}. Must be 'left' or 'right'."
                )

            # Get the list of all outputs
            outputs = self.ipc.list_outputs()

            # Get the currently focused output
            focused_output = self.ipc.get_focused_output()

            if not focused_output:
                raise ValueError("No focused output found.")

            # Extract the geometry of the focused output
            focused_geometry = focused_output["geometry"]
            focused_x = focused_geometry["x"]
            focused_width = focused_geometry["width"]

            # Initialize variables to track the closest output in the specified direction
            target_output_id = None
            target_distance = float("inf")

            # Iterate through all outputs to find the closest one in the specified direction
            for output in outputs:
                if output["id"] == focused_output["id"]:
                    continue  # Skip the focused output

                output_geometry = output["geometry"]
                output_x = output_geometry["x"]

                # Calculate the horizontal distance between the focused output and the current output
                if direction == "left":
                    # Output is to the left if its right edge is to the left of the focused output's left edge
                    if output_x + output_geometry["width"] <= focused_x:
                        distance = focused_x - (output_x + output_geometry["width"])
                        if distance < target_distance:
                            target_output_id = output["id"]
                            target_distance = distance
                elif direction == "right":
                    # Output is to the right if its left edge is to the right of the focused output's right edge
                    if output_x >= focused_x + focused_width:
                        distance = output_x - (focused_x + focused_width)
                        if distance < target_distance:
                            target_output_id = output["id"]
                            target_distance = distance

            # Return the ID of the closest output in the specified direction
            if target_output_id is None:
                return -1

            return target_output_id

        except Exception as e:
            focused_output = self.ipc.get_focused_output()
            outputs = self.ipc.list_outputs()
            self.logger.error(
                error=e,
                message="Error while determining the output from direction.",
                context={
                    "direction": direction,
                    "focused_output": focused_output,
                    "outputs": outputs,
                },
            )
            return -1

    def monitor_width_height(self, monitor_name: str) -> Optional[Tuple[int, int]]:
        focused_view = self.ipc.get_focused_view()
        if focused_view:
            output = self.get_monitor_info()
            output = output[monitor_name]
            monitor_width = output[0]
            monitor_height = output[1]
            return monitor_width, monitor_height

    def on_css_file_changed(
        self, monitor, file, other_file, event_type: Gio.FileMonitorEvent
    ):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            # Reload CSS when changes are done
            def run_once():
                self.load_css_from_file()
                return False

            GLib.idle_add(run_once)

    def load_css_from_file(self):
        # you need to append the widgets to their parent containers first and then add_css_class
        css_provider = Gtk.CssProvider()
        css_provider.load_from_file(Gio.File.new_for_path(self.style_css_config))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def notify_send(self, title: str, message: str):
        """
        Send a notification asynchronously using DBus to avoid blocking the main thread.

        Args:
            title (str): The title (summary) of the notification.
            message (str): The body of the notification.
        """

        def on_notification_sent(obj, result, *args):
            """
            Callback function to handle the result of the asynchronous DBus call.
            """
            try:
                # Finish the asynchronous call
                obj.call_finish(result)
                print("Notification sent successfully.")
            except Exception as e:
                print(f"Error sending notification: {e}")

        # Get the session bus asynchronously
        Gio.bus_get(Gio.BusType.SESSION, None, self._on_bus_acquired, (title, message))

    def _on_bus_acquired(
        self,
        source: Gio.DBusConnection,
        result: Gio.AsyncResult,
        user_data: tuple[str, str],
    ) -> None:
        """
        Callback function when the session bus is acquired.

        Args:
            source: The Gio.DBusConnection object.
            result: The result of the asynchronous bus acquisition.
            user_data: Tuple containing the title and message for the notification.
        """
        try:
            # Complete the bus acquisition
            bus = Gio.bus_get_finish(result)

            # Extract title and message from user_data
            title, message = user_data

            # Make the asynchronous DBus call to send the notification
            bus.call(
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
                "Notify",
                GLib.Variant(
                    "(susssasa{sv}i)",
                    (
                        "waypanel",  # App name
                        0,  # Notification ID (0 = new)
                        "",  # Icon (leave empty)
                        title,  # Summary (title)
                        message,  # Body
                        [],  # Actions (none)
                        {},  # Hints (e.g., urgency)
                        5000,  # Timeout (ms)
                    ),
                ),
                None,  # Reply type (None for no reply)
                Gio.DBusCallFlags.NONE,
                -1,  # Timeout in milliseconds (-1 for default)
                None,  # Cancellable (None for no cancellation)
                self._on_notification_sent,  # Callback function
                None,  # User data for the callback
            )
        except Exception as e:
            print(f"Error acquiring session bus: {e}")

    def _on_notification_sent(
        self,
        source: Gio.DBusConnection,
        result: Gio.AsyncResult,
        user_data: object,
    ) -> None:
        """
        Callback function to handle the result of the asynchronous notification call.

        Args:
            source: The Gio.DBusConnection object.
            result: The result of the asynchronous call.
            user_data: Optional user data passed to the callback.
        """
        try:
            # Finish the asynchronous call
            source.call_finish(result)
            print("Notification sent successfully.")
        except Exception as e:
            print(f"Error sending notification: {e}")

    def run_cmd(self, cmd: str) -> None:
        """
        Run a shell command using subprocess.Popen in a separate thread to avoid blocking the main GTK thread.
        Ensures the process is detached from the panel by creating a new session.

        Args:
            cmd (str): The shell command to execute.
        """
        try:
            # Start the subprocess with a new session to detach it from the panel
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # Ensure output is returned as strings
                start_new_session=True,  # Detach the process from the parent
            )

            # Optionally, log the process details or handle errors
            self.logger.info(f"Command started with PID: {process.pid}")

        except Exception as e:
            self.logger.error(
                error=e, message=f"Error running command: {cmd}", level="error"
            )

    def find_view_middle_cursor_position(
        self,
        view_geometry: Dict[str, int],
        monitor_geometry: Dict[str, int],
    ) -> Tuple[int, int]:
        """
        Calculate the cursor position at the center of the given view relative to the monitor.

        Args:
            view_geometry: A dictionary containing the keys "x", "y", "width", and "height"
                           representing the geometry of the view/window.
            monitor_geometry: A dictionary containing the keys "x" and "y" representing
                              the monitor's top-left corner coordinates.

        Returns:
            A tuple (cursor_x, cursor_y) representing the calculated cursor position.
        """
        # Find the center point of the view
        view_center_x = view_geometry["x"] + view_geometry["width"] // 2
        view_center_y = view_geometry["y"] + view_geometry["height"] // 2

        # Position cursor relative to monitor origin
        cursor_x = monitor_geometry["x"] + view_center_x
        cursor_y = monitor_geometry["y"] + view_center_y

        return cursor_x, cursor_y

    def move_cursor_middle(self, view_id: str) -> None:
        """
        Move the cursor to the center of the specified view on its output (monitor).

        Args:
            view_id (str): The unique identifier of the view/window.
        """
        # Get the view data from IPC
        view = self.ipc.get_view(view_id)
        if not view:
            self.logger.warning(f"View with ID '{view_id}' not found.")
            return

        # Extract relevant geometries
        output_id = view["output-id"]
        view_geometry = view["geometry"]

        output = self.ipc.get_output(output_id)
        if not output:
            self.logger.warning(f"Output with ID '{output_id}' not found.")
            return

        output_geometry = output["geometry"]

        # Calculate center position and move cursor
        cursor_x, cursor_y = self.find_view_middle_cursor_position(
            view_geometry, output_geometry
        )
        self.ipc.move_cursor(cursor_x, cursor_y)

    def widget_exists(self, widget: Any) -> bool:
        """
        Check if the given object is a valid Gtk.Widget instance.

        Args:
            widget (Any): The object to check.

        Returns:
            bool: True if the object is a non-None Gtk.Widget; False otherwise.
        """
        return widget is not None and isinstance(widget, Gtk.Widget)

    def is_widget_ready(self, container: Any) -> bool:
        """
        Check if the container is ready for appending widgets.

        This checks whether the container:
        - Is a valid Gtk.Widget instance
        - Is realized (has an associated window)
        - Is visible

        Args:
            container (Any): The widget container to check.

        Returns:
            bool: True if the container is valid, realized, and visible; False otherwise.
        """
        # Check if container is a valid GTK widget
        if not self.widget_exists(container):
            return False

        # Check if container is realized and visible
        if not Gtk.Widget.get_realized(container) or not Gtk.Widget.get_visible(
            container
        ):
            return False

        return True

    def get_nearest_icon_name(self, app_name: str, size=Gtk.IconSize.LARGE) -> str:
        """
        Get the best matching icon name for an application (GTK4 synchronous version).
        Returns immediately with the icon name or fallback.

        Args:
            app_name: Application name (e.g. 'firefox')
            size: Preferred icon size (Gtk.IconSize)

        Returns:
            Best matching icon name with fallbacks
        """
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        app_name = app_name.lower().strip()

        # Ordered list of possible icon name patterns
        patterns = [
            # Application-specific
            app_name,
            f"{app_name}-symbolic",
            f"org.{app_name}.Desktop",
            f"{app_name}-desktop",
            # Generic formats
            f"application-x-{app_name}",
            f"system-{app_name}",
            f"utility-{app_name}",
            # Vendor prefixes
            f"fedora-{app_name}",
            f"debian-{app_name}",
        ]

        # Check exact matches first
        for pattern in patterns:
            if icon_theme.has_icon(pattern):
                return pattern

        # Search for partial matches
        try:
            all_icons = icon_theme.get_icon_names()
            matches = [icon for icon in all_icons if app_name in icon.lower()]
            if matches:
                return matches[0]  # Return first match
        except Exception as e:
            self.logger.error(f"Icon search error: {e}")

        # Final fallbacks
        for fallback in [
            "application-x-executable",
            "image-missing",
            "gtk-missing-image",
        ]:
            if icon_theme.has_icon(fallback):
                return fallback

        return "image-missing"

    def update_widget(self, function_method: Callable[..., None], *args: Any) -> None:
        """
        Schedule a widget update to run in the main GTK thread using GLib.idle_add.

        Args:
            function_method (Callable): The callable method to execute.
            *args (Any): Variable-length argument list for the callable.
        """
        GLib.idle_add(function_method, *args)

    def update_widget_safely(self, method: Callable[..., None], *args: Any) -> bool:
        """
        Safely call a method with provided arguments if all validations pass.
        Ensures the operation is performed on the main thread using GLib.idle_add.

        Args:
            method: The callable method to invoke (e.g., container.append or set_layer_position_exclusive).
            *args: Arguments to pass to the method.

        Returns:
            bool: True if the method was successfully called, False otherwise.
        """
        # Perform additional validation for specific use cases
        if args:
            first_arg = args[0]
            if isinstance(first_arg, Gtk.Widget):
                if first_arg is None or not isinstance(first_arg, Gtk.Widget):
                    self.logger.error("Error: Invalid widget provided")
                    return False
                if first_arg.get_parent():
                    self.logger.warning(
                        "Widget already has a parent. Skipping operation."
                    )
                    return False

        # Safely update the widget using GLib.idle_add
        try:
            self.update_widget(method, *args)
        except Exception as e:
            self.logger.error(f"Error calling method {method.__name__}: {e}")
            return False

        return True

    def get_monitor_info(self) -> Dict[str, List[int]]:
        """
        Retrieve information about the connected monitors.

        This function gathers details about each connected monitor,
        including their dimensions and names, and returns the data as a dictionary.

        Returns:
            dict: A dictionary where keys are monitor names (str), and values are lists
                  containing [width (int), height (int)].
                  If no monitors are detected or an error occurs, returns an empty dictionary.
        """
        try:
            # Get the default display
            display = Gdk.Display.get_default()
            if not display:
                self.logger.error("Failed to retrieve default display.")
                return {}

            # Retrieve the list of monitors
            monitors = display.get_monitors()
            if not monitors:
                self.logger.warning("No monitors detected.")
                return {}

            # Build the monitor info dictionary
            monitor_info: Dict[str, List[int]] = {}
            for monitor in monitors:
                try:
                    geometry = monitor.get_geometry()
                    name: Optional[str] = monitor.props.connector

                    if not isinstance(name, str) or not name.strip():
                        self.logger.warning(
                            f"Invalid or missing monitor name for monitor: {monitor}"
                        )
                        continue

                    monitor_info[name] = [geometry.width, geometry.height]
                    self.logger.debug(
                        f"Detected monitor: {name} ({geometry.width}x{geometry.height})"
                    )

                except Exception as e:
                    self.logger.error(
                        f"Error retrieving information for a monitor: {e}",
                        exc_info=True,
                    )

            return monitor_info

        except Exception as e:
            self.logger.error(
                f"Unexpected error while retrieving monitor information: {e}",
                exc_info=True,
            )
            return {}

    def search_local_desktop(self, initial_title: str) -> Optional[str]:
        """
        Search for a desktop file matching the given title in the webapps directory.

        This function scans `.desktop` files in the `self.webapps_applications` directory,
        checking if their filename starts with specific prefixes (chrome, msedge, FFPWA-).
        It then searches for the given title inside each file and returns the first match.

        Args:
            initial_title (str): The title to search for inside the desktop files.

        Returns:
            Optional[str]: The matched desktop file name if found, otherwise None.
        """
        for deskfile in os.listdir(self.webapps_applications):
            if not deskfile.startswith(("chrome", "msedge", "FFPWA-")):
                continue

            webapp_path = os.path.join(self.webapps_applications, deskfile)
            if self.search_str_inside_file(webapp_path, initial_title.lower()):
                return deskfile

        return None

    def layer_shell_check(self) -> None:
        """
        Check if gtk4-layer-shell is installed; clone and build it from source if not.

        This function performs the following steps:
        1. Checks for an existing installation by looking for a key shared library file.
        2. If not found, clones the repository from GitHub into a temporary directory.
        3. Sets up the build environment using Meson.
        4. Builds and installs gtk4-layer-shell locally under ~/.local/lib/gtk4-layer-shell.

        Logs are generated at each step for transparency and debugging.
        """
        try:
            # Define paths
            install_path = os.path.expanduser("~/.local/lib/gtk4-layer-shell")
            installed_marker = os.path.join(
                install_path, "libgtk_layer_shell.so"
            )  # Adjust if necessary
            temp_dir = "/tmp/gtk4-layer-shell"
            repo_url = "https://github.com/wmww/gtk4-layer-shell.git"
            build_dir = "build"

            # Check if the library is already installed
            if os.path.exists(installed_marker):
                self.logger.info("gtk4-layer-shell is already installed.")
                return

            self.logger.info("gtk4-layer-shell is not installed. Installing...")

            # Create a temporary directory
            try:
                if not os.path.exists(temp_dir):
                    self.logger.info(f"Creating temporary directory: {temp_dir}")
                    os.makedirs(temp_dir)
            except Exception as e:
                self.logger.error(
                    error=e, message=f"Failed to create temporary directory: {temp_dir}"
                )
                return

            # Clone the repository
            try:
                self.logger.info(f"Cloning repository from: {repo_url}")
                subprocess.run(["git", "clone", repo_url, temp_dir], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e, message="Failed to clone the gtk4-layer-shell repository."
                )
                return

            # Change to the repository directory
            try:
                os.chdir(temp_dir)
            except Exception as e:
                self.logger.error(
                    error=e, message=f"Failed to change directory to: {temp_dir}"
                )
                return

            # Set up the build directory with Meson
            try:
                self.logger.info("Configuring the build environment...")
                subprocess.run(
                    [
                        "meson",
                        "setup",
                        f"--prefix={install_path}",
                        "-Dexamples=true",
                        "-Ddocs=true",
                        "-Dtests=true",
                        build_dir,
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e,
                    message="Failed to configure the build environment with Meson.",
                )
                return

            # Build the project
            try:
                self.logger.info("Building the project...")
                subprocess.run(["ninja", "-C", build_dir], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e, message="Failed to build the gtk4-layer-shell project."
                )
                return

            # Install the project
            try:
                self.logger.info("Installing the project...")
                subprocess.run(["ninja", "-C", build_dir, "install"], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e, message="Failed to install the gtk4-layer-shell project."
                )
                return

            self.logger.info("gtk4-layer-shell installation complete.")

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                error=e,
                message="Unexpected error during gtk4-layer-shell installation.",
            )

    def extract_icon_info(self, application_name: str) -> Optional[str]:
        """
        Extract the icon name for a given application by searching desktop files.

        This function searches through standard desktop file directories to find an entry
        matching the provided application name, then returns the associated icon name.

        Args:
            application_name (str): The name of the application to search for.

        Returns:
            Optional[str]: The icon name if found, or None if no matching application is found.
        """
        # Paths to search for desktop files
        search_paths = [
            "/usr/share/applications/",
            os.path.expanduser("~/.local/share/applications/"),
        ]

        try:
            # Loop through each search path
            for search_path in search_paths:
                # Check if the search path exists
                if not os.path.exists(search_path):
                    self.logger.debug(f"Search path does not exist: {search_path}")
                    continue

                # Loop through each file in the directory
                try:
                    for file_name in os.listdir(search_path):
                        if not file_name.endswith(".desktop"):
                            continue

                        file_path = os.path.join(search_path, file_name)
                        try:
                            with open(file_path, "r") as desktop_file:
                                found_name = False
                                for line in desktop_file:
                                    if line.startswith("Name="):
                                        app_name = line.strip().split("=")[1]
                                        if app_name == application_name:
                                            found_name = True
                                    elif found_name and line.startswith("Icon="):
                                        icon_name = line.strip().split("=")[1]
                                        self.logger.debug(
                                            f"Found icon '{icon_name}' for application '{application_name}' in file: {file_path}"
                                        )
                                        return icon_name
                        except Exception as e:
                            self.logger.error(
                                error=e,
                                message=f"Error reading desktop file: {file_path}",
                                context={"file": file_path},
                            )
                except Exception as e:
                    self.logger.error(
                        error=e,
                        message=f"Error listing files in directory: {search_path}",
                        context={"directory": search_path},
                    )

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                error=e, message="Unexpected error while extracting icon info."
            )

        # Return None if no icon is found
        self.logger.info(f"No icon found for application: {application_name}")
        return None

    def remove_widget(self, widget: Any) -> bool:
        """
        Safely remove a widget from its parent using .unparent().

        Args:
            widget (Any): The widget to remove. Must be a Gtk.Widget instance.

        Returns:
            bool: True if the widget was successfully unparented, False otherwise.
        """
        if not isinstance(widget, Gtk.Widget):
            self.logger.error("Invalid widget provided for removal.")
            return False

        parent = widget.get_parent()
        if not parent:
            self.logger.warning("Widget has no parent. Skipping removal.")
            return False

        try:
            widget.unparent()  # Detach the widget from its parent
            self.logger.debug(f"Successfully unparented widget: {widget}")
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to unparent widget: {widget} - Error: {e}", exc_info=True
            )
            return False

    def validate_iterable(
        self,
        input_value: Any,
        name: str = "input",
        expected_length: Optional[int] = None,
        element_type: Optional[Union[Type, List[Type]]] = None,
        allow_empty: bool = True,
    ) -> bool:
        """
        Validate that the input is an iterable with optional constraints.

        Args:
            input_value (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            expected_length (Optional[int]): Expected length of the iterable. If provided, must match exactly.
            element_type (Optional[Union[Type, List[Type]]]): Expected type(s) of elements in the iterable.
                - If a single type: all elements must be of this type.
                - If a list of types: each element must match the corresponding type by position.
            allow_empty (bool): Whether to allow empty iterables.

        Returns:
            bool: True if validation passes, False otherwise.
        """
        # Check if the input is iterable
        if not isinstance(input_value, Iterable):
            self.logger.warning(
                f"Invalid {name}: Expected an iterable, got {type(input_value).__name__}."
            )
            return False

        # Exclude strings from being considered valid iterables (unless explicitly allowed)
        if isinstance(input_value, str):
            self.logger.warning(
                f"Invalid {name}: Strings are not considered valid iterables in this context."
            )
            return False

        # Convert to a tuple or list for length-based checks
        try:
            iterator = list(input_value)
        except Exception:
            self.logger.warning(f"Invalid {name}: Could not iterate over input.")
            return False

        # Check emptiness
        if not allow_empty and len(iterator) == 0:
            self.logger.warning(f"{name} cannot be empty.")
            return False

        # Check length
        if expected_length is not None and len(iterator) != expected_length:
            self.logger.warning(
                f"Invalid {name}: Expected an iterable of length {expected_length}, got {len(iterator)}."
            )
            return False

        # Check element types
        if element_type is not None:
            if isinstance(element_type, list):
                if len(element_type) != len(iterator):
                    self.logger.warning(
                        f"Invalid {name}: Number of element types ({len(element_type)}) "
                        f"does not match iterable length ({len(iterator)})."
                    )
                    return False
                for idx, (element, typ) in enumerate(zip(iterator, element_type)):
                    if not isinstance(element, typ):
                        self.logger.warning(
                            f"Invalid {name}: Element at index {idx} is not of type {typ.__name__}."
                        )
                        return False
            else:
                for idx, element in enumerate(iterator):
                    if not isinstance(element, element_type):
                        self.logger.warning(
                            f"Invalid {name}: Element at index {idx} is not of type {element_type.__name__}."
                        )
                        return False

        return True

    def validate_method(self, obj: Any, method_name: str) -> bool:
        """
        Validate that a method or attribute exists and is callable or a valid GTK widget.

        Args:
            obj (Any): The object to check.
            method_name (str): The name of the method or attribute to validate.

        Returns:
            bool: True if the method/attribute is callable or a valid GTK widget, False otherwise.
        """
        if not hasattr(obj, method_name):
            self.logger.warning(
                f"Object {obj.__class__.__name__} does not have '{method_name}'."
            )
            return False

        attr = getattr(obj, method_name)

        # Accept either callable or Gtk.Widget instances
        if callable(attr) or isinstance(attr, Gtk.Widget):
            return True

        self.logger.warning(
            f"'{method_name}' on {obj.__class__.__name__} is neither callable nor a valid GTK widget."
        )
        return False

    def validate_widget(self, widget: Any, name: str = "widget") -> bool:
        """
        Validate that the given object is a valid widget.

        Args:
            widget (Any): The object to validate.
            name (str): Name of the widget for logging purposes.

        Returns:
            bool: True if the widget is valid, False otherwise.
        """
        if not isinstance(widget, Gtk.Widget):
            self.logger.warning(f"{name} is not a valid Gtk.Widget.")
            return False
        return True

    def validate_string(
        self, input_value: Any, name: str = "input", allow_empty: bool = False
    ) -> bool:
        """
        Validate that the input is a non-empty string.

        Args:
            input_value (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            allow_empty (bool): Whether to accept empty or whitespace-only strings.

        Returns:
            bool: True if valid, False otherwise.
        """
        if not isinstance(input_value, str):
            self.logger.warning(
                f"Invalid {name}: Expected a string, got {type(input_value).__name__}."
            )
            return False

        if not allow_empty and not input_value.strip():
            self.logger.warning(f"{name} cannot be empty.")
            return False

        return True

    def validate_integer(
        self,
        input_value: Any,
        name: str = "input",
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> bool:
        """
        Validate that the input is an integer within an optional range.

        Args:
            input_value (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            min_value (Optional[int]): Minimum allowed value (inclusive).
            max_value (Optional[int]): Maximum allowed value (inclusive).

        Returns:
            bool: True if valid, False otherwise.
        """
        if not isinstance(input_value, int):
            self.logger.warning(
                f"Invalid {name}: Expected an integer, got {type(input_value).__name__}."
            )
            return False

        if min_value is not None and input_value < min_value:
            self.logger.warning(f"{name} must be >= {min_value}.")
            return False

        if max_value is not None and input_value > max_value:
            self.logger.warning(f"{name} must be <= {max_value}.")
            return False

        return True

    def validate_tuple(
        self,
        input_value: Any,
        expected_length: Optional[int] = None,
        element_types: Optional[Union[Type, List[Type]]] = None,
        name: str = "input",
    ) -> bool:
        """
        Validate that the input is a tuple with optional type and length constraints.

        Args:
            input_value (Any): The value to validate.
            expected_length (Optional[int]): Expected length of the tuple. If provided, must match exactly.
            element_types (Optional[Union[Type, List[Type]]]): Expected type(s) of elements in the tuple.
                - If a single type: all elements must be of this type.
                - If a list of types: each element must match the corresponding type by position.
            name (str): Name of the input for logging purposes.

        Returns:
            bool: True if validation passes, False otherwise.
        """
        # Check if input is a tuple
        if not isinstance(input_value, tuple):
            self.logger.warning(
                f"Invalid {name}: Expected a tuple, got {type(input_value).__name__}."
            )
            return False

        # Check tuple length
        if expected_length is not None and len(input_value) != expected_length:
            self.logger.warning(
                f"Invalid {name}: Expected a tuple of length {expected_length}, got {len(input_value)}."
            )
            return False

        # Validate element types
        if element_types is not None:
            if isinstance(element_types, list):
                if len(element_types) != len(input_value):
                    self.logger.warning(
                        f"Invalid {name}: Number of element types ({len(element_types)}) "
                        f"does not match tuple length ({len(input_value)})."
                    )
                    return False
                for idx, (element, typ) in enumerate(zip(input_value, element_types)):
                    if not isinstance(element, typ):
                        self.logger.warning(
                            f"Invalid element type at index {idx} in {name}: "
                            f"Expected {typ.__name__}, got {type(element).__name__}."
                        )
                        return False
            elif isinstance(element_types, type):
                for idx, element in enumerate(input_value):
                    if not isinstance(element, element_types):
                        self.logger.warning(
                            f"Invalid element type at index {idx} in {name}: "
                            f"Expected {element_types.__name__}, got {type(element).__name__}."
                        )
                        return False
            else:
                self.logger.warning(
                    f"Invalid element_types for {name}: Expected a type or list of types, got {type(element_types).__name__}."
                )
                return False

        return True

    def validate_bytes(
        self, input_value: Any, expected_length: int | None = None, name: str = "input"
    ) -> bool:
        """
        Validate that the input is a bytes object with optional length constraints.

        Args:
            input_value (Any): The value to validate.
            expected_length (Optional[int]): Expected length of the bytes object. If provided, must match exactly.
            name (str): Name of the input for logging purposes.

        Returns:
            bool: True if validation passes, False otherwise.
        """
        # Check if input is a bytes object
        if not isinstance(input_value, bytes):
            self.logger.warning(
                f"Invalid {name}: Expected bytes, got {type(input_value).__name__}."
            )
            return False

        # Check length if specified
        if expected_length is not None and len(input_value) != expected_length:
            self.logger.warning(
                f"Invalid {name}: Expected bytes of length {expected_length}, got {len(input_value)}."
            )
            return False

        return True

    def validate_list(
        self,
        input_list: Any,
        name: str = "input",
        element_type: Optional[Type] = None,
        allow_empty: bool = True,
    ) -> bool:
        """
        Validate that the input is a list with optional element type constraints.

        Args:
            input_list (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            element_type (Optional[Type]): Expected type of each element in the list. If None, no type check is performed.
            allow_empty (bool): Whether to allow empty lists.

        Returns:
            bool: True if validation passes, False otherwise.
        """
        # Check if input is a list
        if not isinstance(input_list, list):
            self.logger.warning(
                f"Invalid {name}: Expected a list, got {type(input_list).__name__}."
            )
            return False

        # Check if the list is empty
        if not allow_empty and not input_list:
            self.logger.warning(f"{name} cannot be empty.")
            return False

        # Validate element types
        if element_type is not None:
            for index, element in enumerate(input_list):
                if not isinstance(element, element_type):
                    self.logger.warning(
                        f"Invalid element type at index {index} in {name}: "
                        f"Expected {element_type.__name__}, got {type(element).__name__}."
                    )
                    return False

        return True

    def search_desktop(self, app_id: str) -> Optional[str]:
        """
        Search for a desktop file associated with the given application ID.

        This function searches through installed applications to find a matching desktop file
        whose ID contains the provided `app_id`.

        Args:
            app_id (str): The application ID or WM_CLASS to search for.

        Returns:
            Optional[str]: The ID of the first matching desktop file if found, or None if no match is found.
        """
        try:
            # Validate input
            if not self.validate_string(app_id):
                self.logger.warning(f"Invalid or missing app_id: {app_id}")
                return None

            # Retrieve all installed applications
            try:
                all_apps = Gio.AppInfo.get_all()
            except Exception as e:
                self.logger.error(
                    "Failed to retrieve installed applications.", exc_info=True
                )
                return None

            # Filter desktop files based on app_id
            desktop_files = [
                app.get_id().lower()
                for app in all_apps
                if app.get_id() and app_id.lower() in app.get_id().lower()
            ]

            # Return the first match if any
            if desktop_files:
                self.logger.debug(
                    f"Found desktop file for app_id '{app_id}': {desktop_files[0]}"
                )
                return desktop_files[0]
            else:
                self.logger.info(f"No desktop file found for app_id: {app_id}")
                return None

        except Exception as e:
            self.logger.error(
                f"Unexpected error while searching for desktop file with app_id: {app_id}",
                exc_info=True,
            )
            return None

    def icon_exist(self, argument: str) -> str:
        """
        Check if an icon exists based on the given application identifier.

        This function attempts to find a matching icon by searching through registered
        Gio.AppInfo entries and icon names.

        Args:
            argument (str): The application name or identifier to search for.

        Returns:
            str: The name or path of the matching icon if found, or an empty string if not found.
        """
        try:
            # Validate input
            if not isinstance(argument, str) or not argument.strip():
                self.logger.warning(f"Invalid or missing argument: {argument}")
                return ""

            # Try finding in Gio.AppInfo list
            matches = [
                app_info.get_icon()
                for app_info in getattr(self, "gio_icon_list", [])
                if argument.lower() in app_info.get_id().lower()
            ]

            if matches:
                icon = matches[0]
                # Extract icon name using available methods
                if hasattr(icon, "get_names") and callable(icon.get_names):
                    names = icon.get_names()
                    if names:
                        return names[0]
                elif hasattr(icon, "get_name") and callable(icon.get_name):
                    return icon.get_name()

            # Fallback: Search directly in known icon names
            icon_matches = [
                name
                for name in getattr(self, "icon_names", [])
                if argument.lower() in name.lower()
            ]
            if icon_matches:
                return icon_matches[0]

            # No icon found
            self.logger.debug(f"No icon found for argument: {argument}")
            return ""

        except Exception as e:
            self.logger.error(
                f"Unexpected error while checking if icon exists for argument: {argument}",
                exc_info=True,
            )
            return ""

    def search_str_inside_file(self, file_path: str, word: str) -> bool:
        """
        Search for a formatted string inside a file.

        This function looks for the pattern 'name=<word>' (case-insensitive)
        within the specified file.

        Args:
            file_path (str): Path to the file to search in.
            word (str): The word to search for, formatted as 'name=<word>'.

        Returns:
            bool: True if the pattern is found, False otherwise.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read().lower()
                return f"name={word.lower()}" in content
        except Exception as e:
            self.logger.warning(f"Error reading file '{file_path}': {e}")
            return False

    def get_icon(self, wm_class: str, initial_title: str, title: str) -> Optional[str]:
        """
        Retrieve an appropriate icon name based on window metadata.

        Args:
            wm_class (str): The window manager class of the application.
            initial_title (str): The original title of the window.
            title (str): The current title of the window.

        Returns:
            Optional[str]: The icon name if found, otherwise None.
        """
        title = self.filter_utf_for_gtk(title)
        initial_title = title.split()[0]

        for terminal in self.terminal_emulators:
            if terminal in wm_class and terminal not in title.lower():
                title_icon = self.icon_exist(initial_title)
                if title_icon:
                    return title_icon

        # Special handling for Microsoft Edge web apps
        web_apps = {
            "msedge",
            "microsoft-edge",
            "microsoft-edge-dev",
            "microsoft-edge-beta",
        }
        if any(app in wm_class.lower() for app in web_apps):
            desk_local = self.search_local_desktop(initial_title)
            self.logger.info(desk_local)

            if desk_local and desk_local.endswith("-Default.desktop"):
                if desk_local.startswith("msedge-"):
                    icon_name = desk_local.split(".desktop")[0]
                    return icon_name
            else:
                return self.get_nearest_icon_name("microsoft-edge")

        found_icon = self.icon_exist(wm_class)
        if found_icon:
            return found_icon

        return None

    def list_app_ids(self) -> list[str]:
        """
        Get a list of lowercase app IDs from all views currently managed by the compositor.

        Returns:
            List[str]: A list of lowercase app IDs (excluding "nil").
        """
        views = self.ipc.list_views()
        return [i["app-id"].lower() for i in views if i["app-id"] != "nil"]

    def focus_view_when_ready(self, view: dict) -> bool:
        """
        Attempt to focus the given view if it's ready. Meant to be used with GLib.idle_add.

        Args:
            view (dict): The view data dictionary containing 'role' and 'focusable'.

        Returns:
            bool: True if the view isn't ready and should be retried, False if done.
        """
        if view["role"] == "toplevel" and view["focusable"] is True:
            self.ipc.set_focus(view["id"])
            return False  # Stop idle processing
        return True  # Continue idle processing

    def find_empty_workspace(self) -> Optional[tuple]:
        """
        Find an empty workspace using wf_utils.get_workspaces_without_views().

        Returns:
            Optional[tuple]: (x, y) coordinates of the first empty workspace,
                             or None if no empty workspace is found.
        """
        try:
            # Get the list of workspaces without views
            empty_workspaces = self.ipc.get_workspaces_without_views()

            if empty_workspaces:
                # Return the first empty workspace as a tuple (x, y)
                return empty_workspaces[0]

            return None

        except Exception as e:
            # Log any unexpected errors
            self.logger.error(f"Error while finding an empty workspace: {e}")
            return None

    def move_view_to_empty_workspace(self, view_id: str) -> None:
        """
        Move the given view to an empty workspace.

        Args:
            view_id (str): The ID of the view to move.
        """
        ws = self.ipc.get_current_workspace()
        if ws:
            x, y = ws.values()
            self.ipc.set_workspace(x, y, view_id)

    # this function is useful because it will handle icon_name and icon_path
    def handle_icon_for_button(self, view: dict, button) -> None:
        """
        Set an appropriate icon for the button based on the view's details.

        Args:
            view (dict): The view object containing details like title and app-id.
            button (Gtk.Button): The button to which the icon will be applied.
        """
        app_id = None
        try:
            # Extract relevant details from the view
            title = view.get("title", "")
            initial_title = title.split()[0] if title else ""
            app_id = view.get("app-id", "")

            # Retrieve the icon path or name
            icon_path = self.get_icon(app_id, title, initial_title)
            icon_path = self.get_nearest_icon_name(icon_path)
            if not icon_path:
                self.logger.debug(f"No icon found for view: {app_id}")
                button.set_icon_name("default-icon-name")
                return

            self.logger.debug(f"Icon retrieved for view: {app_id} -> {icon_path}")

            # Handle file-based icons
            if icon_path.startswith("/"):
                try:
                    image = Gtk.Image.new_from_file(icon_path)
                    if isinstance(image, Gtk.Image):
                        # Use set_child instead of set_image
                        button.set_child(image)
                    else:
                        self.logger.error("Error: Invalid image provided")
                        button.set_icon_name("default-icon-name")
                except Exception as e:
                    self.logger.error(f"Error loading icon from file: {e}")
                    button.set_icon_name("default-icon-name")
            else:
                # Handle icon names directly
                button.set_icon_name(icon_path)

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while handling icon for button: {app_id}, {e}",
                exc_info=True,
            )
            button.set_icon_name("default-icon-name")

    def find_icon_for_app_id(self, app_id: str) -> Optional[str]:
        """
        Find an icon for a given application ID.

        Args:
            app_id (str): The application ID to search for.

        Returns:
            Optional[str]: The icon name or path if found, otherwise None.
        """
        try:
            # Validate input
            if not app_id or not isinstance(app_id, str):
                self.logger.warning(f"Invalid or missing app_id: {app_id}")
                return None

            def normalize_icon_name(app_id: str) -> str:
                if "." in app_id:
                    return app_id.split(".")[-1]  # Extract the last part
                return app_id

            # Normalize the app_id for comparison
            app_id = app_id.lower()
            normalized_app_id = normalize_icon_name(app_id)

            # Retrieve all installed applications
            try:
                app_list = Gio.AppInfo.get_all()
            except Exception as e:
                self.logger.error(
                    f"Failed to retrieve installed applications: {e}", exc_info=True
                )
                return None

            # Search for a matching application
            for app in app_list:
                try:
                    app_info_id = app.get_id().lower()
                    if not app_info_id:
                        continue

                    # Check if the app_id matches the application's ID
                    if (
                        app_info_id.startswith(normalized_app_id)
                        or normalized_app_id in app_info_id
                    ):
                        icon = app.get_icon()
                        if not icon:
                            continue

                        # Handle themed icons
                        if isinstance(icon, Gio.ThemedIcon):
                            icon_names = icon.get_names()
                            if icon_names:
                                return icon_names[0]

                        # Handle file-based icons
                        elif isinstance(icon, Gio.FileIcon):
                            file_path = icon.get_file().get_path()
                            if file_path:
                                return file_path

                except Exception as e:
                    self.logger.error(
                        f"Error processing application: {e}", exc_info=True
                    )

            # Log if no icon is found
            self.logger.debug(f"No icon found for app_id: {app_id}")
            return None

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while finding icon for app_id {app_id}: {e}",
                exc_info=True,
            )
            return None

    def get_wayfire_pid(self) -> Optional[int]:
        """
        Retrieve the PID of the Wayfire compositor process.

        Returns:
            Optional[str]: The PID of the Wayfire process if found, otherwise None.
        """
        try:
            # Iterate over all entries in /proc
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue  # Skip non-numeric entries

                try:
                    comm_file_path = f"/proc/{entry}/comm"
                    with open(comm_file_path, "r") as comm_file:
                        command_name = comm_file.read().strip()
                        if "wayfire" in command_name.lower():
                            self.logger.debug(
                                f"Found Wayfire process with PID: {entry}"
                            )
                            return int(entry)
                except IOError as e:
                    # Log and skip unreadable entries
                    self.logger.warning(
                        f"Failed to read /proc/{entry}/comm. Details: {e}"
                    )
                    continue

            # Log if no Wayfire process is found
            self.logger.info("No Wayfire process found.")
            return None

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while retrieving Wayfire PID: {e}",
                exc_info=True,
            )
            return None

    def list_libs_in_process(self, pid: Union[int, str]) -> list:
        """
        Retrieve the list of shared libraries (.so files) loaded by a process.

        Args:
            pid (Union[int, str]): The Process ID of the target process.

        Returns:
            list: A list of unique shared library paths loaded by the process.
        """
        libs = []
        maps_file = f"/proc/{pid}/maps"

        try:
            # Validate that the PID is valid and the maps file exists
            if not os.path.exists(maps_file):
                self.logger.warning(f"Maps file not found for PID: {pid}")
                return libs

            with open(maps_file, "r") as f:
                for line in f:
                    # Check if the line contains a shared library reference
                    if "so" in line:
                        lib_path = line.split()[-1]
                        # Validate the library path
                        if os.path.isfile(lib_path) and lib_path not in libs:
                            libs.append(lib_path)
                            self.logger.debug(f"Found shared library: {lib_path}")

        except FileNotFoundError:
            self.logger.error(
                error=FileNotFoundError(f"Maps file not found: {maps_file}"),
                message=f"Failed to read /proc/{pid}/maps",
            )
        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while listing shared libraries for PID -> {pid}: {e}",
                exc_info=True,
            )

        return libs

    def check_lib_in_wayfire(self, lib_name: str) -> bool:
        """
        Check if a specific shared library is loaded by the Wayfire process.

        Args:
            lib_name (str): The name of the shared library to check.

        Returns:
            bool: True if the library is found in the Wayfire process, False otherwise.
        """
        try:
            # Validate input
            if not lib_name or not isinstance(lib_name, str):
                self.logger.warning(f"Invalid or missing library name: {lib_name}")
                return False

            # Get the PID of the Wayfire process
            pid = self.get_wayfire_pid()
            if not pid:
                self.logger.info("Wayfire process not found.")
                return False

            self.logger.debug(
                f"Checking for library '{lib_name}' in Wayfire process (PID: {pid})"
            )

            # Retrieve the list of shared libraries loaded by the Wayfire process
            libs = self.list_libs_in_process(pid)
            if not libs:
                self.logger.debug(
                    f"No shared libraries found for Wayfire process (PID: {pid})"
                )
                return False

            # Check if the specified library is loaded
            for lib in libs:
                if lib_name in lib:
                    self.logger.debug(
                        f"Found library '{lib_name}' in Wayfire process: {lib}"
                    )
                    return True

            self.logger.debug(f"Library '{lib_name}' not found in Wayfire process.")
            return False

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while checking for library '{lib_name}' in Wayfire process: {e}",
                exc_info=True,
            )
            return False

    def find_wayfire_lib(self, lib_name: str) -> bool:
        """
        Check if a specific shared library is loaded by the Wayfire process.

        Args:
            lib_name (str): The name of the shared library to check.

        Returns:
            bool: True if the library is found in the Wayfire process, False otherwise.
        """
        try:
            # Directly return the result of `check_lib_in_wayfire`
            return self.check_lib_in_wayfire(lib_name)
        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while finding library '{lib_name}' in Wayfire: {e}",
                exc_info=True,
            )
            return False

    def get_default_monitor_name(self, config_file_path: str) -> Optional[str]:
        """
        Retrieve the default monitor name from a TOML configuration file.

        Args:
            config_file_path (str): The path to the configuration file.

        Returns:
            Optional[str]: The default monitor name if found, otherwise None.
        """
        try:
            # Validate that the configuration file exists
            if not os.path.exists(config_file_path):
                self.logger.error(f"Config file '{config_file_path}' not found.")
                return None

            # Load and parse the TOML configuration file
            try:
                with open(config_file_path, "r") as file:
                    config = toml.load(file)
            except toml.TomlDecodeError as e:
                self.logger.error(
                    f"Failed to parse TOML file: {config_file_path}", exc_info=True
                )
                return None

            # Extract the monitor name if the "monitor" section exists
            if "monitor" in config:
                monitor_name = config["monitor"].get("name")
                if monitor_name:
                    self.logger.debug(f"Default monitor name found: {monitor_name}")
                    return monitor_name
                else:
                    self.logger.info(
                        "Monitor name is missing in the 'monitor' section."
                    )
                    return None
            else:
                self.logger.info(
                    "'monitor' section not found in the configuration file."
                )
                return None

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while retrieving default monitor name from '{config_file_path} and {e}'.",
                exc_info=True,
            )
            return None

    def view_focus_effect_selected(
        self, view: dict, alpha: float = 1.0, selected: bool = False
    ) -> None:
        """
        Apply a focus indicator effect by animating the view's alpha (transparency).

        Args:
          view (dict): The view dictionary containing at least the 'id' key.
          alpha (float): The transparency level to apply when selected (0.0 to 1.0).
          selected (bool): Whether the view is currently selected/focused.
        """
        view_id = None
        try:
            view_id = view["id"]
            if not self.is_view_valid(view):
                self.logger.warning(f"Invalid or non-existent view ID: {view_id}")
                return

            if selected:
                self.ipc.set_view_alpha(view_id, alpha)
            else:
                # FIXME: sometimes it's not set to original value
                # original_alpha_value = self.original_alpha_views_values[view_id]
                original_alpha_value = 1.0
                self.ipc.set_view_alpha(view_id, original_alpha_value)

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while applying focus indicator effect for view ID: {view_id} and {e}",
                exc_info=True,
            )

    def is_view_valid(self, view: Union[int, dict]) -> Union[dict, bool]:
        """
        Validate if a view is valid based on its ID or dictionary.

        Args:
            view (Union[int, dict]): The ID of the view or a dictionary containing view details.

        Returns:
            Union[dict, bool]: The view object if valid, otherwise False.
        """
        view_id = None
        try:
            if view is None:
                return False

            # Extract view_id from dictionary or use directly if it's an int
            if isinstance(view, dict):
                view_id = view.get("id")
                if view_id is None:
                    self.logger.warning(
                        "Invalid dictionary provided: Missing 'id' key."
                    )
                    return False
            elif isinstance(view, int):
                view_id = view
            else:
                self.logger.warning(
                    f"Invalid view type: {type(view).__name__}. Expected int or dict."
                )
                return False

            # Ensure view_id is an integer
            if not isinstance(view_id, int):
                self.logger.warning(
                    f"Invalid view ID type: {type(view_id).__name__}. Expected int."
                )
                return False

            # Get the list of active view IDs
            try:
                view_ids = [i["id"] for i in self.ipc.list_views()]
            except Exception as e:
                self.logger.error(
                    f"Failed to retrieve active view IDs: {e}", exc_info=True
                )
                return False

            if view_id not in view_ids:
                self.logger.debug(
                    f"View ID {view_id} is not in the list of active views."
                )
                return False

            try:
                fetched_view = self.ipc.get_view(view_id)
            except Exception as e:
                self.logger.error(
                    f"Failed to fetch view details for ID: {view_id} and {e}",
                    exc_info=True,
                )
                return False

            # NOTE: Wayfire-only check
            if "role" in fetched_view and "app-id" in fetched_view:
                if not fetched_view:
                    self.logger.debug(f"No view details found for ID: {view_id}")
                    return False

                # Perform additional checks
                if fetched_view.get("role") != "toplevel":
                    self.logger.debug(
                        f"View ID {view_id} has an invalid role: {fetched_view.get('role')}"
                    )
                    return False

                if fetched_view.get("pid") == -1:
                    self.logger.debug(
                        f"View ID {view_id} has an invalid PID: {fetched_view.get('pid')}"
                    )
                    return False

                if fetched_view.get("app-id") in ["", "nil"]:
                    self.logger.debug(
                        f"View ID {view_id} has an invalid app-id: {fetched_view.get('app-id')}"
                    )
                    return False

            return fetched_view

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while validating view ID: {view_id} and {e}",
                exc_info=True,
            )
            return False

    def _setup_config_paths(self) -> None:
        """
        Set up configuration paths based on the user's home directory.
        This initializes instance variables used throughout the application.
        """
        config_paths = self.setup_config_paths()

        # Set instance variables from the dictionary
        self.home: str = config_paths["home"]
        self.webapps_applications: str = os.path.join(
            self.home, ".local/share/applications"
        )
        self.config_path: str = config_paths["config_path"]
        self.style_css_config: str = config_paths["style_css_config"]
        self.cache_folder: str = config_paths["cache_folder"]

    def setup_config_paths(self) -> Dict[str, str]:
        """
        Set up and return configuration paths for the application.

        Returns:
            Dict[str, str]: A dictionary containing paths for home, config, styles, and cache.
                            Returns an empty dict if setup fails.
        """
        try:
            # Determine the user's home directory and script directory
            home = os.path.expanduser("~")
            # Define key paths
            config_path = os.path.join(home, ".config/waypanel")
            style_css_config = os.path.join(config_path, "styles.css")
            cache_folder = os.path.join(home, ".cache/waypanel")

            # Ensure required directories exist
            try:
                if not os.path.exists(config_path):
                    os.makedirs(config_path)
                    self.logger.info(f"Created config directory: {config_path}")

                if not os.path.exists(cache_folder):
                    os.makedirs(cache_folder)
                    self.logger.info(f"Created cache directory: {cache_folder}")
            except Exception as e:
                self.logger.error(
                    f"Failed to create required directories: {e}", exc_info=True
                )

            # Return the configuration paths
            return {
                "home": home,
                "config_path": config_path,
                "style_css_config": style_css_config,
                "cache_folder": cache_folder,
            }

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while setting up configuration paths: {e}",
                exc_info=True,
            )
            return {}

    def filter_utf_for_gtk(self, byte_string: Union[bytes, str]) -> str:
        """
        Safely decode a byte string to UTF-8, handling all encoding issues, with priority to UTF-8.

        Args:
            byte_string (Union[bytes, str]): The input byte string or already decoded string.

        Returns:
            str: The decoded string with invalid characters replaced or ignored.
        """
        try:
            # If the input is already a string, return it directly
            if isinstance(byte_string, str):
                return byte_string

            # If the input is bytes, attempt decoding
            if isinstance(byte_string, bytes):
                encodings = [
                    "utf-8",
                    "utf-16",
                    "utf-32",
                    "utf-16-le",
                    "utf-16-be",
                    "utf-32-le",
                    "utf-32-be",
                ]

                # Try each encoding in order
                for encoding in encodings:
                    try:
                        self.logger.debug(f"Attempting to decode using {encoding}...")
                        return byte_string.decode(encoding, errors="replace")
                    except UnicodeDecodeError as e:
                        self.logger.warning(
                            f"Failed to decode using {encoding}. Details: {e}"
                        )

                # Fallback to 'latin-1' if all other fail
                self.logger.info(
                    "All UTF decoding attempts failed, falling back to 'latin-1'."
                )
                return byte_string.decode("latin-1", errors="replace")

            # Raise an error if the input is neither bytes nor a string
            raise TypeError("Input must be a bytes object or a string.")

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while filtering UTF for GTK: {byte_string} and {e}",
                exc_info=True,
                extra={"input_type": type(byte_string).__name__},
            )
            return ""  # Return an empty string as a fallback

    from gi.repository import Gtk

    def create_button(
        self,
        icon_name: str,
        cmd: str,
        class_style: str,
        use_label: bool = False,
        use_function: Optional[Callable] = None,
        use_args: Optional[Any] = None,
    ) -> Optional[Gtk.Button]:
        """
        Create a Gtk.Button with an icon or label, click behavior, and CSS styling.

        Args:
            icon_name (str): The name of the icon or label text.
            cmd (str): The command to execute on button click. Use "NULL" to disable the button.
            class_style (str): The CSS class to apply to the button.
            use_label (bool): Whether to use a label instead of an icon.
            use_function (Optional[Callable]): A function to execute on button click.
            use_args (Optional[Any]): Arguments to pass to the custom function.

        Returns:
            Optional[Gtk.Button]: The created button, or None if creation failed.
        """
        try:
            # Validate inputs
            if not icon_name and not use_label:
                self.logger.error(
                    "Invalid input: Either icon_name or use_label must be provided.",
                    exc_info=True,
                )
                return None

            if not isinstance(class_style, str):
                self.logger.error(
                    f"Invalid class_style type: {type(class_style).__name__}",
                    exc_info=True,
                )
                return None

            # Create the button
            button = Gtk.Button()
            assert button is not None, "Button creation failed"

            # Create content box
            box = Gtk.Box()

            # Add icon or label
            if use_label:
                label = Gtk.Label(label=icon_name)
                box.append(label)
            else:
                if icon_name:  # Only add icon if name is provided
                    try:
                        icon = Gtk.Image.new_from_icon_name(icon_name)
                        box.append(icon)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to create icon with name: {icon_name}",
                            exc_info=True,
                        )
                        return None

            # Set content
            button.set_child(box)

            # If cmd is NULL, disable the button
            if cmd == "NULL":
                button.set_sensitive(False)
                return button

            # Set up click handling - LEFT CLICK
            if use_function:
                try:
                    button.connect("clicked", lambda *_: use_function(use_args))
                except Exception as e:
                    self.logger.error(
                        f"Failed to connect custom function to button: {e}",
                        exc_info=True,
                    )
                    return None
            else:
                try:
                    button.connect("clicked", lambda *_: self.run_cmd(cmd))
                except Exception as e:
                    self.logger.error(
                        f"Failed to connect command '{cmd}' to button: {e}",
                        exc_info=True,
                    )
                    return None

            # Apply CSS class
            try:
                button.add_css_class(class_style)
            except Exception as e:
                self.logger.error(
                    f"Failed to apply CSS class '{class_style}' to button: {e}",
                    exc_info=True,
                )
                return None

            return button

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(
                f"Unexpected error while creating button: {e}", exc_info=True
            )
            return None

    def is_plugin_enabled(self, plugin_name):
        config_file = os.getenv(
            "WAYFIRE_CONFIG_FILE", os.path.expanduser("~/.config/wayfire.ini")
        )

        if not os.path.exists(config_file):
            print(f"Config file not found: {config_file}")
            return False

        parser = configparser.ConfigParser()

        try:
            parser.read(config_file)
        except Exception as e:
            print(f"Error reading config file: {e}")
            return False

        if "core" not in parser.sections():
            print("No [core] section in config")
            return False

        plugins_line = parser["core"].get("plugins", "").strip()
        if not plugins_line:
            print("plugins= line missing or empty in [core]")
            return False

        plugins = [p.strip() for p in plugins_line.split(" ")]

        return plugin_name in plugins

    def is_keybind_used(self, keybinding):
        """
        Search line-by-line in the Wayfire config file for any line that ends with
        the given keybinding (after optional '=' and whitespace), after normalizing whitespace.

        Returns True if found, False otherwise.
        """
        config_file = os.getenv(
            "WAYFIRE_CONFIG_FILE", os.path.expanduser("~/.config/wayfire.ini")
        )

        if not os.path.exists(config_file):
            print(f"Config file not found: {config_file}")
            return False

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    stripped_line = line.strip()
                    if stripped_line.startswith("#"):
                        continue  # Skip comments

                    if "=" not in stripped_line:
                        continue  # Not a binding line

                    key_part = stripped_line.split("=", 1)[1].strip()

                    normalized_key_part = " ".join(key_part.split())
                    normalized_target = " ".join(keybinding.strip().split())

                    if normalized_key_part == normalized_target:
                        print(
                            f"Pattern '{keybinding}' matched on line {line_number}: {stripped_line}"
                        )
                        return True
            return False
        except Exception as e:
            print(f"Error reading config file: {e}")
            return False

    def get_wayctl_path(self):
        try:
            # Try to locate the installed 'waypanel' module
            waypanel_module_spec = importlib.util.find_spec("waypanel")
            if waypanel_module_spec is None:
                raise ImportError("The 'waypanel' module could not be found.")

            # Get the root path of the module (e.g. site-packages/waypanel or dev dir)
            waypanel_module_path = waypanel_module_spec.origin  # points to __init__.py

            # Traverse up until we find the "waypanel" folder
            while os.path.basename(waypanel_module_path) != "waypanel":
                waypanel_module_path = os.path.dirname(waypanel_module_path)

            # Now construct the path to wayctl.py
            wayctl_path = os.path.join(
                waypanel_module_path, "src", "plugins", "utils", "tools", "_wayctl.py"
            )

            if not os.path.exists(wayctl_path):
                raise FileNotFoundError(f"wayctl.py not found at {wayctl_path}")

            return wayctl_path

        except Exception as e:
            raise RuntimeError(f"Failed to locate wayctl.py: {e}")

    def register_wayctl_binding(self, keybind, keybind_fallback, args):
        if self.is_keybind_used(keybind):
            if keybind_fallback is None:
                return
            keybind = keybind_fallback
            if self.is_keybind_used(keybind):
                self.logger.warning(
                    f"Keybind '{keybind}' already used. Skipping registration."
                )
                return

        self.logger.info(f"Registering keybinding: {keybind}")
        self.ipc.register_binding(
            binding=keybind,
            command=f"python3 {self.get_wayctl_path()} {args}",
            exec_always=True,
            mode="normal",
        )
