from gi.repository import Gtk, Gdk
import os
import toml
from core._base import BasePlugin
from src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

ENABLE_PLUGIN = True

if not os.getenv("WAYFIRE_SOCKET"):
    ENABLE_PLUGIN = False

DEPS = ["event_manager", "gestures_setup"]


def get_plugin_placement(panel_instance):
    position = "left-panel-center"
    dockbar_config = panel_instance.config.get("dockbar_panel", {})
    if dockbar_config:
        if "panel" in dockbar_config:
            position = dockbar_config["panel"]
            position = f"{position}"
    order = 5
    priority = 1
    return position, order, priority


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        dockbar = DockbarPlugin(panel_instance)
        return dockbar


class DockbarPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.create_gesture = self.plugins["gestures_setup"].create_gesture
        self._subscribe_to_events()
        self.layer_state = False
        self.taskbar_list = []
        self.dockbar_panel = self.get_panel()
        self.buttons_id = {}
        self.dockbar = None
        self._setup_dockbar()

    def get_panel(self):
        dockbar_config = self.obj.config.get("dockbar_panel", {})
        if not dockbar_config or "panel" not in dockbar_config:
            self.logger.warning(
                "Dockbar panel config is missing or invalid. Using default: left-panel."
            )
            return self.obj.left_panel

        position = dockbar_config["panel"].lower()
        valid_panels = {
            "left": self.obj.left_panel,
            "right": self.obj.right_panel,
            "top": self.obj.top_panel,
            "bottom": self.obj.bottom_panel,
        }

        panel_key = position.split("-")[0]

        if panel_key in valid_panels:
            return valid_panels[panel_key]
        else:
            self.logger.error(
                f"Invalid panel value: {position}. Defaulting to left-panel."
            )
            return self.obj.left_panel

    def is_scale_enabled(self):
        plugins = self.ipc.get_option_value("core/plugins")["value"].split()
        return "scale" in plugins

    def get_dockbar_position(self, panel):
        if panel == "left-panel":
            return self.obj.left_panel
        if panel == "right-panel":
            return self.obj.right_panel
        elif panel == "bottom-panel":
            return self.obj.bottom_panel
        elif panel == "top-panel":
            return self.obj.top_panel
        else:
            self.log_error(f"Invalid panel value: {panel}")

    def CreateFromAppList(
        self, config, orientation, class_style, callback=None, use_label=False
    ):
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        box = Gtk.Box(spacing=10, orientation=orientation)

        with open(config, "r") as f:
            config_data = toml.load(f)["dockbar"]

        for app_name, app_data in config_data.items():
            app_cmd = app_data["cmd"]
            icon_name = app_data["icon"]

            button = self.utils.create_button(
                self.utils.icon_exist(icon_name),
                app_cmd,
                class_style,
                use_label,
                self.on_left_click,
                app_cmd,
            )

            self.utils.add_cursor_effect(button)

            button.app_name = app_name
            button.app_config = app_data

            self.create_gesture(
                button, 2, lambda _, cmd=app_cmd: self.on_middle_click(cmd)
            )

            self.create_gesture(
                button, 3, lambda _, cmd=app_cmd: self.on_right_click(cmd)
            )

            # Add drag source functionality to each button
            drag_source = Gtk.DragSource.new()
            drag_source.set_actions(Gdk.DragAction.MOVE)
            drag_source.connect("prepare", self.on_drag_prepare)
            drag_source.connect("drag-begin", self.on_drag_begin)
            drag_source.connect("drag-end", self.on_drag_end)
            button.add_controller(drag_source)

            self.update_widget_safely(box.append, button)

        # Add drop target functionality to the box
        drop_target = Gtk.DropTarget.new(Gtk.Button, Gdk.DragAction.MOVE)
        drop_target.connect("drop", self.on_drop)
        box.add_controller(drop_target)

        return box

    def on_drag_prepare(self, drag_source, x, y):
        return Gdk.ContentProvider.new_for_value(drag_source.get_widget())

    def on_drag_begin(self, drag_source, drag):
        dragged_widget = drag_source.get_widget()
        paintable = Gtk.WidgetPaintable.new(dragged_widget)
        drag_source.set_icon(paintable, 0, 0)
        dragged_widget.set_opacity(0.5)

    def on_drag_end(self, drag_source, drag, status):
        dragged_widget = drag_source.get_widget()
        dragged_widget.set_opacity(1.0)

    def on_drop(self, drop_target, value, x, y):
        dragged_button = value
        parent_box = drop_target.get_widget()
        new_position_child = None
        is_vertical = parent_box.get_orientation() == Gtk.Orientation.VERTICAL

        if is_vertical:
            drop_coordinate = y
        else:
            drop_coordinate = x

        child = parent_box.get_first_child()
        while child:
            if child is dragged_button:
                child = child.get_next_sibling()
                continue

            child_allocation = child.get_allocation()
            if is_vertical:
                child_center = child_allocation.y + child_allocation.height / 2
            else:
                child_center = child_allocation.x + child_allocation.width / 2

            if drop_coordinate < child_center:
                new_position_child = child
                break

            child = child.get_next_sibling()

        # Reorder the button in the Gtk.Box
        if new_position_child:
            parent_box.reorder_child_after(dragged_button, new_position_child)
        else:
            parent_box.reorder_child_after(dragged_button, parent_box.get_last_child())

        self.save_dockbar_order()
        return True

    def save_dockbar_order(self):
        """Saves the current order of dockbar icons to the config file."""
        config_path = self.obj.waypanel_cfg
        try:
            with open(config_path, "r") as f:
                config_data = toml.load(f)

            new_dockbar_config = {}
            child = self.dockbar.get_first_child()
            while child:
                if hasattr(child, "app_config"):
                    app_name = child.app_name
                    new_dockbar_config[app_name] = child.app_config
                child = child.get_next_sibling()

            config_data["dockbar"] = new_dockbar_config

            with open(config_path, "w") as f:
                toml.dump(config_data, f)

            self.logger.info("Dockbar order saved to config file.")
        except Exception as e:
            self.logger.error(f"Failed to save dockbar order: {e}")

    def on_left_click(self, cmd):
        self.utils.run_cmd(cmd)
        self.ipc.scale_toggle()

    def on_right_click(self, cmd):
        try:
            outputs = self.ipc.list_outputs()
            focused_output = self.ipc.get_focused_output()
            current_index = next(
                (
                    i
                    for i, output in enumerate(outputs)
                    if output["id"] == focused_output["id"]
                ),
                -1,
            )

            next_index = (current_index + 1) % len(outputs)
            next_output = outputs[next_index]
            output_geometry = next_output["geometry"]
            cursor_x = output_geometry["x"] + output_geometry["width"] // 2
            cursor_y = output_geometry["y"] + output_geometry["height"] // 2

            self.ipc.move_cursor(cursor_x, cursor_y)
            self.ipc.click_button("S-BTN_LEFT", "full")
            self.utils.run_cmd(cmd)

        except Exception as e:
            self.log_error(f"Error while handling right-click action: {e}")

    def on_middle_click(self, cmd):
        coordinates = self.utils.find_empty_workspace()
        if coordinates:
            ws_x, ws_y = coordinates
            self.ipc.scale_toggle()
            self.ipc.set_workspace(ws_x, ws_y)
            self.utils.run_cmd(cmd)
        else:
            self.utils.run_cmd(cmd)

    def _setup_dockbar(self):
        dockbar_toml = self.config.get("dockbar", {})
        orientation = dockbar_toml.get("orientation", "v")
        class_style = dockbar_toml.get("class_style", "dockbar-buttons")

        self.dockbar = self.CreateFromAppList(
            self.obj.waypanel_cfg, orientation, class_style
        )
        self.main_widget = (self.dockbar, "append")
        self.logger.info("Dockbar setup completed.")

    def on_mouse_enter(self, controller, x, y):
        if self.layer_state is False:
            set_layer_position_exclusive(self.dockbar_panel, 64)
            self.layer_state = True

    def _subscribe_to_events(self):
        if "event_manager" not in self.plugins:
            self.logger.info("dockbar is waiting for event manager")
            return True
        else:
            event_manager = self.plugins["event_manager"]
            self.logger.info("Subscribing to events for Dockbar Plugin.")
            event_manager.subscribe_to_event(
                "plugin-activation-state-changed",
                self.handle_plugin_event,
                plugin_name="dockbar",
            )

    def create_dockbar_button(self, view):
        title = self.utils.filter_utf_for_gtk(view.get("title", ""))
        wm_class = view.get("app-id", "")
        initial_title = title.split(" ")[0].lower()
        icon_name = self.utils.get_icon(wm_class, initial_title, title)

        button = Gtk.Button()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            self.update_widget_safely(box.append, icon)

        label = Gtk.Label(label=title[:30])
        self.update_widget_safely(box.append, label)

        button.set_child(box)
        button.add_css_class("dockbar-button")

        button.connect("clicked", lambda *_: self.utils.focus_view_when_ready(view))
        return button

    def on_scale_desactivated(self):
        self.update_widget_safely(unset_layer_position_exclusive, self.dockbar_panel)
        self.layer_state = False

    def handle_plugin_event(self, msg):
        prevent_infinite_loop_from_event_manager_idle_add = False
        if msg["event"] == "plugin-activation-state-changed":
            if msg["state"] is True:
                if msg["plugin"] == "scale":
                    pass
            if msg["state"] is False:
                if msg["plugin"] == "scale":
                    pass
        return prevent_infinite_loop_from_event_manager_idle_add

    def about(self):
        """
        Dockbar Plugin — Launch apps.

        • Configurable via TOML (waypanel.toml).
        • Supports left/right/top/bottom panels.
        • Left-click: Launch app + toggle scale.
        • Middle-click: Launch on empty workspace.
        • Right-click: Move cursor to next output & launch.
        • Integrates with gestures and event_manager.
        • Drag-and-drop to reorder icons, saving the new order.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin implements a static application launcher dockbar, dynamically
        built from a user-defined configuration file.

        Its core logic follows these principles:

        1.  **Configuration-Driven UI**: On startup, it reads a TOML config file
            to determine which applications to display, their icons, and launch commands.
            It then generates a row or column of buttons accordingly.

        2.  **Panel-Aware Placement**: It respects the user’s chosen panel position
            (left, right, top, bottom) by reading the config and attaching itself
            to the corresponding panel container.

        3.  **Gesture-Enhanced Interaction**: Each button is wired to respond to
            left, middle, and right mouse clicks, triggering different behaviors:
            - Left: Launch app and toggle the scale plugin.
            - Middle: Find an empty workspace, switch to it, then launch.
            - Right: Move the cursor to the next monitor and launch there.
            - Drag-and-drop: Dragging an icon and dropping it changes its position
              in the dockbar and saves the new order to the config file.

        4.  **Event-Driven Adaptation**: It listens for system events (like plugin
            activation/deactivation) to potentially adjust its behavior or layer
            properties in the future (e.g., hiding/showing when scale is active).

        In essence, it transforms a static config into an interactive, multi-output
        application launcher dock.
        """
        return self.code_explanation.__doc__
