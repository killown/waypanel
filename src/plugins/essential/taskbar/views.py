class TaskbarViews:
    """Handles view logic, grouping, focusing, and focus state management."""

    def __init__(self, plugin_instance):
        self.plugin = plugin_instance

    def handle_focus_change(self, view: dict):
        """Updates internal state and UI classes when a view gains focus."""
        if not view or view.get("role") != "toplevel":
            return

        fid, aid = view.get("id"), view.get("app-id")
        self.plugin.group_last_focused[aid] = fid

        # Update visual focused classes on buttons
        for ident, btn in self.plugin.in_use_buttons.items():
            is_focused = (self.plugin.group_apps and ident == aid) or (
                not self.plugin.group_apps and ident == fid
            )

            if is_focused:
                btn.add_css_class("focused")
            else:
                btn.remove_css_class("focused")

        # Debounce taskbar sync to update labels/counts
        if not self.plugin._debounce_pending:
            from gi.repository import GLib

            self.plugin._debounce_pending = True
            self.plugin._debounce_timer_id = GLib.timeout_add(
                self.plugin._debounce_interval, self.plugin.Taskbar
            )

    def restore_group_focus(self, identifier):
        """Logic for middle-click restoration of last known view in a group."""
        views = [v for v in self.plugin.ipc.list_views() if self.is_valid_view(v)]
        target_views = [
            v
            for v in views
            if (
                v.get("app-id") == identifier
                if self.plugin.group_apps
                else v.get("id") == identifier
            )
        ]
        if not target_views:
            return

        last_id = self.plugin.group_last_focused.get(identifier)
        target = next(
            (v for v in target_views if v.get("id") == last_id), target_views[0]
        )
        self.set_view_focus(target)

    def set_view_focus(self, view: dict) -> None:
        try:
            vid = view.get("id")
            v = self.plugin.wf_helper.is_view_valid(vid)
            if not v:
                return
            if self.plugin.is_scale_active.get(v.get("output-id")):
                self.plugin.ipc.scale_toggle()
            self.plugin.ipc.go_workspace_set_focus(vid)
            self.plugin.ipc.center_cursor_on_view(vid)
        except Exception as e:
            self.plugin.logger.error(f"Error focusing: {e}")

    def is_valid_view(self, v: dict) -> bool:
        return bool(
            v
            and v.get("layer") == "workspace"
            and v.get("role") == "toplevel"
            and v.get("mapped")
            and v.get("app-id") not in ("nil", None)
            and v.get("pid") != -1
        )

    def cycle_group_focus(self, identifier, direction):
        """Cycles focus among views in a group based on scroll direction."""
        # Filter valid views belonging to this app/identifier
        views = [v for v in self.plugin.ipc.list_views() if self.is_valid_view(v)]
        target_views = [
            v
            for v in views
            if (
                v.get("app-id") == identifier
                if self.plugin.group_apps
                else v.get("id") == identifier
            )
        ]

        if len(target_views) <= 1:
            return

        # Find the index of the currently focused view within this group
        current_focus_id = self.plugin.group_last_focused.get(identifier)

        try:
            current_idx = next(
                i for i, v in enumerate(target_views) if v.get("id") == current_focus_id
            )
            # Calculate next index with wrap-around
            next_idx = (current_idx + direction) % len(target_views)
            target = target_views[next_idx]
            self.set_view_focus(target)
        except StopIteration:
            # If none are focused, just pick the first one
            self.set_view_focus(target_views[0])
