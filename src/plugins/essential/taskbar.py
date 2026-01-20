def get_plugin_metadata(panel_instance):
    """Retrieves metadata for the Taskbar plugin.

    Args:
        panel_instance: The instance of the panel.

    Returns:
        dict: A dictionary containing plugin identification and dependencies.
    """
    container = panel_instance.config_handler.get_root_setting(
        ["org.waypanel.plugin.taskbar", "panel", "name"], "bottom-panel-center"
    )
    about = """
            Provides a dynamic, scrollable taskbar for Wayfire/Waypanel desktops.
            It displays a button for every mapped (visible) toplevel window.
            """
    return {
        "id": "org.waypanel.plugin.taskbar",
        "name": "Taskbar",
        "version": "1.1.2",
        "enabled": True,
        "container": container,
        "deps": [
            "event_manager",
            "gestures_setup",
            "on_output_connect",
            "view_property_controller",
        ],
        "description": about,
    }


def get_plugin_class():
    """Returns the TaskbarPlugin class definition.

    Returns:
        type: The TaskbarPlugin class.
    """
    from src.plugins.core._base import BasePlugin
    from gi.repository import Gtk, GLib, Gdk

    class TaskbarPlugin(BasePlugin):
        """Plugin providing a window taskbar for the Wayfire compositor."""

        def __init__(self, panel_instance):
            """Initializes the TaskbarPlugin instance.

            Args:
                panel_instance: The main panel application instance.
            """
            super().__init__(panel_instance)
            self.last_toplevel_focused_view = None
            self._debounce_pending = False
            self._debounce_timer_id = None
            self._debounce_interval = 50
            self.allow_move_view_scroll = True
            self.is_scale_active = {}
            self.button_pool = []
            self.in_use_buttons = {}
            self.menu = None

            self._init_settings()
            self._subscribe_to_events()

            self.scrolled_window = Gtk.ScrolledWindow()
            self.run_in_thread(self._setup_taskbar)
            self.run_in_thread(self._initialize_button_pool, 10)
            self.main_widget = (self.scrolled_window, "append")

        def _init_settings(self):
            h = self.get_plugin_setting_add_hint
            self.icon_size = h(["layout", "icon_size"], 32, "Icon size.")
            self.spacing = h(["layout", "spacing"], 5, "Spacing.")
            self.show_label = h(["layout", "show_label"], True, "Show label.")
            self.max_title_length = h(
                ["layout", "max_title_length"], 25, "Title limit."
            )
            self.exclusive_zone = h(
                ["panel", "exclusive_zone"], True, "Exclusive zone."
            )
            self.panel_position = h(["panel", "position"], "bottom", "Placement.")
            self.vertical_layout_width = h(
                ["panel", "vertical_layout_width"], 150, "Vertical width."
            )
            self.layer_always_exclusive = h(
                ["panel", "layer_always_exclusive"], False, "Always exclusive."
            )
            self.panel_name = self.config_handler.get_root_setting(["panel", "name"])

        def _setup_taskbar(self) -> None:
            position = self.get_plugin_setting(["panel", "position"], "bottom")
            valid_panels = {
                "left": "left-panel-center",
                "right": "right-panel-center",
                "top": "top-panel-center",
                "bottom": "bottom-panel-center",
            }
            container = valid_panels[position]
            vertical_layout_width = self.get_plugin_setting(
                ["panel", "vertical_layout_width"], 150
            )
            orientation = Gtk.Orientation.VERTICAL
            if "left-panel" in container or "right-panel" in container:
                orientation = Gtk.Orientation.HORIZONTAL
            self.taskbar = Gtk.FlowBox()
            self.taskbar.set_column_spacing(self.spacing)
            self.taskbar.set_row_spacing(self.spacing)
            self.taskbar.set_selection_mode(Gtk.SelectionMode.NONE)
            self.taskbar.set_orientation(orientation)
            self.taskbar.set_max_children_per_line(1)
            self.flowbox_container = Gtk.Box(orientation=orientation)
            self.flowbox_container.set_hexpand(True)
            self.flowbox_container.set_halign(Gtk.Align.FILL)
            self.taskbar.set_halign(Gtk.Align.CENTER)
            self.taskbar.set_valign(Gtk.Align.CENTER)
            self.flowbox_container.append(self.taskbar)

            if orientation is Gtk.Orientation.HORIZONTAL:
                self.scrolled_window.set_hexpand(True)
                top_h = self._panel_instance.top_panel.get_height()
                bottom_h = self._panel_instance.top_panel.get_height()
                space = top_h + bottom_h + 100
                self.scrolled_window.set_size_request(
                    vertical_layout_width, self._panel_instance.monitor_height - space
                )
                self.scrolled_window.set_vexpand(True)
            else:
                self.scrolled_window.set_size_request(
                    self._panel_instance.monitor_width, 0
                )
                self.scrolled_window.set_vexpand(True)

            self.scrolled_window.set_halign(Gtk.Align.FILL)
            self.scrolled_window.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER
            )
            self.scrolled_window.set_child(self.flowbox_container)
            self.taskbar.add_css_class("taskbar")
            self.Taskbar()

        def _on_right_click(self, gesture, n_press, x, y):
            btn = gesture.get_widget()

            if self.menu:
                self.menu.unparent()
                self.menu = None

            self.menu = Gtk.Popover()
            self.menu.set_parent(btn)
            self.menu.set_has_arrow(True)
            self.menu.set_autohide(True)
            self.menu.active_view_id = btn.view_id

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

            view_data = self.ipc.get_view(btn.view_id)
            is_fullscreen = view_data.get("fullscreen", False)
            is_atop = view_data.get("always-on-top", False)
            is_sticky = view_data.get("sticky", False)

            actions = [
                (
                    "Disable Fullscreen" if is_fullscreen else "Enable Fullscreen",
                    self._on_menu_fullscreen_clicked,
                ),
                (
                    "Disable Always on Top" if is_atop else "Enable Always on Top",
                    self._on_menu_atop_clicked,
                ),
                (
                    "Disable Sticky" if is_sticky else "Enable Sticky",
                    self._on_menu_sticky_clicked,
                ),
                ("Move to Next Output", self._on_menu_move_next_clicked),
                ("Close Window", self._on_menu_close_clicked),
                ("Kill Process", self._on_menu_kill_clicked),
            ]

            for label, callback in actions:
                item = Gtk.Button(label=label, has_frame=False)
                item.set_halign(Gtk.Align.START)
                item.connect("clicked", callback)
                box.append(item)

            self.menu.set_child(box)

            rect = Gdk.Rectangle()
            rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
            self.menu.set_pointing_to(rect)
            self.menu.popup()

        def _on_menu_fullscreen_clicked(self, _):
            vid = self.menu.active_view_id
            current = self.ipc.get_view(vid)["fullscreen"]
            self.ipc.set_view_fullscreen(vid, not current)
            self.menu.popdown()

        def _on_menu_atop_clicked(self, _):
            vid = self.menu.active_view_id
            current = self.ipc.get_view(vid)["always-on-top"]
            self.ipc.set_view_always_on_top(vid, not current)
            self.menu.popdown()

        def _on_menu_sticky_clicked(self, _):
            vid = self.menu.active_view_id
            current = self.ipc.get_view(vid)["sticky"]
            self.ipc.set_view_sticky(vid, not current)
            self.menu.popdown()

        def _on_menu_move_next_clicked(self, _):
            self.wf_helper.send_view_to_output(self.menu.active_view_id, None, True)
            self.menu.popdown()

        def _on_menu_close_clicked(self, _):
            self.ipc.close_view(self.menu.active_view_id)
            self.menu.popdown()

        def _on_menu_kill_clicked(self, _):
            view = self.wf_helper.is_view_valid(self.menu.active_view_id)
            if view and view.get("pid"):
                self.run_cmd(f"kill -9 {view.get('pid')}")
            self.menu.popdown()

        def _subscribe_to_events(self):
            mgr = self.plugins.get("event_manager")
            if not mgr:
                return
            events = [
                "view-focused",
                "view-mapped",
                "view-unmapped",
                "view-app-id-changed",
                "view-title-changed",
            ]
            for ev in events:
                mgr.subscribe_to_event(ev, self.handle_view_event, "taskbar")
            mgr.subscribe_to_event(
                "plugin-activation-state-changed", self.handle_plugin_event, "taskbar"
            )

        def _initialize_button_pool(self, count: int) -> None:
            for _ in range(count):
                button = Gtk.Button()
                box = Gtk.Box(
                    orientation=Gtk.Orientation.HORIZONTAL, spacing=self.spacing
                )
                button.icon = Gtk.Image()
                button.label = Gtk.Label()
                button.icon.set_pixel_size(self.icon_size)
                box.append(button.icon)
                if self.show_label:
                    box.append(button.label)
                button.set_child(box)
                button.add_css_class("taskbar-button")

                right_click = Gtk.GestureClick(button=3)
                right_click.connect("pressed", self._on_right_click)
                button.add_controller(right_click)

                middle_click = Gtk.GestureClick(button=2)
                middle_click.connect("pressed", self._on_middle_click)
                button.add_controller(middle_click)

                button.set_visible(False)
                self.button_pool.append({"view_id": "available", "button": button})

        def _on_middle_click(self, gesture, n_press, x, y):
            btn = gesture.get_widget()
            if btn.view_id:
                self.ipc.close_view(btn.view_id)

        def Taskbar(self) -> None:
            if self._debounce_timer_id:
                GLib.source_remove(self._debounce_timer_id)
                self._debounce_timer_id = None
            self._debounce_pending = False

            views = [v for v in self.ipc.list_views() if self.is_valid_view(v)]
            current_ids = {v.get("id") for v in views}

            for vid in list(self.in_use_buttons.keys()):
                if vid not in current_ids:
                    self.remove_button(vid)

            for v in views:
                vid = v.get("id")
                if vid in self.in_use_buttons:
                    self.update_button(self.in_use_buttons[vid], v)
                else:
                    self.add_button_to_taskbar(v)

        def add_button_to_taskbar(self, view: dict):
            vid = view.get("id")
            button = None
            for item in self.button_pool:
                if item["view_id"] == "available":
                    button = item["button"]
                    item["view_id"] = vid
                    break
            if not button:
                return

            button.view_id = vid
            self.taskbar.append(button)
            self.in_use_buttons[vid] = button
            self.update_button(button, view)
            button.set_visible(True)

            button.connect("clicked", lambda *_: self.set_view_focus(view))

            motion = Gtk.EventControllerMotion()
            motion.connect(
                "enter",
                lambda *_: self.wf_helper.view_focus_effect_selected(view, 0.80, True),
            )
            motion.connect(
                "leave",
                lambda *_: self.wf_helper.view_focus_effect_selected(view, False),
            )
            button.add_controller(motion)
            self.gtk_helper.add_cursor_effect(button)

        def remove_button(self, view_id: str) -> None:
            btn = self.in_use_buttons.pop(view_id, None)
            if btn:
                self.taskbar.remove(btn)
                btn.set_visible(False)
                btn.view_id = None
                for item in self.button_pool:
                    if item["button"] == btn:
                        item["view_id"] = "available"
                        break

        def update_button(self, btn, view: dict) -> None:
            title = view.get("title", "")
            trunc = (
                (title[: self.max_title_length] + "...")
                if len(title) > self.max_title_length
                else title
            )
            btn.set_tooltip_text(title)
            btn.view_id = view.get("id")

            ico = self.ipc.get_view_property(btn.view_id, "icon")
            if not isinstance(ico, str):
                ico = self.gtk_helper.icon_exist(view.get("app-id"))

            btn.icon.set_from_icon_name(ico)
            btn.icon.set_pixel_size(self.icon_size)
            if self.show_label:
                btn.label.set_label(trunc)

        def on_view_focused(self, view: dict) -> None:
            if view and view.get("role") == "toplevel":
                fid = view.get("id")
                for vid, btn in self.in_use_buttons.items():
                    if vid == fid:
                        btn.add_css_class("focused")
                    else:
                        btn.remove_css_class("focused")

        def handle_view_event(self, msg: dict) -> None:
            ev, view = msg.get("event"), msg.get("view")
            if not view:
                return
            if ev == "view-unmapped":
                self.remove_button(view.get("id"))
            elif self.is_valid_view(view):
                if ev in ("view-title-changed", "view-app-id-changed"):
                    if view.get("id") in self.in_use_buttons:
                        self.update_button(
                            self.in_use_buttons.get(view.get("id")), view
                        )
                elif ev == "view-focused":
                    self.on_view_focused(view)
                elif ev == "view-mapped":
                    if not self._debounce_pending:
                        self._debounce_pending = True
                        self._debounce_timer_id = GLib.timeout_add(
                            self._debounce_interval, self.Taskbar
                        )

        def is_valid_view(self, view: dict) -> bool:
            if not view:
                return False
            return (
                view.get("layer") == "workspace"
                and view.get("role") == "toplevel"
                and view.get("mapped")
                and view.get("app-id") not in ("nil", None)
                and view.get("pid") != -1
            )

        def scale_toggle(self) -> None:
            if not self.layer_always_exclusive:
                self.ipc.scale_toggle()

        def set_view_focus(self, view: dict) -> None:
            try:
                vid = view.get("id")
                view = self.wf_helper.is_view_valid(vid)
                if not view:
                    return

                oid = view.get("output-id")
                if oid in self.is_scale_active and self.is_scale_active[oid]:
                    self.scale_toggle()

                self.ipc.go_workspace_set_focus(vid)
                self.ipc.center_cursor_on_view(vid)
                self.wf_helper.view_focus_indicator_effect(view)
            except Exception as e:
                self.logger.error(f"Error focusing view: {e}")

        def handle_plugin_event(self, msg: dict) -> bool:
            if (
                msg.get("event") == "plugin-activation-state-changed"
                and msg.get("plugin") == "scale"
            ):
                state = bool(msg.get("state"))
                self.is_scale_active[msg.get("output")] = state
                if not state and self.menu:
                    self.menu.popdown()
            return False

    return TaskbarPlugin
