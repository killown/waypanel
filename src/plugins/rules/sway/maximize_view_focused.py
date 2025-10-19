def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.auto_maximize",
        "enabled": False,
        "name": "Maximize Focused View",
        "version": "1.0.0",
        "deps": "event_manager",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event

    class AutoMaximizePlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.logger.info("AutoMaximizePlugin initialized.")

        @subscribe_to_event("view-mapped")
        def on_view_focused(self, event_message):
            """
            Handle 'view-focused' event by maximizing the view.

            Args:
                event_message (dict): The event message containing view details.
            """
            try:
                if "view" in event_message:
                    view = event_message["view"]
                    print(view)
                    view_id = view.get("id")

                    if not view_id:
                        self.logger.warning("Received evenmd without a valid view ID.")
                        return
                    for _ in range(3):
                        self.ipc.utils.maximize_view(view_id)

            except Exception as e:
                self.logger.error(f"Error handling event: {e}")

    return AutoMaximizePlugin
