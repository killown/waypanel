"""UI and Widget Manager for the Dockbar."""


class DockManager:
    def __init__(self, plugin):
        self.p = plugin

    def load_and_populate(self):
        orientation = self.p.logic.get_orientation()
        self.p.dockbar.set_orientation(orientation)
        config_data = self.p.get_plugin_setting(["app"], [])

        if isinstance(config_data, dict):
            items = config_data.items()
        else:
            items = [
                (item.get("id", f"app_{i}"), item) for i, item in enumerate(config_data)
            ]

        for app_name, app_data in items:
            widget = self.create_dock_item(app_name, app_data)
            if widget:
                widget.set_visible(True)
                self.p.dockbar.append(widget)

        drop_target = self.p.gtk.DropTarget.new(
            self.p.gtk.Button, self.p.gdk.DragAction.MOVE
        )
        drop_target.connect("drop", self.on_drop)
        self.p.dockbar.add_controller(drop_target)

    def create_dock_item(self, app_name, app_data):
        if app_data.get("type") == "separator":
            return self._create_separator()

        app_cmd = app_data.get("cmd", "")
        button = self.p.gtk_helper.create_button(
            self.p.gtk_helper.icon_exist(app_data.get("icon", "system-run")),
            app_cmd,
            self.p.class_style,
            False,
            self.p.logic.on_left_click,
            app_cmd,
        )
        self.p.gtk_helper.add_cursor_effect(button)
        button.app_name = app_name
        button.app_config = app_data

        self.p.create_gesture(
            button, 2, lambda _, cmd=app_cmd: self.p.logic.on_middle_click(cmd)
        )
        self._setup_item_context_menu(button, app_name, app_data)

        # Drag source setup
        drag_source = self.p.gtk.DragSource.new()
        drag_source.set_actions(self.p.gdk.DragAction.MOVE)
        drag_source.connect("prepare", self.on_drag_prepare)
        drag_source.connect("drag-begin", self.on_drag_begin)
        drag_source.connect("drag-end", self.on_drag_end)
        button.add_controller(drag_source)
        return button

    def _create_separator(self):
        sep = self.p.gtk.Separator(orientation=self.p.dockbar.get_orientation())
        sep.set_margin_start(0)
        sep.set_margin_end(0)
        sep.add_css_class("dock-separator")
        # Separator context menu
        menu = self.p.gio.Menu.new()
        menu.append("Remove Separator", "sep.remove")
        popover = self.p.gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(sep)
        ag = self.p.gio.SimpleActionGroup.new()
        act = self.p.gio.SimpleAction.new("remove", None)
        act.connect("activate", lambda *_: self.p._remove_from_dockbar(sep))
        ag.add_action(act)
        sep.insert_action_group("sep", ag)
        self.p.create_gesture(sep, 3, lambda *_: popover.popup())
        return sep

    def _setup_item_context_menu(self, button, app_name, app_data):
        is_vert = self.p.dockbar.get_orientation() == self.p.gtk.Orientation.VERTICAL
        menu = self.p.gio.Menu.new()
        menu.append("Edit Shortcut", "dock.edit")
        menu.append("Move Up" if is_vert else "Move Left", "dock.move_up")
        menu.append("Move Down" if is_vert else "Move Right", "dock.move_down")
        menu.append("Unpin from Dock", "dock.remove")

        popover = self.p.gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(button)
        popover.set_has_arrow(False)

        ag = self.p.gio.SimpleActionGroup.new()
        actions = {
            "remove": lambda *_: self.p._remove_from_dockbar(button),
            "edit": lambda *_: self.p._edit_item(app_name, app_data),
            "move_up": lambda *_: self.p._move_item(button, -1),
            "move_down": lambda *_: self.p._move_item(button, 1),
        }
        for n, cb in actions.items():
            act = self.p.gio.SimpleAction.new(n, None)
            act.connect("activate", cb)
            ag.add_action(act)

        button.insert_action_group("dock", ag)
        self.p.create_gesture(button, 3, lambda *_: popover.popup())

    def on_drag_prepare(self, source, x, y):
        return self.p.gdk.ContentProvider.new_for_value(source.get_widget())

    def on_drag_begin(self, source, drag):
        widget = source.get_widget()
        source.set_icon(self.p.gtk.WidgetPaintable.new(widget), 0, 0)
        widget.set_opacity(0.5)

    def on_drag_end(self, source, drag, status):
        source.get_widget().set_opacity(1.0)

    def on_drop(self, target, value, x, y):
        btn = value
        box = target.get_widget()
        is_vert = box.get_orientation() == self.p.gtk.Orientation.VERTICAL
        coord = y if is_vert else x

        target_child = None
        child = box.get_first_child()
        while child:
            if child is btn:
                child = child.get_next_sibling()
                continue
            alloc = child.get_allocation()
            mid = (
                (alloc.y + alloc.height / 2) if is_vert else (alloc.x + alloc.width / 2)
            )
            if coord < mid:
                target_child = child
                break
            child = child.get_next_sibling()

        if target_child:
            box.reorder_child_after(btn, target_child)
        else:
            box.reorder_child_after(btn, box.get_last_child())

        self.p.save_dockbar_order()
        return True
