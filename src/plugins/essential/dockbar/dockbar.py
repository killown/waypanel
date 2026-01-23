def get_plugin_metadata(panel_instance):
    config = panel_instance.config_handler
    pos = config.get_root_setting(
        ["org.waypanel.plugin.dockbar", "panel", "position"], "left"
    )
    valid = {
        "left": "left-panel-center",
        "right": "right-panel-center",
        "top": "top-panel-center",
        "bottom": "bottom-panel-center",
    }
    return {
        "id": "org.waypanel.plugin.dockbar",
        "name": "Dockbar",
        "version": "1.0.1",
        "enabled": True,
        "container": valid.get(pos, "left-panel-center"),
        "priority": 1,
        "deps": ["event_manager", "gestures_setup", "left_panel"],
        "description": "A plugin that creates a configurable dockbar for launching applications.",
    }


def get_plugin_class():
    from core._base import BasePlugin
    from gi.repository import Gio
    from .logic import DockLogic
    from .manager import DockManager
    from .editor import ShortcutEditor

    class DockbarPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self._init_settings()
            self.logic = DockLogic(self)
            self.ui = DockManager(self)
            self.editor = ShortcutEditor(self)

            self.dockbar = self.gtk.Box(
                spacing=self.spacing, orientation=self.logic.get_orientation()
            )
            self.create_gesture = self.plugins["gestures_setup"].create_gesture
            self.dockbar_content = self.get_panel()

            self._setup_dockbar()
            self.logic.setup_file_watcher()
            self._setup_dock_context_menu()
            self._subscribe_to_events()

        def _init_settings(self):
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

        def _setup_dockbar(self):
            self.ui.load_and_populate()
            self.main_widget = (self.dockbar, "append")
            if self.layer_always_exclusive:
                top_level = self._get_top_level_panel_widget()
                if top_level:
                    self.layer_shell.set_layer(top_level, self.layer_shell.Layer.TOP)
                    self.layer_shell.auto_exclusive_zone_enable(top_level)

        def _on_gio_config_file_changed(
            self,
            monitor: Gio.FileMonitor,
            file: Gio.File,
            other_file: Gio.File,
            event_type: Gio.FileMonitorEvent,
        ) -> None:
            config_file = self.config_handler.config_file
            if event_type in (
                Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                Gio.FileMonitorEvent.MOVED,
                Gio.FileMonitorEvent.CHANGED,
            ):
                try:
                    current_mod_time = self.os.path.getmtime(config_file)
                    if (
                        current_mod_time
                        > getattr(self, "_last_config_mod_time", 0) + 0.1
                    ):
                        self._last_config_mod_time = current_mod_time
                        self.glib.idle_add(self._on_config_changed)
                except (FileNotFoundError, Exception):
                    pass

        def _on_config_changed(self):
            if hasattr(self, "_config_observer") and self._config_observer:
                self._config_observer.cancel()
                self._config_observer = None

            self.config_handler.reload_config()

            child = self.dockbar.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                if child.get_parent() == self.dockbar:
                    self.dockbar.remove(child)
                child = next_child

            self._setup_dockbar()
            self.logic.setup_file_watcher()

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

        def _edit_item(self, app_name=None, app_config=None):
            """Delegates shortcut editing to the GNOME HIG compliant editor."""
            self.editor.open(app_name, app_config)

        def _add_separator(self):
            apps = self.get_plugin_setting(["app"], [])
            apps.append({"type": "separator"})
            self.config_handler.set_root_setting([str(self.plugin_id), "app"], apps)
            self.glib.idle_add(self._on_config_changed)

        def _setup_dock_context_menu(self):
            menu_model = Gio.Menu.new()
            menu_model.append("Add New Launcher", "dock_global.add")
            menu_model.append("Add Separator", "dock_global.separator")

            popover = self.gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(self.dockbar)
            popover.set_has_arrow(False)

            action_group = Gio.SimpleActionGroup.new()
            add_action = Gio.SimpleAction.new("add", None)
            add_action.connect("activate", lambda *_: self._edit_item())
            sep_action = Gio.SimpleAction.new("separator", None)
            sep_action.connect("activate", lambda *_: self._add_separator())

            action_group.add_action(add_action)
            action_group.add_action(sep_action)
            self.dockbar.insert_action_group("dock_global", action_group)

            self.create_gesture(self.dockbar, 3, lambda *_: popover.popup())

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
            position = self.panel_position.lower().split("-")[0]
            valid_panels = {
                "left": self._panel_instance.left_panel_box_center,
                "right": self._panel_instance.right_panel_box_center,
                "top": self._panel_instance.top_panel_box_center,
                "bottom": self._panel_instance.bottom_panel_box_center,
            }
            return valid_panels.get(
                position, self._panel_instance.left_panel_box_center
            )

        def _subscribe_to_events(self):
            if "event_manager" in self.plugins:
                self.plugins["event_manager"].subscribe_to_event(
                    "plugin-activation-state-changed",
                    lambda msg: False,
                    plugin_name="dockbar",
                )

        def __del__(self):
            if hasattr(self, "_config_observer") and self._config_observer:
                self._config_observer.cancel()

    return DockbarPlugin
