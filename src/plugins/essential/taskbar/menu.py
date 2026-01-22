class TaskbarMenu:
    """Handles the creation and logic of the right-click context menu."""

    def __init__(self, plugin_instance):
        """Initializes the menu handler.

        Args:
            plugin_instance: The TaskbarPlugin instance.
        """
        self.plugin = plugin_instance
        self.ipc = plugin_instance.ipc
        self.menu = None

    def show(self, widget, x, y):
        """Creates and displays the context menu for a specific view."""
        from gi.repository import Gtk, Gdk

        if self.menu:
            self.menu.unparent()
            self.menu = None

        self.menu = Gtk.Popover()
        self.menu.set_parent(widget)
        self.menu.set_has_arrow(True)
        self.menu.set_autohide(True)
        self.menu.active_view_id = widget.view_id

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        view_data = self.ipc.get_view(widget.view_id)

        if not view_data:
            return

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

    def popdown(self):
        """Hides the menu."""
        if self.menu:
            self.menu.popdown()

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
        self.plugin.wf_helper.send_view_to_output(self.menu.active_view_id, None, True)
        self.menu.popdown()

    def _on_menu_close_clicked(self, _):
        self.ipc.close_view(self.menu.active_view_id)
        self.menu.popdown()

    def _on_menu_kill_clicked(self, _):
        view = self.plugin.wf_helper.is_view_valid(self.menu.active_view_id)
        if view and view.get("pid"):
            self.plugin.run_cmd(f"kill -9 {view.get('pid')}")
        self.menu.popdown()
