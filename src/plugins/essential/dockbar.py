def get_plugin_metadata(panel_instance):
    container = panel_instance.config_handler.get_root_setting(
        ["org.waypanel.plugin.dockbar", "panel", "position"], "left"
    )
    valid_panels = {
        "left": "left-panel-center",
        "right": "right-panel-center",
        "top": "top-panel-center",
        "bottom": "bottom-panel-center",
    }
    about = "A plugin that creates a configurable dockbar for launching applications."
    return {
        "id": "org.waypanel.plugin.dockbar",
        "name": "Dockbar",
        "version": "1.0.1",
        "enabled": True,
        "container": valid_panels[container],
        "priority": 1,
        "deps": ["event_manager", "gestures_setup", "left_panel"],
        "description": about,
    }


def get_plugin_class():
    from core._base import BasePlugin

    class DockbarPlugin(BasePlugin):
        from gi.repository import Gio  # pyright: ignore

        """
        A plugin that creates a configurable dockbar for launching applications.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.add_hint(
                [
                    "Configuration for the Dockbar appearance, placement, and mouse click behavior."
                ],
                None,
            )
            self.panel_position = self.get_plugin_setting_add_hint(
                ["panel", "position"],
                "left",
                "Which panel container the dockbar should be placed on (left, right, top, bottom).",
            )
            self.spacing = self.get_plugin_setting_add_hint(
                ["spacing"],
                10,
                "Spacing in pixels between the application icons in the dockbar.",
            )
            self.class_style = self.get_plugin_setting_add_hint(
                ["panel", "class_style"],
                "dockbar-buttons",
                "CSS class applied to each application button for custom styling.",
            )
            self.left_click_toggles_scale = self.get_plugin_setting_add_hint(
                ["actions", "left_click_toggles_scale"],
                True,
                "If True, a left-click on a running app toggles Wayfire's 'scale' plugin.",
            )
            self.middle_click_to_empty_workspace = self.get_plugin_setting_add_hint(
                ["actions", "middle_click_to_empty_workspace"],
                True,
                "If True, a middle-click attempts to launch on the nearest empty workspace.",
            )
            self.right_click_to_next_output = self.get_plugin_setting_add_hint(
                ["actions", "right_click_to_next_output"],
                True,
                "If True, a right-click launches the application on the next output.",
            )
            self.panel_orientation = self.get_plugin_setting_add_hint(
                ["panel", "orientation"],
                "v",
                "Overrides the automatically detected orientation (h/v).",
            )
            self.layer_always_exclusive = self.get_plugin_setting_add_hint(
                ["panel", "layer_always_exclusive"],
                False,
                "If True, the dockbar panel will be set to Layer.TOP and reserve space.",
            )
            self.dockbar = self.gtk.Box(
                spacing=self.spacing, orientation=self.get_orientation()
            )
            self.create_gesture = self.plugins["gestures_setup"].create_gesture
            self._subscribe_to_events()
            self.layer_state = False
            self.dockbar_content = self.get_panel()
            self._setup_dockbar()
            self.gio_config_file = None
            self._config_observer = None
            self._last_config_mod_time = 0.0
            self._setup_file_watcher()
            self._setup_dock_context_menu()

        def _on_gio_config_file_changed(
            self,
            monitor: Gio.FileMonitor,
            file: Gio.File,
            other_file: Gio.File,
            event_type: Gio.FileMonitorEvent,
        ) -> None:
            config_file = self.config_handler.config_file
            if event_type in (
                self.gio.FileMonitorEvent.CHANGES_DONE_HINT,
                self.gio.FileMonitorEvent.MOVED,
                self.gio.FileMonitorEvent.CHANGED,
            ):
                try:
                    current_mod_time = self.os.path.getmtime(config_file)
                    if current_mod_time > self._last_config_mod_time + 0.1:
                        self._last_config_mod_time = current_mod_time
                        self.glib.idle_add(self._on_config_changed)
                except (FileNotFoundError, Exception):
                    pass

        def _get_top_level_panel_widget(self):
            position = self.panel_position.lower().split("-")[0]
            top_level_panels = {
                "left": self._panel_instance.left_panel,
                "right": self._panel_instance.right_panel,
                "top": self._panel_instance.top_panel,
                "bottom": self._panel_instance.bottom_panel,
            }
            return top_level_panels.get(position)

        def get_panel(self):
            position = self.panel_position.lower()
            valid_panels = {
                "left": self._panel_instance.left_panel_box_center,
                "right": self._panel_instance.right_panel_box_center,
                "top": self._panel_instance.top_panel_box_center,
                "bottom": self._panel_instance.bottom_panel_box_center,
            }
            panel_key = position.split("-")[0]
            return valid_panels.get(
                panel_key, self._panel_instance.left_panel_box_center
            )

        def is_scale_enabled(self):
            plugins = self.ipc.get_option_value("core/plugins")["value"].split()
            return "scale" in plugins

        def _remove_from_dockbar(self, button):
            self.dockbar.remove(button)
            self.save_dockbar_order()

        def _move_item(self, button, step):
            children = []
            child = self.dockbar.get_first_child()
            while child:
                children.append(child)
                child = child.get_next_sibling()

            try:
                idx = children.index(button)
                new_idx = idx + step
                if 0 <= new_idx < len(children):
                    target = (
                        children[new_idx]
                        if step > 0
                        else (children[new_idx - 1] if new_idx > 0 else None)
                    )
                    self.dockbar.reorder_child_after(button, target)
                    self.save_dockbar_order()
            except (ValueError, IndexError):
                pass

        def _edit_item(self, app_name=None, app_config=None):
            is_new = app_name is None

            def build_dialog():
                dialog = self.gtk.Dialog(
                    title="Edit Launcher" if not is_new else "Add Launcher"
                )
                # Ensure the dialog is treated as a separate window for Wayland
                dialog.set_modal(True)

                content = dialog.get_content_area()
                content.set_margin_end(12)
                content.set_spacing(10)

                name_entry = self.gtk.Entry(
                    text=app_name or "New App", placeholder_text="ID (e.g. firefox)"
                )
                cmd_entry = self.gtk.Entry(
                    text=app_config["cmd"] if app_config else "",
                    placeholder_text="Command",
                )
                icon_entry = self.gtk.Entry(
                    text=app_config["icon"] if app_config else "",
                    placeholder_text="Icon Name",
                )

                for label_text, entry in [
                    ("ID:", name_entry),
                    ("Command:", cmd_entry),
                    ("Icon:", icon_entry),
                ]:
                    box = self.gtk.Box(
                        orientation=self.gtk.Orientation.VERTICAL, spacing=4
                    )
                    box.append(self.gtk.Label(label=label_text, xalign=0))
                    box.append(entry)
                    content.append(box)

                dialog.add_button("Cancel", self.gtk.ResponseType.CANCEL)
                dialog.add_button("Save", self.gtk.ResponseType.OK)

                def on_response(d, response_id):
                    if response_id == self.gtk.ResponseType.OK:
                        new_name = name_entry.get_text()
                        new_config = {
                            "id": new_name,
                            "cmd": cmd_entry.get_text(),
                            "icon": icon_entry.get_text(),
                        }

                        current_apps = self.get_plugin_setting(["app"], [])

                        if not is_new:
                            for i, app in enumerate(current_apps):
                                if app.get("id") == app_name:
                                    current_apps[i] = new_config
                                    break
                        else:
                            current_apps.append(new_config)

                        self.config_handler.set_root_setting(
                            [str(self.plugin_id), "app"], current_apps
                        )
                        self.glib.idle_add(self._on_config_changed)
                    d.destroy()

                dialog.connect("response", on_response)
                dialog.present()
                return False

            self.glib.idle_add(build_dialog)

        def _add_separator(self):
            current_apps = self.get_plugin_setting(["app"], {})
            sep_id = f"sep_{len(current_apps)}"
            current_apps[sep_id] = {"type": "separator"}
            self.config_handler.set_root_setting([self.plugin_id, "app"], current_apps)
            self.glib.idle_add(self._on_config_changed)

        def _setup_dock_context_menu(self):
            menu_model = self.gio.Menu.new()
            menu_model.append("Add New Launcher", "dock_global.add")
            menu_model.append("Add Separator", "dock_global.separator")

            popover = self.gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(self.dockbar)
            popover.set_has_arrow(False)

            action_group = self.gio.SimpleActionGroup.new()
            add_action = self.gio.SimpleAction.new("add", None)
            add_action.connect("activate", lambda *_: self._edit_item())
            sep_action = self.gio.SimpleAction.new("separator", None)
            sep_action.connect("activate", lambda *_: self._add_separator())

            action_group.add_action(add_action)
            action_group.add_action(sep_action)
            self.dockbar.insert_action_group("dock_global", action_group)

            self.create_gesture(self.dockbar, 3, lambda *_: popover.popup())

        def _create_dockbar_button(
            self, app_name, app_data, class_style, use_label=False
        ):
            if app_data.get("type") == "separator":
                sep = self.gtk.Separator(orientation=self.dockbar.get_orientation())
                sep.set_margin_start(5)
                sep.set_margin_end(5)
                sep.add_css_class("dock-separator")

                menu_model = self.gio.Menu.new()
                menu_model.append("Remove Separator", "sep.remove")
                popover = self.gtk.PopoverMenu.new_from_model(menu_model)
                popover.set_parent(sep)

                action_group = self.gio.SimpleActionGroup.new()
                rem_action = self.gio.SimpleAction.new("remove", None)
                rem_action.connect(
                    "activate", lambda *_: self._remove_from_dockbar(sep)
                )
                action_group.add_action(rem_action)
                sep.insert_action_group("sep", action_group)
                self.create_gesture(sep, 3, lambda *_: popover.popup())
                return sep

            app_cmd = app_data.get("cmd", "")
            icon_name = app_data.get("icon", "system-run")
            button = self.gtk_helper.create_button(
                self.gtk_helper.icon_exist(icon_name),
                app_cmd,
                class_style,
                use_label,
                self.on_left_click,
                app_cmd,
            )
            self.gtk_helper.add_cursor_effect(button)
            button.app_name = app_name  # pyright: ignore
            button.app_config = app_data  # pyright: ignore

            self.create_gesture(
                button, 2, lambda _, cmd=app_cmd: self.on_middle_click(cmd)
            )

            is_vert = self.dockbar.get_orientation() == self.gtk.Orientation.VERTICAL
            menu_model = self.gio.Menu.new()
            menu_model.append("Edit Shortcut", "dock.edit")
            menu_model.append("Move Up" if is_vert else "Move Left", "dock.move_up")
            menu_model.append(
                "Move Down" if is_vert else "Move Right", "dock.move_down"
            )
            menu_model.append("Unpin from Dock", "dock.remove")

            popover = self.gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(button)
            popover.set_has_arrow(False)

            action_group = self.gio.SimpleActionGroup.new()
            actions = {
                "remove": lambda *_: self._remove_from_dockbar(button),
                "edit": lambda *_: self._edit_item(app_name, app_data),
                "move_up": lambda *_: self._move_item(button, -1),
                "move_down": lambda *_: self._move_item(button, 1),
            }
            for name, cb in actions.items():
                act = self.gio.SimpleAction.new(name, None)
                act.connect("activate", cb)
                action_group.add_action(act)

            button.insert_action_group("dock", action_group)
            self.create_gesture(button, 3, lambda *_: popover.popup())

            drag_source = self.gtk.DragSource.new()
            drag_source.set_actions(self.gdk.DragAction.MOVE)
            drag_source.connect("prepare", self.on_drag_prepare)
            drag_source.connect("drag-begin", self.on_drag_begin)
            drag_source.connect("drag-end", self.on_drag_end)
            button.add_controller(drag_source)  # pyright: ignore
            return button

        def _load_and_populate_dockbar(self, orientation, class_style, use_label=False):
            """Loads and populates the dockbar, handling both List and Dict structures."""
            if orientation == "h":
                orientation = self.gtk.Orientation.HORIZONTAL
            elif orientation == "v":
                orientation = self.gtk.Orientation.VERTICAL
            self.dockbar.set_orientation(orientation)

            config_data = self.get_plugin_setting(["app"], [])

            if isinstance(config_data, dict):
                items = config_data.items()
            else:
                items = [
                    (item.get("id", f"app_{i}"), item)
                    for i, item in enumerate(config_data)
                ]

            for app_name, app_data in items:
                widget = self._create_dockbar_button(
                    app_name, app_data, class_style, use_label
                )

                if widget:
                    widget.set_visible(True)
                    self.dockbar.append(widget)

            drop_target = self.gtk.DropTarget.new(
                self.gtk.Button, self.gdk.DragAction.MOVE
            )
            drop_target.connect("drop", self.on_drop)
            self.dockbar.add_controller(drop_target)

        def on_drag_prepare(self, drag_source, x, y):
            return self.gdk.ContentProvider.new_for_value(drag_source.get_widget())

        def on_drag_begin(self, drag_source, drag):
            dragged_widget = drag_source.get_widget()
            paintable = self.gtk.WidgetPaintable.new(dragged_widget)
            drag_source.set_icon(paintable, 0, 0)
            dragged_widget.set_opacity(0.5)

        def on_drag_end(self, drag_source, drag, status):
            drag_source.get_widget().set_opacity(1.0)

        def on_drop(self, drop_target, value, x, y):
            dragged_button = value
            parent_box = drop_target.get_widget()
            new_position_child = None
            is_vertical = parent_box.get_orientation() == self.gtk.Orientation.VERTICAL
            drop_coordinate = y if is_vertical else x

            child = parent_box.get_first_child()
            while child:
                if child is dragged_button:
                    child = child.get_next_sibling()
                    continue
                alloc = child.get_allocation()
                center = (
                    (alloc.y + alloc.height / 2)
                    if is_vertical
                    else (alloc.x + alloc.width / 2)
                )
                if drop_coordinate < center:
                    new_position_child = child
                    break
                child = child.get_next_sibling()

            if new_position_child:
                parent_box.reorder_child_after(dragged_button, new_position_child)
            else:
                parent_box.reorder_child_after(
                    dragged_button, parent_box.get_last_child()
                )
            self.save_dockbar_order()
            return True

        def save_dockbar_order(self):
            """Saves dockbar items as an ordered list to maintain visual sequence."""
            try:
                ordered_apps = []
                child = self.dockbar.get_first_child()

                while child:
                    if hasattr(child, "app_config"):
                        item_config = child.app_config.copy()  # pyright: ignore
                        item_config["id"] = child.app_name  # pyright: ignore
                        ordered_apps.append(item_config)
                    elif isinstance(child, self.gtk.Separator):
                        ordered_apps.append({"type": "separator"})

                    child = child.get_next_sibling()

                self.config_handler.set_root_setting(
                    [str(self.plugin_id), "app"], ordered_apps
                )
            except Exception as e:
                self.logger.error(f"Failed to save dockbar order: {e}")

        def on_left_click(self, cmd):
            self.cmd.run(cmd)
            if (
                not self.layer_always_exclusive
                and self.is_scale_enabled()
                and self.left_click_toggles_scale
            ):
                self.ipc.scale_toggle()

        def on_right_click(self, cmd):
            if not self.right_click_to_next_output:
                self.cmd.run(cmd)
                return
            try:
                outputs = self.ipc.list_outputs()
                focused = self.ipc.get_focused_output()
                idx = next(
                    (i for i, o in enumerate(outputs) if o["id"] == focused["id"]), -1
                )
                next_output = outputs[(idx + 1) % len(outputs)]
                self.wf_helper.move_cursor_middle_output(next_output["id"])
                self.ipc.click_button("S-BTN_LEFT", "full")
                self.cmd.run(cmd)
            except Exception as e:
                self.logger.error(f"Error in right-click action: {e}")

        def on_middle_click(self, cmd):
            if self.middle_click_to_empty_workspace:
                coords = self.wf_helper.find_empty_workspace()
                if coords:
                    self.ipc.scale_toggle()
                    self.ipc.set_workspace(*coords)
                    self.cmd.run(cmd)
                    return
            self.cmd.run(cmd)

        def get_orientation(self):
            container = get_plugin_metadata(self._panel_instance)["container"]
            if "top-panel" in container or "bottom-panel" in container:
                return self.gtk.Orientation.HORIZONTAL
            return (
                self.gtk.Orientation.HORIZONTAL
                if self.panel_orientation.lower() == "h"
                else self.gtk.Orientation.VERTICAL
            )

        def _setup_dockbar(self):
            self._load_and_populate_dockbar(
                self.get_orientation(),
                self.class_style,
            )
            self.main_widget = (self.dockbar, "append")
            if self.layer_always_exclusive:
                top_level = self._get_top_level_panel_widget()
                if top_level:
                    self.layer_shell.set_layer(top_level, self.layer_shell.Layer.TOP)
                    self.layer_shell.auto_exclusive_zone_enable(top_level)

        def _setup_file_watcher(self):
            config_file = self.config_handler.config_file
            try:
                self.gio_config_file = self.gio.File.new_for_path(str(config_file))
                self._config_observer = self.gio_config_file.monitor_file(
                    self.gio.FileMonitorFlags.NONE, None
                )
                self._config_observer.connect(
                    "changed", self._on_gio_config_file_changed
                )
                self._last_config_mod_time = self.os.path.getmtime(config_file)
            except Exception:
                pass

        def __del__(self):
            if self._config_observer:
                self._config_observer.cancel()

        def _on_config_changed(self):
            # Temporarily pause monitor to prevent double-triggering during internal save
            if self._config_observer:
                self._config_observer.cancel()
                self._config_observer = None

            self.config_handler.reload_config()

            # Perform safe UI clear
            children = []
            child = self.dockbar.get_first_child()
            while child:
                children.append(child)
                child = child.get_next_sibling()

            for widget in children:
                # Only remove if the widget hasn't been snatched by a parallel rebuild
                if widget.get_parent() == self.dockbar:
                    self.dockbar.remove(widget)

            # Re-populate and restart monitor
            self._setup_dockbar()
            self._setup_file_watcher()

        def handle_plugin_event(self, msg):
            return False

        def _subscribe_to_events(self):
            if "event_manager" in self.plugins:
                self.plugins["event_manager"].subscribe_to_event(
                    "plugin-activation-state-changed",
                    self.handle_plugin_event,
                    plugin_name="dockbar",
                )

    return DockbarPlugin
