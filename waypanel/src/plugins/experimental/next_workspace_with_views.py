import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "right"
    order = 10
    return position, order


def initialize_plugin(panel_instance):
    """
    Initialize the plugin.
    Args:
        panel_instance: The main panel object from panel.py
    """
    if ENABLE_PLUGIN:
        plugin = GoNextWorkspaceWithViewsPlugin(panel_instance)
        plugin.setup_plugin()
        return plugin


class GoNextWorkspaceWithViewsPlugin:
    def __init__(self, panel_instance):
        """Initialize the plugin."""
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.gestures_setup_plugin = None

    def setup_plugin(self):
        """
        Set up the plugin.
        Check every second if the gestures_setup plugin is available.
        Once found, append the action to the right-click gesture in the full section.
        """
        GLib.timeout_add_seconds(1, self.check_for_gestures_setup)

    def check_for_gestures_setup(self):
        """
        Check if the gestures_setup plugin is loaded.
        If found, append the action for the full section.
        """
        if "gestures_setup" in self.obj.plugin_loader.plugins:
            self.gestures_setup_plugin = self.obj.plugin_loader.plugins[
                "gestures_setup"
            ]
            self.append_right_click_action()
            return False  # Stop the timeout loop
        return True  # Continue checking

    def append_right_click_action(self):
        """
        Append the 'go_next_workspace_with_views' action to the right-click gesture
        in the full section of the top panel.
        """
        # Define the callback name for the right-click gesture in the full section
        callback_name = "pos_full_right_click"

        # Append the action to the existing gesture callback
        self.gestures_setup_plugin.append_action(
            callback_name=callback_name, action=self.go_next_workspace_with_views
        )

    def get_workspaces_with_views(self):
        """
        Retrieve a list of workspaces that have views, ensuring the current workspace is always included.
        """
        focused_output = self.sock.get_focused_output()
        monitor = focused_output["geometry"]

        # Always include the current workspace
        current_ws_x = focused_output["workspace"]["x"]
        current_ws_y = focused_output["workspace"]["y"]
        ws_with_views = [{"x": current_ws_x, "y": current_ws_y}]

        views = self.wf_utils.get_focused_output_views()

        if views:
            # Filter views to include only valid toplevel views
            views = [
                view
                for view in views
                if view["role"] == "toplevel"
                and not view["minimized"]
                and view["app-id"] != "nil"
                and view["pid"] > 0
            ]

            if views:
                grid_width = focused_output["workspace"]["grid_width"]
                grid_height = focused_output["workspace"]["grid_height"]

                # Check each workspace for visible views
                for ws_x in range(grid_width):
                    for ws_y in range(grid_height):
                        if (ws_x, ws_y) != (
                            current_ws_x,
                            current_ws_y,
                        ):  # Avoid duplicate entry
                            for view in views:
                                intersection_area = (
                                    self.wf_utils._calculate_intersection_area(
                                        view["geometry"],
                                        ws_x - current_ws_x,
                                        ws_y - current_ws_y,
                                        monitor,
                                    )
                                )
                                if (
                                    intersection_area > 0
                                ):  # View is visible on this workspace
                                    ws_with_views.append({"x": ws_x, "y": ws_y})
                                    break  # No need to check other views for this workspace

        return ws_with_views

    def go_next_workspace_with_views(self):
        """
        Navigate to the next workspace with views, skipping empty workspaces.
        """
        workspaces_with_views = self.get_workspaces_with_views()
        if not workspaces_with_views:
            self.logger.info("No workspaces with views found.")
            return

        # Get the currently active workspace
        active_workspace = self.sock.get_focused_output()["workspace"]
        active_workspace_coords = (active_workspace["x"], active_workspace["y"])

        # Sort workspaces by row (y) and then column (x)
        workspaces_with_views = sorted(
            workspaces_with_views, key=lambda ws: (ws["y"], ws["x"])
        )

        # Find the index of the current workspace
        current_index = next(
            (
                i
                for i, ws in enumerate(workspaces_with_views)
                if (ws["x"], ws["y"]) == active_workspace_coords
            ),
            None,
        )

        if current_index is None:
            self.logger.info(
                "Current workspace not found in the list of workspaces with views."
            )
            return

        # Calculate the index of the next workspace (cyclically)
        next_index = (current_index + 1) % len(workspaces_with_views)
        next_workspace = workspaces_with_views[next_index]

        # Switch to the next workspace
        self.logger.info(
            f"Switching to workspace: x={next_workspace['x']}, y={next_workspace['y']}"
        )
        self.sock.set_workspace(next_workspace["x"], next_workspace["y"])
