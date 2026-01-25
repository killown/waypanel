class DockMenu:
    """Handles the context menu for dock items."""

    def __init__(self, plugin):
        self.p = plugin

    def create_context_menu(self, button, app_name, app_data):
        """Creates a Gtk.Popover menu with actions and icons."""
        popover = self.p.gtk.Popover()
        popover.add_css_class("dockbar-context-menu")

        menu_box = self.p.gtk.Box.new(self.p.gtk.Orientation.VERTICAL, 2)
        for m in ["start", "end", "top", "bottom"]:
            getattr(menu_box, f"set_margin_{m}")(6)

        # Action definitions: (Label, Icon, Method)
        actions = [
            (
                "Edit Shortcut",
                "edit-symbolic",
                lambda: self.p.editor.open_editor(app_name, app_data),
            ),
            (
                "Remove Item",
                "list-remove-symbolic",
                lambda: self._remove_item(app_name),
            ),
        ]

        for label, icon, cb in actions:
            item = self._create_menu_item(label, icon, cb, popover)
            menu_box.append(item)

        popover.set_child(menu_box)
        return popover

    def _create_menu_item(self, label_text, icon_name, callback, popover):
        btn = self.p.gtk.Button()
        btn.set_has_frame(False)
        btn.add_css_class("dockbar-menu-item")

        box = self.p.gtk.Box(orientation=self.p.gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(8)
        box.set_margin_end(8)

        icon = self.p.gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(16)

        lbl = self.p.gtk.Label(label=label_text)

        box.append(icon)
        box.append(lbl)
        btn.set_child(box)

        def on_click(_):
            popover.popdown()
            callback()

        btn.connect("clicked", on_click)
        return btn

    def _remove_item(self, app_name):
        """Removes an item from the configuration."""
        config = self.p.get_plugin_setting(["app"], [])
        if isinstance(config, dict) and app_name in config:
            del config[app_name]
            self.p.set_plugin_setting(["app"], config)
