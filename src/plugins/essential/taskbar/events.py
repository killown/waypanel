class TaskbarEvents:
    """Handles compositor and plugin event subscriptions and routing."""

    def __init__(self, plugin_instance):
        """Initializes the event handler.

        Args:
            plugin_instance: The TaskbarPlugin instance.
        """
        self.plugin = plugin_instance

    def subscribe(self):
        """Subscribes to all relevant compositor and lifecycle events."""
        mgr = self.plugin.plugins.get("event_manager")
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
            mgr.subscribe_to_event(ev, self._handle_view_event, "taskbar")

        mgr.subscribe_to_event(
            "plugin-activation-state-changed", self._handle_plugin_event, "taskbar"
        )

    def _handle_view_event(self, msg: dict):
        """Routes view events to the appropriate plugin logic."""
        ev, v = msg.get("event"), msg.get("view")
        if not v:
            return

        if ev in (
            "view-unmapped",
            "view-mapped",
            "view-title-changed",
            "view-app-id-changed",
        ):
            if not self.plugin._debounce_pending:
                from gi.repository import GLib

                self.plugin._debounce_pending = True
                self.plugin._debounce_timer_id = GLib.timeout_add(
                    self.plugin._debounce_interval, self.plugin.Taskbar
                )
        elif ev == "view-focused":
            self.plugin.on_view_focused(v)

    def _handle_plugin_event(self, msg: dict) -> bool:
        """Handles internal plugin state changes (e.g., scale activation)."""
        if (
            msg.get("event") == "plugin-activation-state-changed"
            and msg.get("plugin") == "scale"
        ):
            self.plugin.is_scale_active[msg.get("output")] = bool(msg.get("state"))
            if not msg.get("state") and self.plugin.menu_handler.menu:
                self.plugin.menu_handler.popdown()
        return False
