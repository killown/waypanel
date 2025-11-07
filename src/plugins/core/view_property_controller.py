def get_plugin_metadata(_):
    """
    Define the plugin's properties and dependencies.
    This plugin runs as a background service and requires the 'event_manager'
    to subscribe to compositor events.
    """
    return {
        "id": "org.waypanel.plugin.view_property_controller",
        "name": "View Property Controller",
        "version": "1.0.0",
        "enabled": True,
        "container": "background",
        "description": "Watches for view events to set or update view properties (e.g., icon).",
        "deps": ["event_manager"],
    }


def get_plugin_class():
    """
    Factory function that returns the main plugin class.
    All imports are deferred to this function as required.
    """
    from src.plugins.core._base import BasePlugin
    from typing import Any, Dict, Optional

    class ViewPropertyControllerPlugin(BasePlugin):
        """
        A background plugin that monitors view events to apply
        standardized properties.
        This service listens for `view-mapped` and `view-title-changed`
        events. Upon receiving one, it calculates the desired property
        (e.g., a standardized icon name) and applies it to the view
        using `ipc.set_view_property`.
        """

        def __init__(self, panel_instance: Any):
            """
            Initializes the plugin instance.
            """
            super().__init__(panel_instance)
            self._subscription_timer_id: Optional[int] = None

        def on_start(self) -> None:
            """
            Asynchronous entry point. Schedules the subscription attempt.
            """
            self.logger.info("Starting View Property Controller...")
            self._subscription_timer_id = self.glib.timeout_add_seconds(
                1, self._attempt_subscription
            )

        def _attempt_subscription(self) -> bool:
            """
            Attempts to find the 'event_manager' and subscribe to events.
            Retries if the manager is not yet available.
            """
            event_manager = self.plugins.get("event_manager")
            if not event_manager:
                self.logger.warning(
                    "ViewPropertyController: EventManager not yet available, will retry..."
                )
                return True
            try:
                event_manager.subscribe_to_event("view-mapped", self._on_view_event)
                event_manager.subscribe_to_event(
                    "view-title-changed", self._on_view_event
                )
                self.logger.info(
                    "View Property Controller successfully subscribed to view events."
                )
                self._subscription_timer_id = None
                return self.glib.SOURCE_REMOVE
            except Exception as e:
                self.logger.error(
                    f"ViewPropertyController: Failed to subscribe to events: {e}",
                    exc_info=True,
                )
                self._subscription_timer_id = None
                return self.glib.SOURCE_REMOVE

        def _on_view_event(self, event_data: Dict[str, Any]) -> None:
            """
            Handles 'view-mapped' and 'view-title-changed' events.
            This function can be extended to set any number of
            view properties as needed.
            """
            view = event_data.get("view")
            if not isinstance(view, dict):
                return
            view_id: Optional[int] = view.get("id")
            app_id: Optional[str] = view.get("app-id")
            title: Optional[str] = view.get("title")
            if not all([view_id, app_id, title]) or app_id == "nil":
                return
            try:
                initial_title: str = title.split(" ")[0].lower()  # pyright: ignore
                icon_name: str = self.gtk_helper.get_icon(app_id, initial_title, title)  # pyright: ignore
                if hasattr(self.ipc, "set_view_property"):
                    self.ipc.set_view_property(view_id, "icon", icon_name)
                    self.logger.debug(f"Set 'icon' for view {view_id} to '{icon_name}'")
            except Exception as e:
                self.logger.warning(
                    f"Failed to set property for view {view_id}: {e}",
                    exc_info=False,
                )

        def on_stop(self) -> None:
            """
            Called when the plugin is stopped or unloaded.
            """
            if self._subscription_timer_id:
                self.glib.source_remove(self._subscription_timer_id)
                self._subscription_timer_id = None
            self.logger.info("View Property Controller stopped.")

    return ViewPropertyControllerPlugin
