import logging
import os
from wayfire.core.template import get_msg_template

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
    # Handle Optional[T] by extracting T
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


@apply_type_checked
class IPC:
    """
    This module provides a Python interface to communicate with the Wayfire compositor
    via its IPC (Inter-Process Communication) socket.
    It encapsulates the functionality required to send commands, retrieve information,
    and manage various aspects of the compositor dynamically.
    """

    def __init__(self):
        self.is_compositor_socket_ready = False
        if os.getenv("WAYFIRE_SOCKET"):
            from wayfire import WayfireSocket
            from wayfire.extra.ipc_utils import WayfireUtils
            from wayfire.extra.stipc import Stipc

            self.sock = WayfireSocket()
            self.wf_utils = WayfireUtils(self.sock)
            self.stipc = Stipc(self.sock)
            self.is_compositor_socket_ready = True
        if os.getenv("SWAYSOCK") and self.is_compositor_socket_ready is False:
            from pysway.ipc import SwayIPC

            self.sock = SwayIPC()

    def get_view(self, id: int) -> Dict[str, Any]:
        """Get the view by the given id"""
        return self.sock.get_view(id)

    def set_focus(self, view_id: int) -> Any:
        """Set focus to the specified view"""
        return self.sock.set_focus(view_id)

    def get_view_alpha(self, id: int) -> float:
        """Get the view alpha by the given id"""
        return self.sock.get_view_alpha(id)

    def set_view_alpha(self, id: int, alpha: float) -> Any:
        """Set the view alpha by the given id"""
        return self.sock.set_view_alpha(id, alpha)

    def list_outputs(self) -> List[Dict[str, Any]]:
        """List all outputs connected to Wayfire"""
        return self.sock.list_outputs()

    def get_focused_output(self) -> Dict[str, Any]:
        """Get the currently focused output"""
        return self.sock.get_focused_output()

    def get_focused_view(self) -> Dict[str, Any]:
        """Get the currently focused view"""
        return self.sock.get_focused_view()

    def list_views(self) -> List[Dict[str, Any]]:
        """List all views managed by Wayfire"""
        return self.sock.list_views()

    def get_option_value(self, option_name: str) -> Union[str, int, float, bool, None]:
        """Retrieve the value of a specific Wayfire option"""
        return self.sock.get_option_value(option_name)

    def set_option_values(self, values: Dict[str, Any]) -> Any:
        """Set multiple Wayfire option values"""
        return self.sock.set_option_values(values)

    def watch(self) -> Any:
        """Start watching for Wayfire events"""
        return self.sock.watch()

    def read_next_event(self) -> Dict[str, Any]:
        """Read the next event from Wayfire"""
        return self.sock.read_next_event()

    def is_connected(self) -> bool:
        """Check if the Wayfire socket is connected"""
        return self.sock.is_connected()

    def close(self) -> Any:
        """Close the Wayfire socket connection"""
        return self.sock.close()

    def scale_toggle(self) -> Any:
        """Toggle the scale plugin"""
        return self.sock.scale_toggle()

    def set_workspace(self, x: int, y: int, view_id: Optional[int] = None) -> Any:
        """Set the workspace to the specified coordinates"""
        if view_id is None:
            return self.sock.set_workspace(x, y)
        else:
            return self.sock.set_workspace(x, y, view_id)

    def list_ids(self) -> List[int]:
        """Get a list of all view IDs"""
        return [view["id"] for view in self.sock.list_views()]

    def get_view_geometry(self, view_id: int) -> Dict[str, int]:
        """Get the geometry of a specific view"""
        return self.sock.get_view(view_id)["geometry"]

    def configure_view(
        self,
        view_id: int,
        x: int,
        y: int,
        w: int,
        h: int,
        output_id: Optional[int] = None,
    ) -> Any:
        """Configure a view's position and size"""
        return self.sock.configure_view(view_id, x, y, w, h, output_id)

    def go_workspace_set_focus(self, view_id: int) -> None:
        """Set focus to a view and go to its workspace"""
        return self.wf_utils.go_workspace_set_focus(view_id)

    def center_cursor_on_view(self, view_id: int) -> None:
        """Center cursor on the specified view"""
        return self.wf_utils.center_cursor_on_view(view_id)

    def move_cursor(self, x: int, y: int) -> None:
        """Move the cursor to the specified coordinates"""
        return self.stipc.move_cursor(x, y)

    def click_button(self, button: str, mode: str) -> None:
        """Simulate mouse button click"""
        return self.stipc.click_button(button, mode)

    def list_input_devices(self) -> List[Dict[str, Any]]:
        """Retrieve a list of input devices managed by Wayfire"""
        return self.sock.list_input_devices()

    def configure_input_device(self, device_id: int, enable: bool) -> None:
        """Enable or disable an input device"""
        return self.sock.configure_input_device(device_id, enable)

    def get_output(self, output_id: int) -> Dict[str, Any]:
        """Get detailed information about a specific output"""
        return self.sock.get_output(output_id)

    def get_current_workspace(self) -> Dict[str, int]:
        """Get the current workspace coordinates"""
        return self.sock.get_focused_output().get("workspace", {})

    def get_active_workspace_number(self) -> int:
        """Retrieve the number of the currently active workspace"""
        workspace_info = self.sock.get_focused_output().get("workspace", {})
        return self.get_workspace_number(workspace_info["x"], workspace_info["y"])

    def get_workspace_number(self, workspace_x: int, workspace_y: int) -> int:
        """Convert workspace coordinates to a workspace number"""
        return self.wf_utils.get_workspace_number(workspace_x, workspace_y)  # pyright: ignore

    def disable_input_device(self, device_id: int) -> None:
        """Disable an input device based on its ID"""
        return self.sock.configure_input_device(device_id, False)

    def enable_input_device(self, device_id: int) -> None:
        """Enable an input device based on its ID"""
        return self.sock.configure_input_device(device_id, True)

    def find_device_id(self, name_or_id_or_type: str) -> int:
        """Find the ID of an input device based on its name, ID, or type"""
        devices = self.sock.list_input_devices()
        for dev in devices:
            if (
                dev["name"] == name_or_id_or_type
                or str(dev["id"]) == name_or_id_or_type
                or dev["type"] == name_or_id_or_type
            ):
                return dev["id"]
        raise ValueError(
            f"Device with name, ID, or type '{name_or_id_or_type}' not found."
        )

    def assign_slot(self, view_id: int, slot: str) -> None:
        """Assign a slot to a view"""
        return self.sock.assign_slot(view_id, slot)

    def set_view_minimized(self, view_id: int, state: bool) -> None:
        """Set the minimized state of a view"""
        return self.sock.set_view_minimized(view_id, state)

    def set_view_maximized(self, view_id: int, state: bool) -> None:
        """Set the maximized state of a specific view"""
        return self.wf_utils.set_view_maximized(view_id)

    def set_view_fullscreen(self, view_id: int, state: bool) -> None:
        """Set the fullscreen state of a specific view"""
        return self.sock.set_view_fullscreen(view_id, state)

    def set_view_focus(self, view_id: int) -> None:
        """Set focus to a specific view"""
        return self.sock.set_focus(view_id)

    def close_view(self, view_id: int) -> None:
        """Close a specific view"""
        return self.sock.close_view(view_id)

    def toggle_showdesktop(self) -> None:
        """Toggle the 'show desktop' mode"""
        return self.sock.toggle_showdesktop()

    def toggle_expo(self) -> None:
        """Toggle the Expo mode"""
        return self.sock.toggle_expo()

    def create_headless_output(self, width: int, height: int) -> Dict[str, Any]:
        """Create a headless output with the specified dimensions"""
        return self.sock.create_headless_output(width, height)

    def destroy_headless_output(
        self, output_name: Optional[str] = None, output_id: Optional[int] = None
    ) -> None:
        """Destroy a headless output by its name or ID"""
        return self.sock.destroy_headless_output(output_name, output_id)

    def cube_activate(self) -> bool:
        """Activate the cube effect"""
        return self.sock.cube_activate()

    def cube_rotate_left(self) -> bool:
        """Rotate the cube to the left"""
        return self.sock.cube_rotate_left()

    def cube_rotate_right(self) -> bool:
        """Rotate the cube to the right"""
        return self.sock.cube_rotate_right()

    def scale_toggle_all(self) -> bool:
        """Toggle the Scale mode for all workspaces"""
        return self.sock.scale_toggle_all()

    def create_wayland_output(self) -> None:
        """Create a Wayland output using Stipc"""
        return self.stipc.create_wayland_output()

    def destroy_wayland_output(self, output: str) -> None:
        """Destroy a Wayland output using Stipc"""
        return self.stipc.destroy_wayland_output(output)

    def get_output_id_by_name(self, output_name: str) -> Optional[int]:
        """Get output ID by its name"""
        for output in self.sock.list_outputs():
            if output["name"] == output_name:
                return output["id"]
        return None

    def get_output_geometry(self, output_id: int) -> Dict[str, int]:
        """Get geometry of a specific output"""
        return self.sock.get_output(output_id)["geometry"]

    def get_workspaces_without_views(self) -> List[List[int]]:
        """Get workspaces that don't contain any views.

        Returns:
            List[List[int]]: A list of workspace coordinates in [x, y] format
            Example: [[1, 0], [2, 0], [0, 1], ...]
        """
        return self.wf_utils.get_workspaces_without_views()  # pyright: ignore

    def get_workspace_from_view(self, view_id: int) -> Dict[str, int]:
        """Get workspace coordinates for a specific view"""
        return self.wf_utils.get_workspace_from_view(view_id)  # pyright: ignore

    def hide_view(self, view_id: int) -> None:
        """Hide a specific view"""
        message = get_msg_template("hide-view/hide")
        message["data"]["view-id"] = view_id
        self.sock.send_json(message)

    def unhide_view(self, view_id: int) -> None:
        """Unhide a specific view"""
        message = get_msg_template("hide-view/unhide")
        message["data"]["view-id"] = view_id
        self.sock.send_json(message)

    def get_focused_output_views(self) -> List[Dict[str, Any]]:
        """Get all views on the focused output"""
        return [
            view
            for view in self.sock.list_views()
            if view["output-id"] == self.get_focused_output_id()
        ]

    def get_focused_output_id(self) -> int:
        """Get ID of the currently focused output"""
        return self.sock.get_focused_output()["id"]

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
