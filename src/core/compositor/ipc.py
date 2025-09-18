import logging
import os
import socket

from typing import (
    Any,
    Callable,
    Optional,
    Type,
    Union,
    List,
    Tuple,
    Dict,
    get_origin,
    get_args,
)

from functools import wraps

from gi.repository import GLib

logger = logging.getLogger(__name__)


def validate_type(
    value: Any,
    expected_type: Union[Type, List[Type], Tuple[Type, ...]],
    name: str = "value",
    allow_none: bool = False,
    optional: bool = False,
) -> bool:
    """
    Validate that the provided value matches the expected type.

    Supports:
        - Single types (int, str, etc.)
        - Lists of types for iterables or unions
        - Optional/None values via `allow_none` or `optional`

    Args:
        value: The value to validate.
        expected_type: Expected type(s) (e.g., int, [str, int], (str, int), Optional[str])
        name: Name/description of the value for error messages.
        allow_none: If True, allows None even if not in Optional.
        optional: If True, treats as Optional[expected_type].

    Returns:
        bool: True if valid, raises TypeError otherwise.
    """
    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin is Union and type(None) in args:
        inner_type = [t for t in args if t is not type(None)]
        if len(inner_type) == 1:
            return validate_type(value, inner_type[0], name=name, allow_none=True)

    if optional:
        if value is None:
            return True
        return validate_type(value, expected_type, name=name)

    if allow_none and value is None:
        return True

    if isinstance(expected_type, list):
        if not isinstance(value, list):
            raise TypeError(
                f"Invalid {name}: Expected list, got {type(value).__name__}"
            )
        for idx, item in enumerate(value):
            if not any(isinstance(item, t) for t in expected_type):
                raise TypeError(
                    f"Invalid element at index {idx} in {name}: "
                    f"Expected one of {', '.join(t.__name__ for t in expected_type)}, "
                    f"got {type(item).__name__}"
                )
        return True

    if isinstance(expected_type, tuple):
        if not isinstance(value, tuple):
            raise TypeError(
                f"Invalid {name}: Expected tuple, got {type(value).__name__}"
            )
        if len(expected_type) != len(value):
            raise TypeError(
                f"Length mismatch in {name}: Expected {len(expected_type)} elements, "
                f"got {len(value)}"
            )
        for idx, (item, typ) in enumerate(zip(value, expected_type)):
            if not isinstance(item, typ):
                raise TypeError(
                    f"Invalid element at index {idx} in {name}: "
                    f"Expected {typ.__name__}, got {type(item).__name__}"
                )
        return True

    if not isinstance(value, expected_type):
        raise TypeError(
            f"Invalid {name}: Expected type {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )

    return True


def type_checked(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        annotations = func.__annotations__
        for arg_name, arg_value in kwargs.items():
            expected_type = annotations.get(arg_name)
            if expected_type:
                validate_type(arg_value, expected_type, name=arg_name)
        return func(*args, **kwargs)

    return wrapper


def apply_type_checked(cls: type) -> type:
    """
    A class decorator that applies @type_checked to all callable methods.
    """
    for name, method in vars(cls).items():
        if isinstance(method, (classmethod, staticmethod)):
            # Handle classmethod/staticmethod wrappers
            inner_func = method.__func__
            wrapped_func = type_checked(inner_func)
            decorated_method = type(method)(wrapped_func)
            setattr(cls, name, decorated_method)
        elif callable(method) and not name.startswith("__"):
            # Regular instance method
            setattr(cls, name, type_checked(method))
    return cls


def handle_ipc_error(func):
    """Decorator to handle common IPC-related errors."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except (socket.error, ConnectionRefusedError, BrokenPipeError) as e:
            logger.error(f"IPC connection error in '{func.__name__}': {e}")
            self.is_compositor_socket_set_up = False
            self.sock = None
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred in '{func.__name__}': {e}")
            return None

    return wrapper


@apply_type_checked
class IPC:
    """
    This module provides a Python interface to communicate with the Wayfire and Sway
    compositors via their respective IPC (Inter-Process Communication) sockets.

    It encapsulates the functionality required to send commands, retrieve information,
    and manage various aspects of the compositor dynamically. It automatically detects
    the running compositor and uses the appropriate backend.
    """

    def __init__(self):
        """
        Initializes the IPC instance. It detects the compositor and establishes
        the connection. A GLib timeout is set to ensure the connection remains active.
        """
        self.compositor_name = self.setup_compositor_socket()
        GLib.timeout_add(1000, self.ensure_ipc_connection)

    def setup_compositor_socket(self):
        """
        Determines the active compositor (Wayfire or Sway) based on environment
        variables and initializes the corresponding IPC socket object.
        """
        if os.getenv("WAYFIRE_SOCKET"):
            self.connect_wayfire_ipc()
            return "wayfire"
        if os.getenv("SWAYSOCK"):
            self.connect_sway_ipc()
            return "sway"
        return None

    def connect_wayfire_ipc(self):
        """Initializes the connection to the Wayfire IPC socket."""
        try:
            from wayfire.core.template import get_msg_template
            from wayfire import WayfireSocket
            from wayfire.extra.ipc_utils import WayfireUtils
            from wayfire.extra.stipc import Stipc

            self.sock = WayfireSocket()
            self.wf_utils = WayfireUtils(self.sock)
            self.stipc = Stipc(self.sock)
            self.is_compositor_socket_set_up = True
            self.get_msg_template = get_msg_template
        except Exception as e:
            logger.error(f"Failed to connect to Wayfire IPC: {e}")
            self.sock = None
            self.is_compositor_socket_set_up = False

    def connect_sway_ipc(self):
        """Initializes the connection to the Sway IPC socket."""
        try:
            from pysway.ipc import SwayIPC
            from pysway.extra.utils import SwayUtils

            self.sock = SwayIPC()
            self.utils = SwayUtils(self.sock)
        except Exception as e:
            logger.error(f"Failed to connect to Sway IPC: {e}")
            self.sock = None

    def ensure_ipc_connection(self):
        """
        Periodically checks if the IPC connection is active. If not, it attempts
        to re-establish the connection.
        """
        if not self.sock or not self.is_connected():
            logger.warning("Attempting to re-establish IPC connection...")
            self.setup_compositor_socket()
        return True

    @handle_ipc_error
    def get_view(self, id: int) -> Optional[Dict[str, Any]]:
        """Get the view by the given id."""
        return self.sock.get_view(id)  # pyright: ignore

    @handle_ipc_error
    def set_focus(self, view_id: int) -> Any:
        """Set focus to the specified view."""
        if self.compositor_name == "wayfire":
            return self.sock.set_focus(view_id)  # pyright: ignore
        if self.compositor_name == "sway":
            return self.sock.set_view_focus(view_id)  # pyright: ignore

    @handle_ipc_error
    def set_view_alpha(self, id: int, alpha: float) -> Any:
        """Set the view alpha by the given id."""
        return self.sock.set_view_alpha(id, alpha)  # pyright: ignore

    @handle_ipc_error
    def list_outputs(self) -> Optional[List[Dict[str, Any]]]:
        """List all outputs connected to the compositor."""
        return self.sock.list_outputs()  # pyright: ignore

    @handle_ipc_error
    def get_focused_output(self) -> Optional[Dict[str, Any]]:
        """Get the currently focused output."""
        return self.sock.get_focused_output()  # pyright: ignore

    @handle_ipc_error
    def get_focused_view(self) -> Optional[Dict[str, Any]]:
        """Get the currently focused view."""
        return self.sock.get_focused_view()  # pyright: ignore

    @handle_ipc_error
    def list_views(self) -> List[Dict[str, Any]]:
        """List all views managed by the compositor."""
        return self.sock.list_views()  # pyright: ignore

    @handle_ipc_error
    def watch(self, events=None) -> Any:
        """Start watching for compositor events."""
        return self.sock.watch(events)  # pyright: ignore

    @handle_ipc_error
    def read_next_event(self) -> Optional[Dict[str, Any]]:
        """Read the next event from the compositor."""
        return self.sock.read_next_event()  # pyright: ignore

    def is_connected(self) -> bool:
        """Check if the compositor socket is connected."""
        if self.sock:
            return self.sock.is_connected()  # pyright: ignore
        return False

    @handle_ipc_error
    def close(self) -> Any:
        """Close the compositor socket connection."""
        return self.sock.close()  # pyright: ignore

    @handle_ipc_error
    def set_workspace(self, x: int, y: int, view_id: Optional[int] = None) -> Any:
        """Set the workspace to the specified coordinates."""
        if view_id is None:
            return self.sock.set_workspace(x, y)  # pyright: ignore
        else:
            return self.sock.set_workspace(x, y, view_id)  # pyright: ignore

    @handle_ipc_error
    def list_ids(self) -> List[int]:
        """Get a list of all view IDs."""
        views = self.sock.list_views()  # pyright: ignore
        if views:
            return [view["id"] for view in views]
        return []

    @handle_ipc_error
    def get_view_geometry(self, view_id: int) -> Optional[Dict[str, Any]]:
        """Get the geometry of a specific view."""
        view = self.sock.get_view(view_id)  # pyright: ignore
        if view:
            return view.get("geometry")

    @handle_ipc_error
    def configure_view(
        self,
        view_id: int,
        x: int,
        y: int,
        w: int,
        h: int,
        output_id: Optional[int] = None,
    ) -> Any:
        """Configure a view's position and size."""
        if hasattr(self.sock, "configure_view"):
            return self.sock.configure_view(view_id, x, y, w, h, output_id)  # pyright: ignore

    @handle_ipc_error
    def has_output_fullscreen_view(self, output_id: Optional[int] = None) -> bool:
        """Check if the specified output has fullscreen views."""
        return self.wf_utils.has_output_fullscreen_view(output_id)  # pyright: ignore

    @handle_ipc_error
    def go_workspace_set_focus(self, view_id: int) -> None:
        """Set focus to a view and go to its workspace."""
        return self.wf_utils.go_workspace_set_focus(view_id)  # pyright: ignore

    @handle_ipc_error
    def center_cursor_on_view(self, view_id: int) -> None:
        """Center cursor on the specified view."""
        return self.wf_utils.center_cursor_on_view(view_id)  # pyright: ignore

    @handle_ipc_error
    def get_views_from_active_workspace(self):
        """Get all views on the currently active workspace."""
        return self.wf_utils.get_views_from_active_workspace()  # pyright: ignore

    @handle_ipc_error
    def move_cursor(self, x: int, y: int) -> None:
        """Move the cursor to the specified coordinates."""
        return self.stipc.move_cursor(x, y)  # pyright: ignore

    @handle_ipc_error
    def run_cmd(self, cmd: str) -> None:
        """
        Run a shell command using subprocess.Popen in a separate thread to
        avoid blocking the main GTK thread.
        """
        return self.stipc.run_cmd(cmd)  # pyright: ignore

    @handle_ipc_error
    def click_button(self, button: str, mode: str) -> None:
        """Simulate mouse button click."""
        return self.stipc.click_button(button, mode)  # pyright: ignore

    @handle_ipc_error
    def list_input_devices(self) -> Optional[Dict[str, Any]]:
        """Retrieve a list of input devices managed by the compositor."""
        return self.sock.list_input_devices()  # pyright: ignore

    @handle_ipc_error
    def configure_input_device(self, device_id: int, enable: bool) -> None:
        """Enable or disable an input device."""
        if hasattr(self.sock, "configure_input_device"):
            return self.sock.configure_input_device(device_id, enable)  # pyright: ignore

    @handle_ipc_error
    def get_output(self, output_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific output."""
        return self.sock.get_output(output_id)  # pyright: ignore

    @handle_ipc_error
    def get_current_workspace(self) -> Optional[Dict[str, Any]]:
        """Get the current workspace coordinates."""
        focused_output = self.sock.get_focused_output()  # pyright: ignore
        if focused_output is not None:
            return focused_output.get("workspace", {})

    @handle_ipc_error
    def get_active_workspace_number(self) -> Optional[int]:
        """Retrieve the number of the currently active workspace."""
        focused_output = self.sock.get_focused_output()  # pyright: ignore
        if focused_output is not None:
            workspace_info = focused_output.get("workspace", {})
            return self.get_workspace_number(workspace_info["x"], workspace_info["y"])

    @handle_ipc_error
    def get_workspace_number(self, workspace_x: int, workspace_y: int) -> int:
        """Convert workspace coordinates to a workspace number."""
        return self.wf_utils.get_workspace_number(workspace_x, workspace_y)  # pyright: ignore

    @handle_ipc_error
    def set_view_minimized(self, view_id: int, state: bool) -> None:
        """Set the minimized state of a view."""
        return self.sock.set_view_minimized(view_id, state)  # pyright: ignore

    @handle_ipc_error
    def set_view_maximized(self, view_id: int) -> None:
        """Set the maximized state of a specific view."""
        return self.wf_utils.set_view_maximized(view_id)  # pyright: ignore

    @handle_ipc_error
    def set_view_fullscreen(self, view_id: int, state: bool) -> None:
        """Set the fullscreen state of a specific view."""
        return self.sock.set_view_fullscreen(view_id, state)  # pyright: ignore

    @handle_ipc_error
    def set_view_focus(self, view_id: int) -> None:
        """Set focus to a specific view."""
        return self.set_focus(view_id)

    @handle_ipc_error
    def close_view(self, view_id: int) -> bool:
        """Close a specific view."""
        return self.sock.close_view(view_id)  # pyright: ignore

    @handle_ipc_error
    def create_wayland_output(self) -> None:
        """Create a Wayland output using Stipc."""
        return self.stipc.create_wayland_output()  # pyright: ignore

    @handle_ipc_error
    def destroy_wayland_output(self, output: str) -> None:
        """Destroy a Wayland output using Stipc."""
        return self.stipc.destroy_wayland_output(output)  # pyright: ignore

    @handle_ipc_error
    def get_output_id_by_name(self, output_name: str) -> Optional[int]:
        """Get output ID by its name."""
        outputs = self.sock.list_outputs()  # pyright: ignore
        if outputs:
            for output in outputs:
                if output["name"] == output_name:
                    return output["id"]
        return None

    @handle_ipc_error
    def get_output_geometry(self, output_id: int) -> Optional[Dict[str, Any]]:
        """Get geometry of a specific output."""
        output = self.sock.get_output(output_id)  # pyright: ignore
        if output:
            return output["geometry"]

    @handle_ipc_error
    def get_workspaces_without_views(self) -> List[List[int]]:
        """
        Get workspaces that don't contain any views.

        Returns:
            List[List[int]]: A list of workspace coordinates in [x, y] format.
            Example: [[1, 0], [2, 0], [0, 1], ...]
        """
        return self.wf_utils.get_workspaces_without_views()  # pyright: ignore

    @handle_ipc_error
    def get_workspace_from_view(self, view_id: int) -> Dict[str, int]:
        """Get workspace coordinates for a specific view."""
        return self.wf_utils.get_workspace_from_view(view_id)  # pyright: ignore

    @handle_ipc_error
    def get_focused_output_views(self) -> List[Dict[str, Any]]:
        """Get all views on the focused output."""
        return [
            view
            for view in self.sock.list_views()  # pyright: ignore
            if view["output-id"] == self.get_focused_output_id()
        ]

    @handle_ipc_error
    def get_focused_output_id(self) -> Optional[int]:
        """Get ID of the currently focused output."""
        focused_output = self.sock.get_focused_output()  # pyright: ignore
        if focused_output:
            return focused_output["id"]

    #  WARNING: wayfire specific functions -------------------
    @handle_ipc_error
    def get_view_alpha(self, id: int) -> float:
        """Get the view alpha by the given id."""
        return self.sock.get_view_alpha(id)  # pyright: ignore

    @handle_ipc_error
    def hide_view(self, view_id: int) -> None:
        """Hide a specific view."""
        message = self.get_msg_template("hide-view/hide")  # pyright: ignore
        message["data"]["view-id"] = view_id
        self.sock.send_json(message)  # pyright: ignore

    @handle_ipc_error
    def unhide_view(self, view_id: int) -> None:
        """Unhide a specific view."""
        message = self.get_msg_template("hide-view/unhide")  # pyright: ignore
        message["data"]["view-id"] = view_id
        self.sock.send_json(message)  # pyright: ignore

    @handle_ipc_error
    def toggle_showdesktop(self) -> None:
        """Toggle the 'show desktop' mode."""
        return self.sock.toggle_showdesktop()  # pyright: ignore

    @handle_ipc_error
    def toggle_expo(self) -> None:
        """Toggle the Expo mode."""
        return self.sock.toggle_expo()  # pyright: ignore

    @handle_ipc_error
    def create_headless_output(self, width: int, height: int) -> Dict[str, Any]:
        """Create a headless output with the specified dimensions."""
        return self.sock.create_headless_output(width, height)  # pyright: ignore

    @handle_ipc_error
    def destroy_headless_output(
        self, output_name: Optional[str] = None, output_id: Optional[int] = None
    ) -> None:
        """Destroy a headless output by its name or ID."""
        return self.sock.destroy_headless_output(output_name, output_id)  # pyright: ignore

    @handle_ipc_error
    def cube_activate(self) -> bool:
        """Activate the cube effect."""
        return self.sock.cube_activate()  # pyright: ignore

    @handle_ipc_error
    def cube_rotate_left(self) -> bool:
        """Rotate the cube to the left."""
        return self.sock.cube_rotate_left()  # pyright: ignore

    @handle_ipc_error
    def cube_rotate_right(self) -> bool:
        """Rotate the cube to the right."""
        return self.sock.cube_rotate_right()  # pyright: ignore

    @handle_ipc_error
    def scale_toggle_all(self, output_id: Optional[int] = None) -> None:
        """Toggle the Scale mode for all workspaces."""
        if output_id is not None:
            self.sock.scale_toggle_all(output_id)  # pyright: ignore
        else:
            self.sock.scale_toggle_all()  # pyright: ignore

    @handle_ipc_error
    def scale_toggle(self, output_id: Optional[int] = None) -> None:
        """Toggle the scale plugin."""
        if output_id is not None:
            self.sock.scale_toggle(output_id)  # pyright: ignore
        else:
            self.sock.scale_toggle()  # pyright: ignore

    @handle_ipc_error
    def assign_slot(self, view_id: int, slot: str) -> None:
        """Assign a slot to a view."""
        return self.sock.assign_slot(view_id, slot)  # pyright: ignore

    @handle_ipc_error
    def get_option_value(self, option_name: str) -> Union[str, int, float, bool, None]:
        """Retrieve the value of a specific Wayfire option."""
        return self.sock.get_option_value(option_name)  # pyright: ignore

    @handle_ipc_error
    def set_option_values(self, values: Dict[str, Any]) -> Any:
        """Set multiple Wayfire option values."""
        return self.sock.set_option_values(values)  # pyright: ignore

    @handle_ipc_error
    def tile_show_maximized(self, id, should_maximize):
        """Toggle tiling maximized state for a view."""
        self.sock.tile_show_maximized(id, should_maximize)  # pyright: ignore

    @handle_ipc_error
    def register_binding(self, binding, command, exec_always=True, mode="normal"):
        """Register a keyboard or mouse binding."""
        return self.sock.register_binding(  # pyright: ignore
            binding=binding,
            command=command,
            exec_always=True,
            mode=mode,
        )

    @handle_ipc_error
    def ping(self):
        """Send a ping to the compositor to check for a response."""
        return self.stipc.ping()  # pyright: ignore

    @handle_ipc_error
    def connect_client(self, path):
        """Connect to a client via a socket path."""
        return self.sock.connect_client(path)  # pyright: ignore

    @handle_ipc_error
    def get_cursor_position(self):
        """Get the current cursor position."""
        return self.sock.get_cursor_position()  # pyright: ignore

    @handle_ipc_error
    def clear_bindings(self):
        """Clear all registered bindings."""
        return self.sock.clear_bindings()  # pyright: ignore

    @handle_ipc_error
    def set_tiling_layout(self, wset, wsx, wsy, desired_layout):
        """Set the tiling layout for a specific workspace."""
        return self.sock.set_tiling_layout(wset, wsx, wsy, desired_layout)  # pyright: ignore

    @handle_ipc_error
    def get_tiling_layout(self, wset, wsx, wsy):
        """Get the current tiling layout of a workspace."""
        return self.sock.get_tiling_layout(wset, wsx, wsy)  # pyright: ignore

    @handle_ipc_error
    def set_tiling_maximized(self, view_id, should_maximize):
        """Set the maximized state of a tiled view."""
        self.sock.set_tiling_maximized(view_id, should_maximize)  # pyright: ignore

    @handle_ipc_error
    def _calculate_intersection_area(
        self, view: dict, ws_x: int, ws_y: int, monitor: dict
    ) -> int:
        """
        Calculate the intersection area between a view and a workspace.

        This method computes the area of intersection between a given view and a
        workspace based on their respective rectangles. It calculates the intersection
        by determining the overlapping coordinates and then computes the area.

        Args:
            view (dict): A dictionary representing the view with keys "x", "y",
                          "width", and "height" for its position and dimensions.
            ws_x (int): The x-coordinate of the workspace in grid units.
            ws_y (int): The y-coordinate of the workspace in grid units.
            monitor (dict): A dictionary representing the monitor with keys "width"
                            and "height" for its dimensions.

        Returns:
            int: The area of the intersection between the view and the workspace.
                  Returns 0 if there is no overlap.
        """
        # Calculate workspace rectangle
        workspace_start_x = ws_x * monitor["width"]
        workspace_start_y = ws_y * monitor["height"]
        workspace_end_x = workspace_start_x + monitor["width"]
        workspace_end_y = workspace_start_y + monitor["height"]
        # Calculate view rectangle
        view_start_x = view["x"]
        view_start_y = view["y"]
        view_end_x = view_start_x + view["width"]
        view_end_y = view_start_y + view["height"]
        # Calculate intersection coordinates
        inter_start_x = max(view_start_x, workspace_start_x)
        inter_start_y = max(view_start_y, workspace_start_y)
        inter_end_x = min(view_end_x, workspace_end_x)
        inter_end_y = min(view_end_y, workspace_end_y)
        # Calculate intersection area
        inter_width = max(0, inter_end_x - inter_start_x)
        inter_height = max(0, inter_end_y - inter_start_y)
        return inter_width * inter_height
