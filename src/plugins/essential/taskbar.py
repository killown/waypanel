import os
import orjson as json
from gi.repository import Gtk, GLib  # pyright: ignore
from src.plugins.core._base import BasePlugin
from src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

ENABLE_PLUGIN = True
if not os.getenv("WAYFIRE_SOCKET"):
    ENABLE_PLUGIN = False
DEPS = [
    "event_manager",
    "gestures_setup",
    "on_output_connect",
    "bottom_panel",
    "top_panel",
    "left_panel",
    "right_panel",
]


def get_plugin_placement(panel_instance):
    position = "bottom-panel-center"
    order = 1
    priority = 10
    return position, order, priority


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return TaskbarPlugin(panel_instance)


class TaskbarPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self._subscribe_to_events()
        self.layer_always_exclusive = False
        self.last_toplevel_focused_view = None
        self._debounce_pending = False
        self._debounce_timer_id = None
        self._debounce_interval = 50
        self.allow_move_view_scroll = True
        self.is_scale_active = {}
        self.create_gesture = self.plugins["gestures_setup"].create_gesture
        self.remove_gesture = self.plugins["gestures_setup"].remove_gesture
        self.scrolled_window = Gtk.ScrolledWindow()
        self.button_pool = []
        self.in_use_buttons = {}
        self.icon_size = self.get_config(
            ["taskbar", "layout", "icon_size"],
        )
        self.spacing = self.get_config(
            ["taskbar", "layout", "spacing"],
        )
        self.show_label = self.get_config(
            ["taskbar", "layout", "show_label"],
        )
        self.max_title_lenght = self.get_config(
            ["taskbar", "layout", "max_title_lenght"],
        )
        self.exclusive_zone = self.get_config(
            ["taskbar", "panel", "exclusive_zone"],
        )
        self.panel_name = self.config_handler.check_and_get_config(
            ["taskbar", "panel", "name"],
        )
        self._setup_taskbar()
        self._initialize_button_pool(10)
        self.main_widget = (self.scrolled_window, "append")

    def set_layer_exclusive(self, exclusive) -> None:
        panel_attr_name = self.panel_name.replace("-", "_")
        panel_instance = getattr(self, panel_attr_name, None)
        if not panel_instance:
            self.logger.error(f"Panel '{self.panel_name}' not found.")
            return
        if exclusive:
            self.update_widget_safely(
                set_layer_position_exclusive, panel_instance, self.exclusive_zone
            )
        else:
            self.update_widget_safely(unset_layer_position_exclusive, panel_instance)

    def _setup_taskbar(self) -> None:
        self.taskbar = Gtk.FlowBox()
        self.taskbar.set_column_spacing(self.spacing)
        self.taskbar.set_row_spacing(self.spacing)
        self.taskbar.set_selection_mode(Gtk.SelectionMode.NONE)
        self.logger.debug("Setting up bottom panel.")
        if self.layer_always_exclusive:
            self.layer_shell.set_layer(self.bottom_panel, self.layer_shell.Layer.TOP)
            self.layer_shell.auto_exclusive_zone_enable(self.bottom_panel)
            self.bottom_panel.set_size_request(10, 10)
        output = os.getenv("waypanel")
        output_name = None
        output_id = None
        geometry = None
        if output:
            try:
                output_data = json.loads(output)
                output_name = output_data.get("output_name")
                output_id = output_data.get("output_id")
            except (json.JSONDecodeError, TypeError):
                self.logger.error("Could not parse waypanel environment variable.")
        if output_name:
            output_id = self.ipc.get_output_id_by_name(output_name)
            if output_id:
                geometry = self.ipc.get_output_geometry(output_id)
        if geometry:
            monitor_width = geometry["width"]
            self.scrolled_window.set_size_request(
                monitor_width, self.get_config(["taskbar", "panel", "exclusive_zone"])
            )
        self.taskbar.set_halign(Gtk.Align.CENTER)
        self.taskbar.set_valign(Gtk.Align.END)
        self.scrolled_window.set_child(self.taskbar)
        self.taskbar.add_css_class("taskbar")
        self.Taskbar()
        self.logger.info("Bottom panel setup completed.")

    def _subscribe_to_events(self) -> bool:
        if "event_manager" not in self.obj.plugin_loader.plugins:
            self.logger.debug("Taskbar is waiting for EventManagerPlugin.")
            return True
        else:
            event_manager = self.obj.plugin_loader.plugins["event_manager"]
            self.logger.info("Subscribing to events for Taskbar Plugin.")
            event_manager.subscribe_to_event(
                "view-focused",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-mapped",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-unmapped",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-app-id-changed",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "view-title-changed",
                self.handle_view_event,
                plugin_name="taskbar",
            )
            event_manager.subscribe_to_event(
                "plugin-activation-state-changed",
                self.handle_plugin_event,
                plugin_name="taskbar",
            )
        return False

    def _initialize_button_pool(self, count):
        for _ in range(count):
            button = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=self.spacing)
            button.icon = Gtk.Image.new_from_icon_name("")  # pyright: ignore
            button.label = Gtk.Label()  # pyright: ignore
            button.icon.set_pixel_size(self.icon_size)  # pyright: ignore
            box.append(button.icon)  # pyright: ignore
            if self.show_label:
                box.append(button.label)  # pyright: ignore
            button.set_child(box)
            button.add_css_class("taskbar-button")
            self.taskbar.append(button)
            button.set_visible(False)
            self.button_pool.append({"view_id": "available", "button": button})

    def _get_available_button(self):
        for item in self.button_pool:
            if item["view_id"] == "available":
                return item["button"], item
        return None, None

    def update_taskbar_button(self, view):
        view_id = view.get("id")
        if view_id not in self.in_use_buttons:
            self.logger.warning(
                f"Button for view ID {view_id} not found in in_use_buttons."
            )
            return
        button = self.in_use_buttons[view_id]
        app_id = view.get("app-id")
        title = view.get("title")
        initial_title = title.split()[0]
        if not title or not view_id:
            return
        icon_name = self.gtk_helper.get_icon(app_id, initial_title, title)
        if icon_name is None:
            return
        title = self.gtk_helper.filter_utf_for_gtk(view.get("title", ""))
        if not title:
            return
        words = title.split()
        shortened_words = [w[:50] + "…" if len(w) > 50 else w for w in words]
        title = " ".join(shortened_words)
        use_this_title = (
            title[:30] if len(title.split()[0]) <= 13 else title.split()[0][:30]
        )
        button.icon.set_from_icon_name(icon_name)
        button.icon.set_pixel_size(self.icon_size)
        if self.show_label:
            button.label.set_label(use_this_title)

    def refresh_all_buttons(self):
        """
        Forces a complete refresh and re-layout of the taskbar buttons.
        This method ensures that buttons from lower rows move up to fill empty space.
        """
        used_buttons = [item for item in self.button_pool]
        for b in used_buttons:
            if b["view_id"] != "available":
                button = b["button"]
                self.taskbar.remove(button)
                self.taskbar.append(button)
        for b in used_buttons:
            if b["view_id"] == "available":
                button = b["button"]
                self.taskbar.remove(button)
                self.taskbar.append(button)
        self.logger.info("Taskbar reconciliation completed.")

    def Taskbar(self):
        self.logger.debug("Reconciling taskbar views.")
        if self._debounce_timer_id:
            GLib.source_remove(self._debounce_timer_id)
            self._debounce_timer_id = None
        self._debounce_pending = False
        current_views = self.ipc.list_views()
        valid_views = [v for v in current_views if self.is_valid_view(v)]
        current_view_ids = {v.get("id") for v in valid_views}
        views_to_remove = list(self.in_use_buttons.keys() - current_view_ids)
        for view_id in views_to_remove:
            self.remove_button(view_id)
        for view in valid_views:
            view_id = view.get("id")
            if view_id in self.in_use_buttons:
                button = self.in_use_buttons[view_id]
                self.update_button(button, view)
                button.set_visible(True)
            else:
                self.add_button_to_taskbar(view)
        self.logger.info("Taskbar reconciliation completed.")

    def remove_button(self, view_id):
        if view_id not in self.in_use_buttons:
            return
        button = self.in_use_buttons.pop(view_id)
        button.set_visible(False)
        button.remove_css_class("focused")
        self.remove_gesture(button)
        for item in self.button_pool:
            if item["button"] == button:
                item["view_id"] = "available"
                self.logger.debug(f"Button for view ID {view_id} returned to pool.")
                break
        self.refresh_all_buttons()

    def update_button(self, button, view):
        title = view.get("title")
        initial_title = ""
        if title:
            initial_title = title[0]
        app_id = view.get("app-id")
        if len(title) > self.max_title_lenght:
            truncated_title = title[: self.max_title_lenght] + "..."
        else:
            truncated_title = title
        button.view_id = view.get("id")
        button.set_tooltip_text(title)
        icon_name = self.gtk_helper.get_icon(app_id, initial_title, title)
        button.icon.set_from_icon_name(icon_name)
        button.icon.set_pixel_size(self.icon_size)
        if self.show_label:
            button.label.set_label(truncated_title)

    def add_button_to_taskbar(self, view):
        view_id = view.get("id")
        button, pool_item = self._get_available_button()
        if not button:
            self.logger.info("Button pool exhausted, creating a new button.")
            button = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=self.spacing)
            button.icon = Gtk.Image()  # pyright: ignore
            button.label = Gtk.Label()  # pyright: ignore
            button.icon.set_pixel_size(self.icon_size)  # pyright: ignore
            box.append(button.icon)  # pyright: ignore
            if self.show_label:
                box.append(button.label)  # pyright: ignore
            button.set_child(box)
            button.add_css_class("taskbar-button")
            self.taskbar.append(button)
            self.button_pool.append({"view_id": view_id, "button": button})
        else:
            pool_item["view_id"] = view_id  # pyright: ignore
            self.logger.debug("Reusing a button from the pool.")
        self.in_use_buttons[view_id] = button
        self.update_button(button, view)
        button.set_visible(True)
        button.connect("clicked", lambda *_: self.set_view_focus(view))
        self.create_gesture(button.get_child(), 1, lambda *_: self.set_view_focus(view))
        self.create_gesture(
            button.get_child(), 2, lambda *_: self.ipc.close_view(view_id)
        )
        direction = None
        toggle_scale_off = True
        self.create_gesture(
            button.get_child(),
            3,
            lambda *_: self.wf_helper.send_view_to_output(
                view_id, direction, toggle_scale_off
            ),
        )
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("enter", lambda *_: self.on_button_hover(view))
        motion_controller.connect("leave", lambda *_: self.on_button_hover_leave(view))
        button.add_controller(motion_controller)
        self.gtk_helper.add_cursor_effect(button)
        return button

    def add_scroll_gesture(self, widget, view):
        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        scroll_controller.connect("scroll", self.on_scroll, view.get("id"))
        widget.add_controller(scroll_controller)

    def is_view_in_focused_output(self, view_id):
        view = self.ipc.get_view(view_id)
        if not view:
            return False
        view_output_id = view.get("output-id")
        focused_output = self.ipc.get_focused_output()
        if not focused_output:
            return False
        if view_output_id != focused_output.get("id"):
            return False
        else:
            return True

    def set_fullscreen_after_move(self, view_id):
        try:
            self.ipc.set_view_fullscreen(view_id, True)
            self.set_view_focus(view_id)
        except Exception as e:
            self.logger.error(f"Error setting fullscreen after move: {e}")

    def choose_fullscreen_state(self, view_id):
        if self.is_view_in_focused_output(view_id):
            self.ipc.set_view_fullscreen(view_id, False)
        else:
            self.ipc.set_view_fullscreen(view_id, True)
        return False

    def set_allow_move_view_scroll(self):
        self.allow_move_view_scroll = True
        return False

    def on_scroll(self, controller, dx, dy, view_id):
        try:
            view = self.ipc.get_view(view_id)
            if not view:
                return
            view_output_id = view.get("output-id")
            if not view_output_id:
                return
            if self.allow_move_view_scroll:
                self.allow_move_view_scroll = False
                if dy > 0:
                    GLib.timeout_add(300, self.set_allow_move_view_scroll)
                    output_from_right = self.wf_helper.get_output_from("right")
                    if view_output_id != output_from_right:
                        self.wf_helper.send_view_to_output(view_id, "right")
                        GLib.timeout_add(100, self.choose_fullscreen_state, view_id)
                elif dy < 0:
                    GLib.timeout_add(300, self.set_allow_move_view_scroll)
                    output_from_left = self.wf_helper.get_output_from("left")
                    if view_output_id != output_from_left:
                        self.wf_helper.send_view_to_output(view_id, "left")
                        GLib.timeout_add(100, self.choose_fullscreen_state, view_id)
        except Exception as e:
            GLib.timeout_add(300, self.set_allow_move_view_scroll)
            self.logger.error(
                message=f"Error handling scroll event {e}",
            )

    def send_view_to_empty_workspace(self, view_id):
        view = self.ipc.get_view(view_id)
        if not view:
            self.logger.error(
                f"Cannot send view {view_id} to empty workspace: view not found."
            )
            return
        empty_workspace = self.wf_helper.find_empty_workspace()
        geo = view.get("geometry")
        wset_index_focused = self.ipc.get_focused_output().get("wset-index")
        wset_index_view = view.get("wset-index")
        output_id = self.ipc.get_focused_output().get("id")
        if wset_index_focused is None or wset_index_view is None or output_id is None:
            self.logger.error(
                f"Cannot send view {view_id} to empty workspace: IPC data is incomplete."
            )
            return
        if wset_index_focused != wset_index_view:
            if geo:
                self.ipc.configure_view(
                    view_id,
                    geo.get("x", 0),
                    geo.get("y", 0),
                    geo.get("width", 0),
                    geo.get("height", 0),
                    output_id,
                )
                self.set_view_focus(view)
            else:
                self.logger.error(
                    f"Cannot send view {view_id} to empty workspace: geometry data is missing."
                )
        else:
            if empty_workspace:
                x, y = empty_workspace
                self.set_view_focus(view)
                self.ipc.set_workspace(x, y, view_id)

    def on_button_hover(self, view):
        self.wf_helper.view_focus_effect_selected(view, 0.80, True)

    def on_button_hover_leave(self, view):
        self.wf_helper.view_focus_effect_selected(view, False)

    def match_on_app_id_changed_view(self, unmapped_view):
        try:
            app_id = unmapped_view.get("app-id")
            mapped_view_list = [
                i
                for i in self.ipc.list_views()
                if app_id == i.get("app-id") and i.get("mapped") is True
            ]
            if mapped_view_list:
                mapped_view = mapped_view_list[0]
                self.update_taskbar_button(mapped_view)
            return False
        except IndexError as e:
            self.logger.error(
                message=f"IndexError handling 'view-app-id-changed' event: {e}",
            )
            return False
        except Exception as e:
            self.logger.error(
                message=f"General error handling 'view-app-id-changed' event: {e}",
            )
            return False

    def on_view_app_id_changed(self, view):
        GLib.timeout_add(500, self.match_on_app_id_changed_view, view)

    def on_view_focused(self, view):
        try:
            if view and view.get("role") == "toplevel":
                self.last_toplevel_focused_view = view
                view_id = view.get("id")
                if view_id:
                    self.update_focused_button_style(view_id)
        except Exception as e:
            self.logger.error(f"Error handling 'view-focused' event: {e}")

    def update_focused_button_style(self, focused_view_id):
        for view_id, button in self.in_use_buttons.items():
            if view_id == focused_view_id:
                button.add_css_class("focused")
            else:
                button.remove_css_class("focused")

    def _trigger_debounced_update(self):
        if not self._debounce_pending:
            self._debounce_pending = True
            self._debounce_timer_id = GLib.timeout_add(
                self._debounce_interval, self.Taskbar
            )

    def on_view_created(self, view):
        self._trigger_debounced_update()

    def on_view_destroyed(self, view):
        view_id = view.get("id")
        if view_id:
            self.remove_button(view_id)

    def on_title_changed(self, view):
        self.logger.debug(f"Title changed for view: {view}")
        self.update_taskbar_button(view)

    def handle_plugin_event(self, msg):
        prevent_infinite_loop_from_event_manager_idle_add = False
        if msg.get("event") == "plugin-activation-state-changed":
            if msg.get("state") is True:
                if msg.get("plugin") == "scale":
                    self.is_scale_active[msg.get("output")] = True
            if msg.get("state") is False:
                if msg.get("plugin") == "scale":
                    self.is_scale_active[msg.get("output")] = False
        return prevent_infinite_loop_from_event_manager_idle_add

    def set_view_focus(self, view):
        try:
            if not view:
                return
            view_id = view.get("id")
            if not view_id:
                self.logger.debug("Invalid view object: missing 'id'.")
                return
            view = self.wf_helper.is_view_valid(view_id)
            if not view:
                self.logger.debug(f"Invalid or non-existent view ID: {view_id}")
                return
            output_id = view.get("output-id")
            if not output_id:
                self.logger.debug(
                    f"Invalid view object for ID {view_id}: missing 'output-id'."
                )
                return
            try:
                viewgeo = self.ipc.get_view_geometry(view_id)
                if viewgeo and (
                    viewgeo.get("width", 0) < 100 or viewgeo.get("height", 0) < 100
                ):
                    self.ipc.configure_view(
                        view_id, viewgeo.get("x", 0), viewgeo.get("y", 0), 400, 400
                    )
                    self.logger.debug(f"Resized view ID {view_id} to 400x400.")
            except Exception as e:
                self.logger.error(
                    message=f"Failed to retrieve or resize geometry for view ID: {view_id} {e}",
                )
            if output_id in self.is_scale_active and self.is_scale_active[output_id]:
                try:
                    self.ipc.scale_toggle()
                    self.logger.debug("Scale toggled off.")
                except Exception as e:
                    self.logger.error(message=f"Failed to toggle scale. {e}")
                finally:
                    self._focus_and_center_cursor(view_id)
            else:
                self.ipc.scale_toggle()
                self._focus_and_center_cursor(view_id)
            self.wf_helper.view_focus_indicator_effect(view)
        except Exception as e:
            self.logger.error(
                message=f"Unexpected error while setting focus for view ID: {view['id']} {e}",
            )
            return True

    def _focus_and_center_cursor(self, view_id):
        try:
            self.ipc.go_workspace_set_focus(view_id)
            self.ipc.center_cursor_on_view(view_id)
        except Exception as e:
            self.logger.error(
                message=f"Failed to focus workspace or center cursor for view ID: {view_id} {e}",
            )

    def update_taskbar_on_scale(self) -> None:
        self.logger.debug("Updating taskbar buttons during scale plugin activation.")
        list_views = self.ipc.list_views()
        if list_views:
            for view in list_views:
                self.Taskbar()

    def on_scale_activated(self):
        focused_output = self.ipc.get_focused_output()
        focused_output_name = focused_output.get("name") if focused_output else None
        on_output = self.plugins.get("on_output_connect")
        if not on_output:
            return
        layer_set_on_output_name = on_output.current_output_name
        if not layer_set_on_output_name:
            layer_set_on_output_name = on_output.primary_output_name
        if (
            layer_set_on_output_name == focused_output_name
            and not self.layer_always_exclusive
        ):
            self.set_layer_exclusive(True)

    def on_scale_desactivated(self):
        if not self.layer_always_exclusive:
            self.set_layer_exclusive(False)

    def view_exist(self, view_id):
        try:
            view_id_list = {
                view.get("id")
                for view in self.ipc.list_views()
                if view and view.get("id")
            }
            if view_id not in view_id_list:
                return False
            view = self.ipc.get_view(view_id)
            if not self.is_valid_view(view):
                return False
            return True
        except Exception as e:
            self.logger.error(
                message=f"Error checking view existence {e}",
            )
            return False

    def is_valid_view(self, view):
        if not view:
            return False
        return (
            view.get("layer") == "workspace"
            and view.get("role") == "toplevel"
            and view.get("mapped") is True
            and view.get("app-id") not in ("nil", None)
            and view.get("pid") != -1
        )

    def handle_view_event(self, msg):
        event = msg.get("event")
        view = msg.get("view")
        if event == "view-app-id-changed":
            self.on_view_app_id_changed(view)
        if event == "view-wset-changed":
            return
        if event == "view-unmapped":
            if view:
                self.on_view_destroyed(view)
            return
        if not view:
            return
        if view.get("pid", -1) == -1:
            return
        if view.get("role") != "toplevel":
            return
        if view.get("app-id") in ("", "nil"):
            return
        if event == "output-gain-focus":
            return
        if event == "view-title-changed":
            self.on_title_changed(view)
        if event == "view-tiled" and view:
            pass
        if event == "view-focused":
            self.on_view_focused(view)
            return
        if event == "view-mapped":
            self.on_view_created(view)

    def about(self):
        """
        Taskbar Plugin
        ==============
        Purpose
        -------
        Provides a dynamic, scrollable taskbar for Wayfire/Waypanel desktops.
        It displays a button for every mapped (visible) toplevel window, allowing
        quick focus, movement, and management of running applications.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        1.  **Event-Driven Updates**: The plugin subscribes to events (like a window opening, closing, or gaining focus) from the system.
            When an event occurs, it triggers an update process.
        2.  **State Reconciliation**: On each update, the plugin fetches the current list of valid application windows.
            It then compares this list to its existing UI buttons.
        3.  **UI Management**: Based on the comparison, it adds new buttons for newly opened apps,
            removes buttons for closed apps, and updates the icon/title of existing buttons if the app's state changed
            (e.g., its title updated).
        4.  **User Interaction**: Each button is wired to perform actions (like focusing the corresponding app,
            closing it, or moving it to another screen) when clicked or scrolled on.
        5.  **Resource Efficiency**: To avoid constantly creating and destroying UI elements,
            it uses an object pool to reuse button widgets.
        In essence, it acts as a real-time bridge between the window manager's data and the user's visual interface.
        """
        return self.code_explanation.__doc__
