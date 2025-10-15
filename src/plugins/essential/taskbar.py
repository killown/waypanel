def get_plugin_metadata(panel_instance):
    container = panel_instance.config_handler.get_root_setting(
        ["org.waypanel.plugin.taskbar", "panel", "name"], "bottom-panel-center"
    )
    about = """
            Provides a dynamic, scrollable taskbar for Wayfire/Waypanel desktops.
            It displays a button for every mapped (visible) toplevel window, allowing
            quick focus, movement, and management of running applications.
            """
    return {
        "id": "org.waypanel.plugin.taskbar",
        "name": "Taskbar",
        "version": "1.0.0",
        "enabled": True,
        "container": container,
        "deps": [
            "event_manager",
            "gestures_setup",
            "on_output_connect",
            "right_panel",
        ],
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

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
            self.scrolled_window = self.gtk.ScrolledWindow()
            self.button_pool = []
            self.in_use_buttons = {}
            self.debounce_interval = self.get_plugin_setting_add_hint(
                ["debounce", "interval_ms"],
                50,
                "The delay (in milliseconds) used to debounce view creation/destruction events, preventing rapid taskbar updates during busy periods.",
            )

            self.allow_move_view_scroll = self.get_plugin_setting_add_hint(
                ["actions", "allow_move_view_scroll"],
                True,
                "If True, scrolling up/down on a taskbar button moves the corresponding window to the next/previous output (monitor).",
            )

            self.icon_size = self.get_plugin_setting_add_hint(
                ["layout", "icon_size"],
                32,
                "The size (in pixels) for the application icons displayed on the taskbar buttons.",
            )

            self.spacing = self.get_plugin_setting_add_hint(
                ["layout", "spacing"],
                5,
                "Spacing (in pixels) between taskbar buttons.",
            )

            self.show_label = self.get_plugin_setting_add_hint(
                ["layout", "show_label"],
                True,
                "If True, display the window title next to the icon; otherwise, only show the icon.",
            )

            self.max_title_lenght = self.get_plugin_setting_add_hint(
                ["layout", "max_title_lenght"],
                25,
                "The maximum length (in characters) of the window title shown on the taskbar button label before being truncated with '...'.",
            )

            self.exclusive_zone = self.get_plugin_setting_add_hint(
                ["panel", "exclusive_zone"],
                True,
                "If True, the taskbar panel will claim an exclusive zone on the screen, ensuring windows do not maximize underneath it.",
            )

            self.panel_position = self.get_plugin_setting_add_hint(
                ["panel", "position"],
                "bottom",
                "Which panel position the taskbar should be attached to (top, bottom, left, right). This defines the orientation and placement.",
            )

            self.vertical_layout_width = self.get_plugin_setting_add_hint(
                ["panel", "vertical_layout_width"],
                150,
                "The maximum width (in pixels) to reserve for the taskbar when it is oriented vertically (i.e., on the left or right panel).",
            )

            self.layer_always_exclusive = self.get_plugin_setting_add_hint(
                ["panel", "layer_always_exclusive"],
                False,
                "If True, the panel's exclusive zone is always active, regardless of other plugins like 'scale'.",
            )
            self.panel_name = self.config_handler.get_root_setting(
                ["panel", "name"],
            )
            self.run_in_thread(self._setup_taskbar)
            self.run_in_thread(self._initialize_button_pool, 10)
            self.main_widget = (self.scrolled_window, "append")

        def set_layer_exclusive(self, exclusive) -> None:
            panel_attr_name = self.panel_name.replace("-", "_")
            panel_instance = getattr(self, panel_attr_name, None)
            if not panel_instance:
                self.logger.error(f"Panel '{self.panel_name}' not found.")
                return
            if exclusive:
                self.update_widget_safely(
                    self._set_layer_pos_exclusive,
                    panel_instance,
                    self.exclusive_zone,  # pyright: ignore
                )
            else:
                self.update_widget_safely(
                    self._unset_layer_pos_exclusive, panel_instance
                )

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
            orientation = self.gtk.Orientation.VERTICAL
            if "left-panel" in container or "right-panel" in container:
                orientation = self.gtk.Orientation.HORIZONTAL
            self.taskbar = self.gtk.FlowBox()
            self.taskbar.set_column_spacing(self.spacing)
            self.taskbar.set_row_spacing(self.spacing)
            self.taskbar.set_selection_mode(self.gtk.SelectionMode.NONE)
            self.taskbar.set_orientation(orientation)
            self.taskbar.set_max_children_per_line(1)
            self.flowbox_container = self.gtk.Box(orientation=orientation)
            self.flowbox_container.set_hexpand(True)
            self.flowbox_container.set_halign(self.gtk.Align.FILL)
            self.taskbar.set_halign(self.gtk.Align.CENTER)
            self.taskbar.set_valign(self.gtk.Align.CENTER)
            self.flowbox_container.append(self.taskbar)
            if orientation is self.gtk.Orientation.HORIZONTAL:
                self.scrolled_window.set_hexpand(True)
                top_height_space = self._panel_instance.top_panel.get_height()
                bottom_height_space = self._panel_instance.top_panel.get_height()
                space = top_height_space + bottom_height_space + 100
                self.scrolled_window.set_size_request(
                    vertical_layout_width, self._panel_instance.monitor_height - space
                )
                self.scrolled_window.set_vexpand(True)
            else:
                self.scrolled_window.set_size_request(
                    self._panel_instance.monitor_width, 0
                )
                self.scrolled_window.set_vexpand(True)
            self.scrolled_window.set_halign(self.gtk.Align.FILL)
            self.scrolled_window.set_policy(
                self.gtk.PolicyType.AUTOMATIC,
                self.gtk.PolicyType.NEVER,
            )
            self.scrolled_window.set_child(self.flowbox_container)
            self.logger.debug("Setting up bottom panel.")
            target = {
                "left": self.left_panel,
                "right": self.right_panel,
                "top": self.top_panel,
                "bottom": self.bottom_panel,
            }
            if self.layer_always_exclusive:
                self.layer_shell.set_layer(target[position], self.layer_shell.Layer.TOP)
                self.layer_shell.auto_exclusive_zone_enable(target[position])
                target[position].set_size_request(60, 0)
            output = self.os.getenv("waypanel")
            output_name = None
            output_id = None
            geometry = None
            if output:
                try:
                    output_data = self.json.loads(output)
                    output_name = output_data.get("output_name")
                    output_id = output_data.get("output_id")
                except (self.json.JSONDecodeError, TypeError):
                    self.logger.error("Could not parse waypanel environment variable.")
            if output_name:
                output_id = self.ipc.get_output_id_by_name(output_name)
                if output_id:
                    geometry = self.ipc.get_output_geometry(output_id)
            self.taskbar.add_css_class("taskbar")
            self.Taskbar()
            self.logger.info("Taskbar setup completed.")

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
                button = self.gtk.Button()
                box = self.gtk.Box(
                    orientation=self.gtk.Orientation.HORIZONTAL, spacing=self.spacing
                )
                button.icon = self.gtk.Image.new_from_icon_name("")  # pyright: ignore
                button.label = self.gtk.Label()  # pyright: ignore
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
            self.logger.debug("Taskbar reconciliation completed.")

        def Taskbar(self):
            self.logger.debug("Reconciling taskbar views.")
            if self._debounce_timer_id:
                self.glib.source_remove(self._debounce_timer_id)
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
            self.safe_remove_css_class(button, "focused")
            self.remove_gesture(button)
            for item in self.button_pool:
                if item["button"] == button:
                    item["view_id"] = "available"
                    self.logger.debug(f"Button for view ID {view_id} returned to pool.")
                    break
            self.taskbar.remove(button)
            self.taskbar.append(button)
            self.taskbar.queue_draw()
            self.taskbar.queue_resize()
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
                button = self.gtk.Button()
                box = self.gtk.Box(
                    orientation=self.gtk.Orientation.HORIZONTAL, spacing=self.spacing
                )
                button.icon = self.gtk.Image()  # pyright: ignore
                button.label = self.gtk.Label()  # pyright: ignore
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
            self.create_gesture(
                button.get_child(), 1, lambda *_: self.set_view_focus(view)
            )
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
            motion_controller = self.gtk.EventControllerMotion()
            motion_controller.connect("enter", lambda *_: self.on_button_hover(view))
            motion_controller.connect(
                "leave", lambda *_: self.on_button_hover_leave(view)
            )
            button.add_controller(motion_controller)
            self.gtk_helper.add_cursor_effect(button)
            return button

        def add_scroll_gesture(self, widget, view):
            scroll_controller = self.gtk.EventControllerScroll.new(
                self.gtk.EventControllerScrollFlags.VERTICAL
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
                        self.glib.timeout_add(300, self.set_allow_move_view_scroll)
                        output_from_right = self.wf_helper.get_output_from("right")
                        if view_output_id != output_from_right:
                            self.wf_helper.send_view_to_output(view_id, "right")
                            self.glib.timeout_add(
                                100, self.choose_fullscreen_state, view_id
                            )
                    elif dy < 0:
                        self.glib.timeout_add(300, self.set_allow_move_view_scroll)
                        output_from_left = self.wf_helper.get_output_from("left")
                        if view_output_id != output_from_left:
                            self.wf_helper.send_view_to_output(view_id, "left")
                            self.glib.timeout_add(
                                100, self.choose_fullscreen_state, view_id
                            )
            except Exception as e:
                self.glib.timeout_add(300, self.set_allow_move_view_scroll)
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
            if (
                wset_index_focused is None
                or wset_index_view is None
                or output_id is None
            ):
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
            self.glib.timeout_add(500, self.match_on_app_id_changed_view, view)

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
                    self.safe_remove_css_class(button, "focused")

        def _trigger_debounced_update(self):
            if not self._debounce_pending:
                self._debounce_pending = True
                self._debounce_timer_id = self.glib.timeout_add(
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

        def scale_toggle(self):
            if self.layer_always_exclusive is True:
                return
            self.ipc.scale_toggle()

        def handle_plugin_event(self, msg):
            if self.layer_always_exclusive is True:
                return

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
                if (
                    output_id in self.is_scale_active
                    and self.is_scale_active[output_id]
                ):
                    try:
                        self.scale_toggle()
                        self.logger.debug("Scale toggled off.")
                    except Exception as e:
                        self.logger.error(message=f"Failed to toggle scale. {e}")
                    finally:
                        self._focus_and_center_cursor(view_id)
                else:
                    self.scale_toggle()
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
            self.logger.debug(
                "Updating taskbar buttons during scale plugin activation."
            )
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

    return TaskbarPlugin
