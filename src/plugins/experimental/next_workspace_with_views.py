def get_plugin_metadata(_):
    about = """
        A plugin that allows a user to cycle through workspaces that have
        active windows (views) on them, skipping any empty workspaces.
        """
    return {
        "id": "org.waypanel.plugin.next_workspace_with_views",
        "name": "Next Workspace",
        "version": "1.0.0",
        "enabled": True,
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class GoNextWorkspaceWithViewsPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            """Initialize the plugin."""
            self.gestures_setup_plugin = None

        def on_start(self):
            self.setup_plugin()

        def setup_plugin(self):
            """
            Set up the plugin.
            Check every second if the gestures_setup plugin is available.
            Once found, append the action to the right-click gesture in the full section.
            """
            self.glib.timeout_add_seconds(1, self.check_for_gestures_setup)

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
                return False
            return True

        def append_right_click_action(self):
            """
            Append the 'go_next_workspace_with_views' action to the right-click gesture
            in the full section of the top panel.
            """
            callback_name = "pos_full_right_click"
            self.gestures_setup_plugin.append_action(  # pyright: ignore
                callback_name=callback_name,
                action=self.go_next_workspace_with_views,
            )

        def get_workspaces_with_views(self):
            """
            Retrieve a list of workspaces that have views, ensuring the current workspace is always included.
            """
            focused_output = self.ipc.get_focused_output()
            monitor = focused_output["geometry"]
            current_ws_x = focused_output["workspace"]["x"]
            current_ws_y = focused_output["workspace"]["y"]
            ws_with_views = [{"x": current_ws_x, "y": current_ws_y}]
            views = self.ipc.get_focused_output_views()
            if views:
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
                    for ws_x in range(grid_width):
                        for ws_y in range(grid_height):
                            if (ws_x, ws_y) != (
                                current_ws_x,
                                current_ws_y,
                            ):
                                for view in views:
                                    intersection_area = (
                                        self.ipc._calculate_intersection_area(
                                            view["geometry"],
                                            ws_x - current_ws_x,
                                            ws_y - current_ws_y,
                                            monitor,
                                        )
                                    )
                                    if intersection_area > 0:
                                        ws_with_views.append({"x": ws_x, "y": ws_y})
                                        break
            return ws_with_views

        def go_next_workspace_with_views(self):
            """
            Navigate to the next workspace with views, skipping empty workspaces.
            """
            workspaces_with_views = self.get_workspaces_with_views()
            if not workspaces_with_views:
                self.logger.info("No workspaces with views found.")
                return
            active_workspace = self.ipc.get_focused_output()["workspace"]
            active_workspace_coords = (active_workspace["x"], active_workspace["y"])
            workspaces_with_views = sorted(
                workspaces_with_views, key=lambda ws: (ws["y"], ws["x"])
            )
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
            next_index = (current_index + 1) % len(workspaces_with_views)
            next_workspace = workspaces_with_views[next_index]
            self.logger.info(
                f"Switching to workspace: x={next_workspace['x']}, y={next_workspace['y']}"
            )
            self.ipc.set_workspace(next_workspace["x"], next_workspace["y"])

    return GoNextWorkspaceWithViewsPlugin
