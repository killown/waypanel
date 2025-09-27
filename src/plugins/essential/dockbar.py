import gi
import os
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from gi.repository import Gtk, Gdk, GLib  # pyright: ignore
from core._base import BasePlugin
from src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
ENABLE_PLUGIN = True
if not os.getenv("WAYFIRE_SOCKET"):
    ENABLE_PLUGIN = False
DEPS = ["event_manager", "gestures_setup"]


def get_plugin_placement(panel_instance):
    position = "left-panel-center"
    order = 5
    priority = 1
    return position, order, priority


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        dockbar = DockbarPlugin(panel_instance)
        return dockbar


class DockbarPlugin(BasePlugin):
    """
    A plugin that creates a configurable dockbar for launching applications.
    """

    class _ConfigReloadHandler(FileSystemEventHandler):
        """
        A file system event handler for reloading the configuration file.
        """

        def __init__(self, callback, watched_path):
            self.callback = callback
            self.last_update_time = 0.0
            self._watched = Path(watched_path).resolve()

        def on_modified(self, event):
            try:
                p = Path(event.src_path).resolve()
            except Exception:
                return
            if p == self._watched:
                now = time.time()
                if now - self.last_update_time > 1.0:
                    self.last_update_time = now
                    GLib.idle_add(self.callback)

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.dockbar = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)
        self.create_gesture = self.plugins["gestures_setup"].create_gesture
        self._subscribe_to_events()
        self.layer_state = False
        self.dockbar_content = self.get_panel()
        self._setup_dockbar()
        self._config_observer = None
        self._setup_file_watcher()

    def get_panel(self):
        """
        Retrieves the GTK panel object based on the configuration.
        """
        dockbar_config = self.config_handler.config_data.get("dockbar", {}).get("panel")
        if not dockbar_config:
            self.logger.warning(
                "Dockbar panel config is missing or invalid. Using default: left-panel."
            )
            return self.obj.left_panel
        position = dockbar_config.get("name").lower()
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
        """
        Checks if the 'scale' plugin is enabled in the Wayfire configuration.
        """
        plugins = self.ipc.get_option_value("core/plugins")["value"].split()
        return "scale" in plugins

    def _create_dockbar_button(self, app_name, app_data, class_style, use_label=False):
        """
        Creates and returns a Gtk.Button for a given app.
        """
        app_cmd = app_data["cmd"]
        icon_name = app_data["icon"]
        button = self.gtk_helper.create_button(
            self.gtk_helper.icon_exist(icon_name),
            app_cmd,
            class_style,
            use_label,
            self.on_left_click,
            app_cmd,
        )
        self.gtk_helper.add_cursor_effect(button)
        button.app_name = app_name
        button.app_config = app_data
        self.create_gesture(button, 2, lambda _, cmd=app_cmd: self.on_middle_click(cmd))
        self.create_gesture(button, 3, lambda _, cmd=app_cmd: self.on_right_click(cmd))
        drag_source = Gtk.DragSource.new()
        drag_source.set_actions(Gdk.DragAction.MOVE)
        drag_source.connect("prepare", self.on_drag_prepare)
        drag_source.connect("drag-begin", self.on_drag_begin)
        drag_source.connect("drag-end", self.on_drag_end)
        button.add_controller(drag_source)
        return button

    def _load_and_populate_dockbar(self, orientation, class_style, use_label=False):
        """
        Loads app list from config and populates the dockbar.
        """
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL
        self.dockbar.set_orientation(orientation)
        child = self.dockbar.get_first_child()
        while child:
            self.dockbar.remove(child)
            child = self.dockbar.get_first_child()
        config_data = self.config_handler.config_data.get("dockbar", {}).get("app", {})
        for app_name, app_data in config_data.items():
            button = self._create_dockbar_button(
                app_name, app_data, class_style, use_label
            )
            self.gtk_helper.update_widget_safely(self.dockbar.append, button)
        drop_target = Gtk.DropTarget.new(Gtk.Button, Gdk.DragAction.MOVE)
        drop_target.connect("drop", self.on_drop)
        self.dockbar.add_controller(drop_target)

    def on_drag_prepare(self, drag_source, x, y):
        """
        Prepares the content for a drag-and-drop operation.
        """
        return Gdk.ContentProvider.new_for_value(drag_source.get_widget())

    def on_drag_begin(self, drag_source, drag):
        """
        Starts a drag-and-drop operation.
        """
        dragged_widget = drag_source.get_widget()
        paintable = Gtk.WidgetPaintable.new(dragged_widget)
        drag_source.set_icon(paintable, 0, 0)
        dragged_widget.set_opacity(0.5)

    def on_drag_end(self, drag_source, drag, status):
        """
        Ends a drag-and-drop operation.
        """
        dragged_widget = drag_source.get_widget()
        dragged_widget.set_opacity(1.0)

    def on_drop(self, drop_target, value, x, y):
        """
        Handles the drop event to reorder the dockbar.
        """
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
        if new_position_child:
            parent_box.reorder_child_after(dragged_button, new_position_child)
        else:
            parent_box.reorder_child_after(dragged_button, parent_box.get_last_child())
        self.save_dockbar_order()
        return True

    def save_dockbar_order(self):
        """
        Saves the current order of the dockbar icons to the configuration file.
        """
        try:
            new_dockbar_config = {}
            child = self.dockbar.get_first_child()
            while child:
                if hasattr(child, "app_config"):
                    app_name = child.app_name  # pyright: ignore
                    new_dockbar_config[app_name] = child.app_config  # pyright: ignore
                child = child.get_next_sibling()
            self.config_handler.config_data.get("dockbar", {})["app"] = (
                new_dockbar_config
            )
            self.config_handler.save_config()
            self.logger.info("Dockbar order saved to config file.")
        except Exception as e:
            self.logger.error(f"Failed to save dockbar order: {e}")

    def on_left_click(self, cmd):
        """
        Handles a left-click event on a dockbar button.
        """
        self.cmd.run(cmd)
        self.ipc.scale_toggle()

    def on_right_click(self, cmd):
        """
        Handles a right-click event on a dockbar button.
        """
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
            self.wf_helper.move_cursor_middle_output(next_output["id"])
            self.ipc.click_button("S-BTN_LEFT", "full")
            self.cmd.run(cmd)
        except Exception as e:
            self.logger.error(f"Error while handling right-click action: {e}")

    def on_middle_click(self, cmd):
        """
        Handles a middle-click event on a dockbar button.
        """
        coordinates = self.wf_helper.find_empty_workspace()
        if coordinates:
            ws_x, ws_y = coordinates
            self.ipc.scale_toggle()
            self.ipc.set_workspace(ws_x, ws_y)
            self.cmd.run(cmd)
        else:
            self.cmd.run(cmd)

    def _setup_dockbar(self):
        """
        Configures the dockbar based on the loaded settings.
        """
        dockbar_data = self.config_handler.config_data.get("dockbar", {}).get(
            "panel", {}
        )
        orientation = dockbar_data.get("orientation", "v")
        class_style = dockbar_data.get("class_style", "dockbar-buttons")
        self._load_and_populate_dockbar(orientation, class_style)
        self.main_widget = (self.dockbar, "append")
        self.logger.info("Dockbar setup completed.")

    def _setup_file_watcher(self):
        """
        Sets up a file monitor to watch for changes in the waypanel.toml config file using watchdog.
        """
        config_file = self.config_handler.config_file
        try:
            event_handler = self._ConfigReloadHandler(
                self._on_config_changed, config_file
            )
            self._config_observer = Observer()
            self._config_observer.schedule(
                event_handler, str(Path(config_file).parent), recursive=False
            )
            self._config_observer.start()
            self.logger.info(
                f"Started monitoring config file with watchdog: {config_file}"
            )
        except Exception as e:
            self.logger.error(f"Failed to set up watchdog file watcher: {e}")

    def _on_config_changed(self):
        """
        Callback for file changes. Updates the dockbar on change.
        """
        self.logger.info("Config file changed. Updating dockbar by rebuilding.")
        self.config_handler.reload_config()
        self._setup_dockbar()

    def on_mouse_enter(self, controller, x, y):
        """
        Handles the mouse enter event to set the layer position.
        """
        if self.layer_state is False:
            set_layer_position_exclusive(self.dockbar_content, 64)
            self.layer_state = True

    def _subscribe_to_events(self):
        """
        Subscribes to events from the event manager.
        """
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
        """
        Creates a GTK button for a given application view.
        """
        title = self.gtk_helper.filter_utf_for_gtk(view.get("title", ""))
        wm_class = view.get("app-id", "")
        initial_title = title.split(" ")[0].lower()
        icon_name = self.gtk_helper.get_icon(wm_class, initial_title, title)
        button = Gtk.Button()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            self.gtk_helper.update_widget_safely(box.append, icon)
        label = Gtk.Label(label=title[:30])
        self.gtk_helper.update_widget_safely(box.append, label)
        button.set_child(box)
        button.add_css_class("dockbar-button")
        button.connect("clicked", lambda *_: self.wf_helper.focus_view_when_ready(view))
        return button

    def on_scale_desactivated(self):
        """
        Handles the deactivation of the 'scale' plugin.
        """
        self.gtk_helper.update_widget_safely(
            unset_layer_position_exclusive, self.dockbar_content
        )
        self.layer_state = False

    def handle_plugin_event(self, msg):
        """
        Handles events related to plugin activation state changes.
        """
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
