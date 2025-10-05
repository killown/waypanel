ENABLE_PLUGIN = False
DEPS = ["event_manager"]


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        tile = call_plugin_class()
        return tile(panel_instance)


def call_plugin_class():
    from src.plugins.core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event
    import os

    MAXIMIZE_BY_DEFAULT = True
    ADJUST_LAYOUT = True
    KEYBIND = "<alt> KEY_TAB"
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    TOGGLE_SCRIPT = os.path.join(SCRIPT_DIR, "_toggle_maximize.py")

    class Tile(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.logger.info("TileOnScalePlugin initialized.")
            self.workarea_width = self.ipc.get_focused_output()["workarea"]["width"]
            self.keybind = KEYBIND
            self.schedule_in_gtk_thread(self.register_binding_toggle_maximize)

        def register_binding_toggle_maximize(self):
            print(f"Registering binding: {self.keybind}")
            if self.wf_helper.is_keybind_used(self.keybind):
                self.keybind = "<super> KEY_SPACE"
            self.ipc.register_binding(
                binding=self.keybind,
                command=f"python3 {TOGGLE_SCRIPT}",
                exec_always=True,
                mode="normal",
            )

        def create_list_views(self, layout):
            if "view-id" in layout:
                return [
                    (
                        layout["view-id"],
                        layout["geometry"]["width"],
                        layout["geometry"]["height"],
                    )
                ]
            split = (
                "horizontal-split" if "horizontal-split" in layout else "vertical-split"
            )
            list = []
            for child in layout[split]:
                list += self.create_list_views(child)
            return list

        def adjust_tile_layout(self, view):
            output = self.ipc.get_output(view["output-id"])
            wset = output["wset-index"]
            wsx = output["workspace"]["x"]
            wsy = output["workspace"]["y"]
            layout = self.ipc.get_tiling_layout(wset, wsx, wsy)
            all_views = self.create_list_views(layout)
            desired_layout = {}
            if not all_views or (len(all_views) == 1 and all_views[0][0] == view["id"]):
                desired_layout = {
                    "vertical-split": [{"view-id": view["id"], "weight": 1}]
                }
                self.ipc.set_tiling_layout(wset, wsx, wsy, desired_layout)
                return
            main_view = all_views[0][0]
            weight_main = all_views[0][1]
            stack_views_old = [v for v in all_views[1:] if v[0] != view["id"]]
            weight_others = max(
                [v[1] for v in stack_views_old],
                default=output["workarea"]["width"] - weight_main,
            )
            if main_view == view["id"]:
                return
            if not stack_views_old:
                desired_layout = {
                    "vertical-split": [
                        {"view-id": main_view, "weight": 2},
                        {"view-id": view["id"], "weight": 1},
                    ]
                }
                self.ipc.set_tiling_layout(wset, wsx, wsy, desired_layout)
                return
            stack = [{"view-id": v[0], "weight": v[2]} for v in stack_views_old]
            stack += [
                {
                    "view-id": view["id"],
                    "weight": sum([v[2] for v in stack_views_old])
                    / len(stack_views_old),
                }
            ]
            desired_layout = {
                "vertical-split": [
                    {"weight": weight_main, "view-id": main_view},
                    {"weight": weight_others, "horizontal-split": stack},
                ]
            }
            self.ipc.set_tiling_layout(wset, wsx, wsy, desired_layout)

        @subscribe_to_event("plugin-activation-state-changed")
        def handle_scale_event(self, event_message):
            """Toggle tiling when Scale plugin is activated or deactivated."""
            try:
                plugin = event_message.get("plugin")
                state = event_message.get("state")
                if plugin != "scale":
                    return
                if state:
                    self.wf_helper.tile_maximize_all_from_active_workspace(True)
            except Exception as e:
                self.logger.error(f"Error handling scale activation: {e}")

        @subscribe_to_event("view-mapped")
        def handle_view_mapped(self, event_message):
            """Toggle tiling when a new view is created."""
            try:
                view = event_message.get("view")
                if view["type"] == "toplevel" and view["parent"] == -1:
                    if ADJUST_LAYOUT:
                        self.adjust_tile_layout(view)
                    self.ipc.set_tiling_maximized(view["id"], MAXIMIZE_BY_DEFAULT)
                    self.wf_helper.tile_maximize_all_from_active_workspace(
                        MAXIMIZE_BY_DEFAULT
                    )
            except Exception as e:
                self.logger.error(f"Error handling view mapped: {e}")

    return Tile
