import logging
from wayfire import WayfireSocket
from wayfire.core.template import get_msg_template
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.extra.stipc import Stipc
from typing import Optional

logger = logging.getLogger(__name__)


class IPC:
    """
    This module provides a Python interface to communicate with the Wayfire compositor
    via its IPC (Inter-Process Communication) socket.
    It encapsulates the functionality required to send commands, retrieve information,
    and manage various aspects of the compositor dynamically.
    """

    def __init__(self):
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.stipc = Stipc(self.sock)

    def get_view(self, id):
        """Get the view by the give id"""
        return self.sock.get_view(id)

    def set_focus(self, view_id: int):
        return self.sock.set_focus(view_id)

    def get_view_alpha(self, id):
        """Get the view alpha by the give id"""
        return self.sock.get_view_alpha(id)

    def set_view_alpha(self, id, alpha):
        """Set the view alpha by the give id"""
        return self.sock.set_view_alpha(id, alpha)

    def list_outputs(self):
        """List all outputs connected to Wayfire."""
        return self.sock.list_outputs()

    def get_focused_output(self):
        """Get the currently focused output."""
        return self.sock.get_focused_output()

    def get_focused_view(self):
        """Get the currently focused view."""
        return self.sock.get_focused_view()

    def list_views(self):
        """List all views managed by Wayfire."""
        return self.sock.list_views()

    def get_option_value(self, option_name):
        """Retrieve the value of a specific Wayfire option."""
        return self.sock.get_option_value(option_name)

    def set_option_values(self, values: dict):
        return self.sock.set_option_values(values)

    def watch(self):
        """Start watching for Wayfire events."""
        return self.sock.watch()

    def read_next_event(self):
        """Read the next event from Wayfire."""
        return self.sock.read_next_event()

    def is_connected(self):
        """Check if the Wayfire socket is connected."""
        return self.sock.is_connected()

    def close(self):
        """Close the Wayfire socket connection."""
        return self.sock.close()

    def scale_toggle(self):
        """Toggle the scale plugin."""
        return self.sock.scale_toggle()

    def set_workspace(self, x, y, view_id=None):
        """Set the workspace to the specified coordinates."""
        if view_id is None:
            return self.sock.set_workspace(x, y)
        else:
            return self.sock.set_workspace(x, y, view_id)

    def list_ids(self):
        return [view["id"] for view in self.sock.list_views()]

    def get_view_geometry(self, view_id: int):
        return self.sock.get_view(view_id)["geometry"]

    def configure_view(
        self, view_id: int, x: int, y: int, w: int, h: int, output_id=None
    ):
        return self.sock.configure_view(view_id, x, y, w, h, output_id)

    def go_workspace_set_focus(self, view_id: int) -> None:
        return self.wf_utils.go_workspace_set_focus(view_id)

    def center_cursor_on_view(self, view_id: int) -> None:
        return self.wf_utils.center_cursor_on_view(view_id)

    def move_cursor(self, x, y):
        """Move the cursor to the specified coordinates."""
        return self.stipc.move_cursor(x, y)

    def click_button(self, button, mode):
        return self.stipc.click_button(button, mode)

    def list_input_devices(self):
        """Retrieve a list of input devices managed by Wayfire."""
        return self.sock.list_input_devices()

    def configure_input_device(self, device_id, enable):
        """Enable or disable an input device."""
        return self.sock.configure_input_device(device_id, enable)

    def get_output(self, output_id):
        """Get detailed information about a specific output."""
        return self.sock.get_output(output_id)

    def get_current_workspace(self):
        """Get the current workspace coordinates."""
        return self.sock.get_focused_output().get("workspace", {})

    def get_active_workspace_number(self):
        """Retrieve the number of the currently active workspace."""
        workspace_info = self.sock.get_focused_output().get("workspace", {})
        return self.get_workspace_number(workspace_info["x"], workspace_info["y"])

    def get_workspace_number(self, workspace_x, workspace_y):
        """Convert workspace coordinates to a workspace number."""
        return self.wf_utils.get_workspace_number(workspace_x, workspace_y)

    def disable_input_device(self, device_id: int):
        """Disable an input device based on its ID."""
        return self.sock.configure_input_device(device_id, False)

    def enable_input_device(self, device_id: int):
        """Enable an input device based on its ID."""
        return self.sock.configure_input_device(device_id, True)

    def find_device_id(self, name_or_id_or_type: str):
        """Find the ID of an input device based on its name, ID, or type."""
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

    def assign_slot(self, view_id, slot):
        return self.sock.assign_slot(view_id, slot)

    def set_view_minimized(self, view_id, state):
        return self.sock.set_view_minimized(view_id, state)

    def set_view_maximized(self, view_id: int, state: bool):
        """Set the maximized state of a specific view."""
        return self.wf_utils.set_view_maximized(view_id)

    def set_view_fullscreen(self, view_id: int, state: bool):
        """Set the fullscreen state of a specific view."""
        return self.sock.set_view_fullscreen(view_id, state)

    def set_view_focus(self, view_id: int):
        """Set focus to a specific view."""
        return self.sock.set_focus(view_id)

    def close_view(self, view_id: int):
        """Close a specific view."""
        return self.sock.close_view(view_id)

    def toggle_showdesktop(self):
        """Toggle the "show desktop" mode."""
        return self.sock.toggle_showdesktop()

    def toggle_expo(self):
        """Toggle the Expo mode."""
        return self.sock.toggle_expo()

    def create_headless_output(self, width: int, height: int):
        """Create a headless output with the specified dimensions."""
        return self.sock.create_headless_output(width, height)

    def destroy_headless_output(
        self, output_name: Optional[str] = None, output_id: Optional[int] = None
    ):
        """Destroy a headless output by its name or ID."""
        return self.sock.destroy_headless_output(output_name, output_id)

    def cube_activate(self):
        """Activate the cube effect."""
        return self.sock.cube_activate()

    def cube_rotate_left(self):
        """Rotate the cube to the left."""
        return self.sock.cube_rotate_left()

    def cube_rotate_right(self):
        """Rotate the cube to the right."""
        return self.sock.cube_rotate_right()

    def scale_toggle_all(self):
        """Toggle the Scale mode for all workspaces."""
        return self.sock.scale_toggle_all()

    def create_wayland_output(self):
        """Create a Wayland output using Stipc."""
        return self.stipc.create_wayland_output()

    def destroy_wayland_output(self, output: str):
        """Destroy a Wayland output using Stipc."""
        return self.stipc.destroy_wayland_output(output)

    def get_output_id_by_name(self, output_name: str):
        for output in self.sock.list_outputs():
            if output["name"] == output_name:
                return output["id"]

    def get_output_geometry(self, output_id: int):
        return self.sock.get_output(output_id)["geometry"]

    def get_workspaces_without_views(self):
        return self.wf_utils.get_workspaces_without_views()

    def hide_view(self, view_id):
        message = get_msg_template("hide-view/hide")
        message["data"]["view-id"] = view_id
        self.sock.send_json(message)

    def unhide_view(self, view_id):
        message = get_msg_template("hide-view/unhide")
        message["data"]["view-id"] = view_id
        self.sock.send_json(message)

    def get_focused_output_views(self):
        return [
            view
            for view in self.sock.list_views()
            if view["output-id"] == self.get_focused_output_id()
        ]

    def get_focused_output_id(self):
        return self.sock.get_focused_output()["id"]

    def _calculate_intersection_area(
        self, view: dict, ws_x: int, ws_y: int, monitor: dict
    ):
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
