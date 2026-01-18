def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.auto_center"
    container = "background"

    return {
        "id": id,
        "name": "Auto Center",
        "version": "1.1.0",
        "enabled": True,
        "container": container,
        "index": 0,
        "deps": ["event_manager"],
        "description": "Automatically centers newly mapped windows based on size and app-id filters.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class AutoCenterPlugin(BasePlugin):
        """
        Monitors 'view-mapped' events and centers floating views.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.ignore_list = []
            self.threshold = 0.9

        def on_start(self):
            """Subscribes to events and registers configuration settings."""
            self.ignore_list = self.get_plugin_setting_add_hint(
                "ignore_app_ids",
                ["gnome-calculator", "pavucontrol"],
                "List of app-ids to skip auto-centering",
            )
            self.threshold = self.get_plugin_setting_add_hint(
                "maximized_threshold",
                0.9,
                "Percentage (0.0-1.0) of workarea coverage to consider a view 'maximized'",
            )

            self._subscribe_to_events()

        def _subscribe_to_events(self):
            """Connects to the event manager to listen for window mapping."""
            if "event_manager" not in self.obj.plugin_loader.plugins:
                self.logger.error("Event Manager not found; cannot auto-center views.")
                return

            event_mgr = self.obj.plugin_loader.plugins["event_manager"]
            event_mgr.subscribe_to_event("view-mapped", self._on_view_mapped)

        def _on_view_mapped(self, event_data: dict):
            """
            Evaluates the size and app-id of a newly mapped view and centers it if floating.

            Args:
                event_data: The IPC event payload containing view details.
            """
            view = event_data.get("view", {})
            view_id = view.get("id")
            app_id = view.get("app-id", "")

            if (
                view_id is None
                or view.get("fullscreen")
                or view.get("tiled-edges", 0) > 0
            ):
                return

            if app_id in self.ignore_list:
                return

            outputs = self.ipc.list_outputs()
            out = next((o for o in outputs if o["id"] == view.get("output-id")), None)

            if not out:
                return

            wa = out["workarea"]
            geom = view.get("geometry", {})
            w, h = geom.get("width", 0), geom.get("height", 0)

            is_nearly_maximized = w > (wa["width"] * self.threshold) and h > (
                wa["height"] * self.threshold
            )

            if not is_nearly_maximized:
                self.wf_helper.center_view_on_output(view_id, w, h)

        def on_stop(self):
            """Cleanup operations when the plugin is disabled."""
            pass

    return AutoCenterPlugin
