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
        "version": "1.1.0",
        "enabled": True,
        "container": container,
        "deps": [
            "event_manager",
            "gestures_setup",
            "on_output_connect",
            "right_panel",
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

    class TaskbarPlugin(BasePlugin):
        """Plugin providing a window taskbar for the Wayfire compositor."""

        def __init__(self, panel_instance):
            """Initializes the TaskbarPlugin instance.

            Args:
                panel_instance: The main panel application instance.
            """
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
                "The delay (in ms) used to debounce view events.",
            )

            self.allow_move_view_scroll = self.get_plugin_setting_add_hint(
                ["actions", "allow_move_view_scroll"],
                True,
                "If True, scrolling on a button moves the corresponding window to another output.",
            )

            self.icon_size = self.get_plugin_setting_add_hint(
                ["layout", "icon_size"],
                32,
                "The size (in pixels) for the application icons.",
            )

            self.spacing = self.get_plugin_setting_add_hint(
                ["layout", "spacing"],
                5,
                "Spacing (in pixels) between taskbar buttons.",
            )

            self.show_label = self.get_plugin_setting_add_hint(
                ["layout", "show_label"],
                True,
                "If True, display the window title next to the icon.",
            )

            self.max_title_length = self.get_plugin_setting_add_hint(
                ["layout", "max_title_length"],
                25,
                "The maximum length of the window title before truncation.",
            )

            self.exclusive_zone = self.get_plugin_setting_add_hint(
                ["panel", "exclusive_zone"],
                True,
                "If True, the taskbar panel will claim an exclusive zone.",
            )

            self.panel_position = self.get_plugin_setting_add_hint(
                ["panel", "position"],
                "bottom",
                "Placement: top, bottom, left, right.",
            )

            self.vertical_layout_width = self.get_plugin_setting_add_hint(
                ["panel", "vertical_layout_width"],
                150,
                "The maximum width to reserve for the taskbar when vertical.",
            )

            self.layer_always_exclusive = self.get_plugin_setting_add_hint(
                ["panel", "layer_always_exclusive"],
                False,
                "If True, the panel's exclusive zone is always active.",
            )
            self.panel_name = self.config_handler.get_root_setting(
                ["panel", "name"],
            )
            self.run_in_thread(self._setup_taskbar)
            self.run_in_thread(self._initialize_button_pool, 10)
            self.main_widget = (self.scrolled_window, "append")

        def set_layer_exclusive(self, exclusive: bool) -> None:
            """Toggles the exclusive zone for the panel.

            Args:
                exclusive: Whether to enable or disable the exclusive zone.
            """
            panel_attr_name = self.panel_name.replace("-", "_")
            panel_instance = getattr(self, panel_attr_name, None)
            if not panel_instance:
                return
            if exclusive:
                self.update_widget_safely(
                    self._set_layer_pos_exclusive,
                    panel_instance,
                    self.exclusive_zone,
                )
            else:
                self.update_widget_safely(
                    self._unset_layer_pos_exclusive, panel_instance
                )

        def _setup_taskbar(self) -> None:
            """Configures the UI layout for the taskbar."""
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

            self.scrolled_window.set_halign(self.gtk.Align.FILL)
            self.scrolled_window.set_policy(
                self.gtk.PolicyType.AUTOMATIC,
                self.gtk.PolicyType.NEVER,
            )
            self.scrolled_window.set_child(self.flowbox_container)
            self.taskbar.add_css_class("taskbar")
            self.Taskbar()

        def _subscribe_to_events(self) -> bool:
            """Subscribes to EventManager events.

            Returns:
                bool: True if waiting for EventManager, False otherwise.
            """
            if "event_manager" not in self.obj.plugin_loader.plugins:
                return True
            else:
                event_manager = self.obj.plugin_loader.plugins["event_manager"]
                for event_name in [
                    "view-focused",
                    "view-mapped",
                    "view-unmapped",
                    "view-app-id-changed",
                    "view-title-changed",
                ]:
                    event_manager.subscribe_to_event(
                        event_name, self.handle_view_event, plugin_name="taskbar"
                    )
                event_manager.subscribe_to_event(
                    "plugin-activation-state-changed",
                    self.handle_plugin_event,
                    plugin_name="taskbar",
                )
            return False

        def _initialize_button_pool(self, count: int) -> None:
            """Pre-allocates buttons for the pool. They are NOT appended to the taskbar.

            Args:
                count: Number of buttons to pre-allocate.
            """
            for _ in range(count):
                button = self.gtk.Button()
                box = self.gtk.Box(
                    orientation=self.gtk.Orientation.HORIZONTAL, spacing=self.spacing
                )
                button.icon = self.gtk.Image.new_from_icon_name("")
                button.label = self.gtk.Label()
                button.icon.set_pixel_size(self.icon_size)
                box.append(button.icon)
                if self.show_label:
                    box.append(button.label)
                button.set_child(box)
                button.add_css_class("taskbar-button")
                button.set_visible(False)
                self.button_pool.append({"view_id": "available", "button": button})

        def _get_available_button(self) -> tuple:
            """Retrieves an unused button from the pool.

            Returns:
                tuple: (Gtk.Button, pool_item_dict) or (None, None).
            """
            for item in self.button_pool:
                if item["view_id"] == "available":
                    return item["button"], item
            return None, None

        def update_taskbar_button(self, view: dict) -> None:
            """Updates the properties of an existing taskbar button.

            Args:
                view: The Wayfire view object data.
            """
            view_id = view.get("id")
            if view_id not in self.in_use_buttons:
                return
            button = self.in_use_buttons[view_id]
            title = view.get("title", "")
            if not title or not view_id:
                return

            icon_name = self.ipc.get_view_property(view_id, "icon")
            if not isinstance(icon_name, str):
                icon_name = self.gtk_helper.icon_exist(view.get("app-id"))

            title = self.gtk_helper.filter_utf_for_gtk(title)
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

        def Taskbar(self) -> None:
            """Main reconciliation loop for updating the taskbar state."""
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
                    self.update_button(self.in_use_buttons[view_id], view)
                else:
                    self.add_button_to_taskbar(view)

        def remove_button(self, view_id: str) -> None:
            """Removes a button from the UI and returns it to the pool.

            Args:
                view_id: The unique identifier of the Wayfire view.
            """
            if view_id not in self.in_use_buttons:
                return

            button = self.in_use_buttons.pop(view_id)
            self.taskbar.remove(button)
            button.set_visible(False)
            self.safe_remove_css_class(button, "focused")
            self.remove_gesture(button)

            for item in self.button_pool:
                if item["button"] == button:
                    item["view_id"] = "available"
                    break

            self.taskbar.queue_draw()

        def update_button(self, button, view: dict) -> None:
            """Updates title, icon, and tooltip for a taskbar button.

            Args:
                button: The Gtk.Button widget.
                view: The view data dictionary.
            """
            title = view.get("title", "")
            truncated_title = (
                (title[: self.max_title_length] + "...")
                if len(title) > self.max_title_length
                else title
            )

            button.view_id = view.get("id")
            button.set_tooltip_text(title)

            icon_name = self.ipc.get_view_property(button.view_id, "icon")
            if not isinstance(icon_name, str):
                icon_name = self.gtk_helper.icon_exist(view.get("app-id"))

            button.icon.set_from_icon_name(icon_name)
            button.icon.set_pixel_size(self.icon_size)
            if self.show_label:
                button.label.set_label(truncated_title)

        def add_button_to_taskbar(self, view: dict):
            """Allocates a button and appends it to the taskbar.

            Args:
                view: The view data dictionary.

            Returns:
                Gtk.Button: The allocated button widget.
            """
            view_id = view.get("id")
            button, pool_item = self._get_available_button()

            if not button:
                button = self.gtk.Button()
                box = self.gtk.Box(
                    orientation=self.gtk.Orientation.HORIZONTAL, spacing=self.spacing
                )
                button.icon = self.gtk.Image()
                button.label = self.gtk.Label()
                button.icon.set_pixel_size(self.icon_size)
                box.append(button.icon)
                if self.show_label:
                    box.append(button.label)
                button.set_child(box)
                button.add_css_class("taskbar-button")
                self.button_pool.append({"view_id": view_id, "button": button})
            else:
                pool_item["view_id"] = view_id

            self.taskbar.append(button)
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

            self.create_gesture(
                button.get_child(),
                3,
                lambda *_: self.wf_helper.send_view_to_output(view_id, None, True),
            )

            motion = self.gtk.EventControllerMotion()
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

            return button

        def on_scroll(self, controller, dx: float, dy: float, view_id: str) -> None:
            """Handles scroll events to move windows between outputs.

            Args:
                controller: The scroll controller.
                dx: Horizontal scroll delta.
                dy: Vertical scroll delta.
                view_id: The view ID.
            """
            try:
                view = self.ipc.get_view(view_id)
                if not view or not self.allow_move_view_scroll:
                    return

                v_out_id = view.get("output-id")
                self.allow_move_view_scroll = False
                self.glib.timeout_add(
                    300, lambda: setattr(self, "allow_move_view_scroll", True) or False
                )

                direction = "right" if dy > 0 else "left"
                target_out = self.wf_helper.get_output_from(direction)

                if v_out_id != target_out:
                    self.wf_helper.send_view_to_output(view_id, direction)
                    self.glib.timeout_add(100, self._set_fs_state, view_id)
            except Exception:
                self.allow_move_view_scroll = True

        def _set_fs_state(self, view_id: str) -> bool:
            """Helper to toggle fullscreen based on output focus."""
            view = self.ipc.get_view(view_id)
            focused_out = self.ipc.get_focused_output()
            if view and focused_out:
                state = view.get("output-id") != focused_out.get("id")
                self.ipc.set_view_fullscreen(view_id, state)
            return False

        def on_view_focused(self, view: dict) -> None:
            """Updates taskbar button styling based on focus.

            Args:
                view: The focused view dictionary.
            """
            if view and view.get("role") == "toplevel":
                self.last_toplevel_focused_view = view
                fid = view.get("id")
                for vid, btn in self.in_use_buttons.items():
                    if vid == fid:
                        btn.add_css_class("focused")
                    else:
                        self.safe_remove_css_class(btn, "focused")

        def _trigger_debounced_update(self) -> None:
            """Triggers a debounced taskbar reconciliation."""
            if not self._debounce_pending:
                self._debounce_pending = True
                self._debounce_timer_id = self.glib.timeout_add(
                    self._debounce_interval, self.Taskbar
                )

        def scale_toggle(self) -> None:
            """Toggles the Wayfire scale plugin."""
            if not self.layer_always_exclusive:
                self.ipc.scale_toggle()

        def handle_plugin_event(self, msg: dict) -> bool:
            """Processes plugin activation state events.

            Args:
                msg: The event message dictionary.

            Returns:
                bool: Always False.
            """
            if self.layer_always_exclusive:
                return False
            if (
                msg.get("event") == "plugin-activation-state-changed"
                and msg.get("plugin") == "scale"
            ):
                self.is_scale_active[msg.get("output")] = bool(msg.get("state"))
            return False

        def set_view_focus(self, view: dict) -> None:
            """Focuses and centers the cursor on a specific view.

            Args:
                view: The view data dictionary.
            """
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

        def is_valid_view(self, view: dict) -> bool:
            """Determines if a view should be visible in the taskbar.

            Args:
                view: The view data dictionary.

            Returns:
                bool: True if the view is a valid toplevel window.
            """
            if not view:
                return False
            return (
                view.get("layer") == "workspace"
                and view.get("role") == "toplevel"
                and view.get("mapped") is True
                and view.get("app-id") not in ("nil", None)
                and view.get("pid") != -1
            )

        def handle_view_event(self, msg: dict) -> None:
            """Orchestrates view-related event handling.

            Args:
                msg: The event message dictionary.
            """
            event = msg.get("event")
            view = msg.get("view")
            if event == "view-app-id-changed":
                self.glib.timeout_add(
                    500, lambda: self.update_taskbar_button(view) or False
                )
            elif event == "view-unmapped":
                if view:
                    self.remove_button(view.get("id"))
            elif view and self.is_valid_view(view):
                if event == "view-title-changed":
                    self.update_taskbar_button(view)
                elif event == "view-focused":
                    self.on_view_focused(view)
                elif event == "view-mapped":
                    self._trigger_debounced_update()

    return TaskbarPlugin
