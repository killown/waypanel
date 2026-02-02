import os
import psutil
import sys
from typing import Dict, Optional, Tuple, Union, Any
from gi.repository import GLib  # pyright: ignore
from pathlib import Path
import operator


class WayfireHelpers:
    """
    A class containing helper methods for interacting with the Wayfire IPC.
    """

    def __init__(self, panel_instance):
        """
        Initializes the WayfireHelpers instance with an IPC object.
        Args:
            ipc: An object representing the Wayfire IPC connection, which
                 is expected to have a `list_views()` method.
        """
        self.ipc = panel_instance.ipc
        self.logger = panel_instance.logger

    def has_output_fullscreen_view(self, output_id: str) -> bool:
        """
        Check if there is any fullscreen view on the specified output.
        This method retrieves the list of views and checks if any view is
        currently fullscreen on the specified output. It does not consider
        the workspace of the view; it only checks the fullscreen status
        and output ID.
        Args:
            output_id (str): The ID of the output to check for fullscreen views.
        Returns:
            bool: True if there is at least one fullscreen view on the specified
                  output, otherwise False.
        """
        try:
            list_views = self.ipc.list_views()
            if not list_views:
                return False
            return any(
                view["fullscreen"] and view["output-id"] == output_id
                for view in list_views
            )
        except Exception as e:
            self.logger.error(
                f"An error occurred while checking for fullscreen views: {e}"
            )
            return False

    def ping_wayfire_ipc(self):
        try:
            self.ipc.ping()
            return True
        except Exception as e:
            self.logger.error(f"Failed to ping Wayfire IPC: {e}")
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
            return self.check_lib_in_wayfire(lib_name)
        except Exception as e:
            self.logger.error(
                f"Unexpected error while finding library '{lib_name}' in Wayfire: {e}",
                exc_info=True,
            )
            return False

    def check_lib_in_wayfire(self, lib_name: str) -> bool:
        """
        Check if a specific shared library is loaded by the Wayfire process.
        Args:
            lib_name (str): The name of the shared library to check.
        Returns:
            bool: True if the library is found in the Wayfire process, False otherwise.
        """
        try:
            if not lib_name or not isinstance(lib_name, str):
                self.logger.warning(f"Invalid or missing library name: {lib_name}")
                return False
            pid = self.get_wayfire_pid()
            if not pid:
                self.logger.info("Wayfire process not found.")
                return False
            self.logger.debug(
                f"Checking for library '{lib_name}' in Wayfire process (PID: {pid})"
            )
            libs = self.list_libs_in_process(pid)
            if not libs:
                self.logger.debug(
                    f"No shared libraries found for Wayfire process (PID: {pid})"
                )
                return False
            for lib in libs:
                if lib_name in lib:
                    self.logger.debug(
                        f"Found library '{lib_name}' in Wayfire process: {lib}"
                    )
                    return True
            self.logger.debug(f"Library '{lib_name}' not found in Wayfire process.")
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error while checking for library '{lib_name}' in Wayfire process: {e}",
                exc_info=True,
            )
            return False

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
            if not os.path.exists(maps_file):
                self.logger.warning(f"Maps file not found for PID: {pid}")
                return libs
            with open(maps_file, "r") as f:
                for line in f:
                    if "so" in line:
                        lib_path = line.split()[-1]
                        if os.path.isfile(lib_path) and lib_path not in libs:
                            libs.append(lib_path)
                            self.logger.debug(f"Found shared library: {lib_path}")
        except FileNotFoundError:
            self.logger.error(
                error=FileNotFoundError(f"Maps file not found: {maps_file}"),
                message=f"Failed to read /proc/{pid}/maps",
            )
        except Exception as e:
            self.logger.error(
                exc_info=True,
            )
        return libs

    def get_wayfire_pid(self) -> Optional[int]:
        """
        Retrieve the PID of the Wayfire compositor process.
        Returns:
            Optional[str]: The PID of the Wayfire process if found, otherwise None.
        """
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
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
                    self.logger.warning(
                        f"Failed to read /proc/{entry}/comm. Details: {e}"
                    )
                    continue
            self.logger.info("No Wayfire process found.")
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error while retrieving Wayfire PID: {e}",
                exc_info=True,
            )
            return None

    def send_view_to_output(self, view_id, direction=None, toggle_scale_off=False):
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
            send_view_to_output(123, "left")
        Notes:
            - The `direction` argument must be a valid string ("left" or "right").
            - If the view is already on the focused output, the function uses `get_output_from(direction)`
              to determine the target output ID.
        """
        view = self.ipc.get_view(view_id)
        geo = view["geometry"]
        focused_output = self.ipc.get_focused_output()
        wset_index_focused = focused_output.get("wset-index")
        wset_index_view = view["wset-index"]
        next_output = [
            i.get("id")
            for i in self.ipc.list_outputs()
            if i.get("id") != focused_output.get("id")
        ]
        if toggle_scale_off:
            self.ipc.scale_toggle(focused_output.get("id"))
        if direction is None and next_output:
            self.ipc.configure_view(
                view_id,
                geo["x"],
                geo["y"],
                geo["width"],
                geo["height"],
                next_output[0],
            )
        if wset_index_focused != wset_index_view:
            self.ipc.configure_view(
                view_id,
                geo["x"],
                geo["y"],
                geo["width"],
                geo["height"],
                focused_output.get("id"),
            )
        else:
            if direction:
                output_direction = self.get_output_from(direction)
                self.ipc.configure_view(
                    view_id,
                    geo["x"],
                    geo["y"],
                    geo["width"],
                    geo["height"],
                    output_direction,
                )

        def set_maximized(view_id=view_id):
            tiled_edges = view.get("tiled-edges") == 15
            if tiled_edges:
                self.ipc.set_focus(view_id)
                self.ipc.set_view_maximized(view_id)
            return

        GLib.timeout_add(100, set_maximized, view_id)

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
            left_output_id = self.get_output_from("left")
            if left_output_id:
                self.logger.error(f"Output to the left: {left_output_id}")
            else:
                self.logger.error("No output to the left.")
            right_output_id = self.get_output_from("right")
            if right_output_id:
                self.logger.error(f"Output to the right: {right_output_id}")
            else:
                self.logger.error("No output to the right.")
        Notes:
            - The function uses horizontal distances (`x` coordinates) to determine adjacency.
            - Outputs are considered "to the left" if their right edge is to the left of the focused output's left edge.
            - Outputs are considered "to the right" if their left edge is to the right of the focused output's right edge.
            - If multiple outputs exist in the specified direction, the closest one is returned.
        """
        try:
            if direction not in ["left", "right"]:
                raise ValueError(
                    f"Invalid direction: {direction}. Must be 'left' or 'right'."
                )
            outputs = self.ipc.list_outputs()
            focused_output = self.ipc.get_focused_output()
            if not focused_output:
                raise ValueError("No focused output found.")
            focused_geometry = focused_output["geometry"]
            focused_x = focused_geometry["x"]
            focused_width = focused_geometry["width"]
            target_output_id = None
            target_distance = float("inf")
            for output in outputs:
                if output.get("id") == focused_output.get("id"):
                    continue
                output_geometry = output["geometry"]
                output_x = output_geometry["x"]
                if direction == "left":
                    if output_x + output_geometry["width"] <= focused_x:
                        distance = focused_x - (output_x + output_geometry["width"])
                        if distance < target_distance:
                            target_output_id = output.get("id")
                            target_distance = distance
                elif direction == "right":
                    if output_x >= focused_x + focused_width:
                        distance = output_x - (focused_x + focused_width)
                        if distance < target_distance:
                            target_output_id = output.get("id")
                            target_distance = distance
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

    def center_view_on_output(
        self, view_id: int, w: int | None = None, h: int | None = None
    ):
        """Centers a view within its assigned output's workarea.

        Args:
            view_id: The unique identifier of the view.
            w: Target width. If None, current view width is used.
            h: Target height. If None, current view height is used.

        Returns:
            The result of the IPC configure command.
        """
        view = self.ipc.get_view(view_id)
        outputs = self.ipc.list_outputs()

        out = next(o for o in outputs if o["id"] == view["output-id"])

        if w is None:
            w = view["geometry"]["width"]
        if h is None:
            h = view["geometry"]["height"]

        wa = out["workarea"]

        target_x = wa["x"] + (wa["width"] - w) // 2
        target_y = wa["y"] + (wa["height"] - h) // 2

        return self.ipc.configure_view(
            view_id, int(target_x), int(target_y), int(w), int(h)
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
        view_center_x = view_geometry["x"] + view_geometry["width"] // 2
        view_center_y = view_geometry["y"] + view_geometry["height"] // 2
        cursor_x = monitor_geometry["x"] + view_center_x
        cursor_y = monitor_geometry["y"] + view_center_y
        return cursor_x, cursor_y

    def move_cursor_middle_output(self, output_id: int) -> None:
        """
        Move the cursor to the center of the specified output (monitor).
        Args:
            output_id (int): The unique identifier of the output.
        """
        try:
            output = self.ipc.get_output(output_id)
            if not output:
                self.logger.warning(f"Output with ID '{output_id}' not found.")
                return
            output_geometry = output.get("geometry")
            if not output_geometry:
                self.logger.warning(f"Output with ID '{output_id}' has no geometry.")
                return
            cursor_x = output_geometry["x"] + output_geometry["width"] // 2
            cursor_y = output_geometry["y"] + output_geometry["height"] // 2
            self.ipc.move_cursor(cursor_x, cursor_y)
            self.logger.info(
                f"Cursor moved to the center of output {output_id} at ({cursor_x}, {cursor_y})."
            )
        except Exception as e:
            self.logger.error(
                "Error while moving cursor to output center.",
                error=e,
                context={"output_id": output_id},
            )

    def move_cursor_middle(self, view_id: str) -> None:
        """
        Move the cursor to the center of the specified view on its output (monitor).
        Args:
            view_id (str): The unique identifier of the view/window.
        """
        view = self.ipc.get_view(view_id)
        if not view:
            self.logger.warning(f"View with ID '{view_id}' not found.")
            return
        output_id = view["output-id"]
        view_geometry = view["geometry"]
        output = self.ipc.get_output(output_id)
        if not output:
            self.logger.warning(f"Output with ID '{output_id}' not found.")
            return
        output_geometry = output["geometry"]
        cursor_x, cursor_y = self.find_view_middle_cursor_position(
            view_geometry, output_geometry
        )
        self.ipc.move_cursor(cursor_x, cursor_y)

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
            self.ipc.set_focus(view.get("id"))
            return False
        return True

    def find_empty_workspace(self) -> Optional[tuple]:
        """
        Find an empty workspace using wf_utils.get_workspaces_without_views().
        Returns:
            Optional[tuple]: (x, y) coordinates of the first empty workspace,
                             or None if no empty workspace is found.
        """
        try:
            empty_workspaces = self.ipc.get_workspaces_without_views()
            if empty_workspaces:
                return empty_workspaces[0]
            return None
        except Exception as e:
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

    def is_view_valid(
        self, view: Union[int, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Validate if a view is valid based on its ID or dictionary.
        If the view is valid and exists in the compositor, returns its details (dict).
        Otherwise, returns None.
        Args:
            view (Union[int, dict]): The ID of the view or a dictionary containing view details.
        Returns:
            Optional[dict]: The view object if valid, otherwise None.
        """
        view_id: Optional[int] = None
        if isinstance(view, dict):
            view_id = view.get("id")
        elif isinstance(view, int):
            view_id = view
        if not isinstance(view_id, int) or view_id is None:
            self.logger.warning(
                "Input is not a valid view ID (int) or dictionary with an 'id'."
            )
            return None
        fetched_view: Optional[Dict[str, Any]] = None
        try:
            fetched_view = self.ipc.get_view(view_id)
            if not fetched_view:
                self.logger.debug(
                    f"View details not found via IPC for ID: {view_id}. View is likely closed."
                )
                return None
        except Exception as e:
            self.logger.error(
                f"Failed to fetch view details for ID {view_id}: {e}", exc_info=True
            )
            return None
        role = fetched_view.get("role")
        app_id = fetched_view.get("app-id")
        pid = fetched_view.get("pid")
        if role and app_id:
            if role != "toplevel":
                self.logger.debug(f"View ID {view_id} has an invalid role: {role}")
                return None
            if pid == -1:
                self.logger.debug(f"View ID {view_id} has an invalid PID: {pid}")
                return None
            if app_id in ["", "nil"]:
                self.logger.debug(f"View ID {view_id} has an invalid app-id: {app_id}")
                return None
        return fetched_view

    def tile_maximize_all_from_active_workspace(self, should_maxmize):
        view_ids = self.ipc.get_views_from_active_workspace()
        [self.ipc.set_tiling_maximized(view_id, should_maxmize) for view_id in view_ids]

    def get_wayctl_path(self):
        """
        Locate the path to the _wayctl.py script by traversing the directory tree
        relative to the current file's location.
        """
        try:
            current_dir = Path(__file__).resolve().parent
            wayctl_path = (
                current_dir
                / ".."
                / ".."
                / "src"
                / "plugins"
                / "utils"
                / "tools"
                / "_wayctl.py"
            )
            if not wayctl_path.exists():
                raise FileNotFoundError(f"wayctl.py not found at {wayctl_path}")
            return str(wayctl_path)
        except (FileNotFoundError, RuntimeError) as e:
            raise RuntimeError(f"Failed to locate wayctl.py: {e}") from e

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
            self.logger.error(f"Config file not found: {config_file}")
            return False
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    stripped_line = line.strip()
                    if stripped_line.startswith("#"):
                        continue
                    if "=" not in stripped_line:
                        continue
                    key_part = stripped_line.split("=", 1)[1].strip()
                    normalized_key_part = " ".join(key_part.split())
                    normalized_target = " ".join(keybinding.strip().split())
                    if normalized_key_part == normalized_target:
                        self.logger.error(
                            f"Pattern '{keybinding}' matched on line {line_number}: {stripped_line}"
                        )
                        return True
            return False
        except Exception as e:
            self.logger.error(f"Error reading config file: {e}")
            return False

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

    def view_focus_effect_selected(
        self, view: dict, alpha: float = 1.0, selected: bool = False
    ) -> None:
        """
        Apply a focus indicator effect by animating the view's alpha.
        Always restores the original alpha value retrieved before the effect started.
        """
        view_id = view.get("id")
        if not view_id or not self.is_view_valid(view_id):
            return

        if selected:
            # Only store if we haven't stored it yet to avoid capturing the 'effect' alpha
            stored = self.ipc.get_view_property(view_id, "original_alpha")
            if not stored or (
                isinstance(stored, dict) and stored.get("result") != "ok"
            ):
                original_alpha_value = self.ipc.get_view_alpha(view_id)["alpha"]
                self.ipc.set_view_property(
                    view_id, "original_alpha", str(original_alpha_value)
                )

            self.ipc.set_view_alpha(view_id, alpha)
        else:
            stored = self.ipc.get_view_property(view_id, "original_alpha")
            if stored:
                val = stored.get("value") if isinstance(stored, dict) else stored
                if val:
                    self.ipc.set_view_alpha(view_id, float(str(val).replace(",", ".")))

    def is_plugin_enabled(self, plugin_name: str) -> bool:
        """
        Check if a Wayfire plugin is enabled.
        """
        return plugin_name in self.ipc.get_option_value("core/plugins")["value"]

    def find_redirection_file(self, process_name):
        """
        Finds the file path to which the standard output (file descriptor 1)
        of a running process is redirected.
        """
        STDOUT_FD = 1
        wayfire_processes = [
            proc
            for proc in psutil.process_iter(["pid", "name"])
            if proc.info["name"] and process_name.lower() in proc.info["name"].lower()
        ]
        if not wayfire_processes:
            self.logger.info(
                f"Error: No running process found with the name '{process_name}'."
            )
            return
        process = wayfire_processes[0]
        pid = process.info["pid"]
        try:
            if sys.platform.startswith("linux") or sys.platform.startswith("darwin"):
                fd_path = f"/proc/{pid}/fd/{STDOUT_FD}"
                if not os.path.exists(fd_path):
                    pass
                try:
                    target_file = os.readlink(fd_path)
                    if target_file.startswith(("pipe", "socket")):
                        self.logger.info(
                            f"Stdout (FD {STDOUT_FD}) is connected to an in-memory pipe or socket."
                        )
                        self.logger.info(
                            "This usually means it is being piped to another process or a terminal."
                        )
                        return
                    elif target_file == "/dev/null":
                        self.logger.info(
                            f"Stdout (FD {STDOUT_FD}) is redirected to /dev/null (output is discarded)."
                        )
                        return
                    elif target_file.startswith("/dev/pts"):
                        return target_file
                    elif target_file.startswith("/dev/tty"):
                        return target_file
                    else:
                        return target_file
                except FileNotFoundError:
                    print(
                        f"Could not find file descriptor {STDOUT_FD} path for PID {pid}."
                    )
                except PermissionError:
                    self.logger.exception(
                        f"Permission denied to read /proc/{pid}/fd/{STDOUT_FD}. Try running with 'sudo'."
                    )
                    return
            self.logger.info("\nChecking process open files as a fallback...")
            open_files = process.open_files()
            for file in open_files:
                if file.fd == STDOUT_FD and "w" in file.mode:
                    return file.path
            self.logger.warning(
                "Stdout (FD 1) is not explicitly redirected to a standard file or could not be determined."
            )
            self.logger.warning(
                "It is likely going to a terminal, system log (e.g., journald), or being piped."
            )
        except psutil.NoSuchProcess:
            self.logger.exception(
                f"Error: Process with PID {pid} is no longer running."
            )
        except Exception as e:
            self.logger.exception(f"An unexpected error occurred: {e}")

    def get_the_last_focused_view_id(self, skip_minimized=False, skip_maximized=False):
        workspace_ids = self.ipc.get_views_from_active_workspace()
        if not workspace_ids:
            return None
        active_views_data = []
        for view_id in workspace_ids:
            view_data = self.ipc.get_view(view_id)
            is_minimized = view_data.get("minimized", False)
            timestamp = view_data.get("last-focus-timestamp")
            if timestamp is None:
                continue
            skip_view = False
            if skip_minimized and is_minimized:
                skip_view = True
            if skip_maximized and not is_minimized:
                skip_view = True
            if skip_view:
                continue
            active_views_data.append((view_id, timestamp))
        if not active_views_data:
            return None
        most_recent_tuple = max(active_views_data, key=operator.itemgetter(1))
        most_recent_id = most_recent_tuple[0]
        return most_recent_id

    def get_most_recent_focused_view(self) -> dict | None:
        """Returns the view with the highest last-focus-timestamp.

        Args:
            views: List of view dictionaries.

        Returns:
            The most recently focused view dictionary or None if list is empty.
        """
        views = self.ipc.list_views()
        return max(views, key=lambda x: x.get("last-focus-timestamp", 0))

    def get_view_by_pid(self, pid: int) -> dict | None:
        """
        Retrieves detailed Wayfire view metadata for a specific Process ID.

        Args:
            pid (int): The process ID to search for.

        Returns:
            dict | None: The view metadata dictionary if found, otherwise None.
        """
        if not pid:
            return None

        try:
            # Accessing the IPC socket (sock) and listing all active views
            all_views = self.ipc.list_views()

            # Generator expression to find the first matching view by PID
            return next((view for view in all_views if view.get("pid") == pid), None)

        except Exception as e:
            self.logger.error(f"Failed to resolve view for PID {pid}: {e}")
            return None

    def _check_hanging_process(self, vid):
        """Checks if view is still active via IPC and kills it if PID > 0."""
        import os
        import signal
        import subprocess

        # Retrieve the current state of the view directly
        view = self.ipc.get_view(vid)

        # If view is gone (None) completely, we are good.
        if not view:
            return False

        pid = view.get("pid", -1)

        # PID -1 usually implies successful minimization to tray.
        # We only kill if we have a tangible Process ID > 0.
        if pid <= 0:
            return False

        # If PID is valid (>0) and view still exists, it is hanging.
        app_id = view.get("app-id", "Unknown")

        subprocess.Popen(
            [
                "notify-send",
                "-i",
                "process-stop-symbolic",
                "Taskbar Watchdog",
                f"Process '{app_id}' is hanging. Force killing...",
            ]
        )

        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            # Process might have died exactly between check and kill
            pass
        except Exception as e:
            self.logger.error(f"Watchdog failed to kill {pid} ({app_id}): {e}")

        return False
