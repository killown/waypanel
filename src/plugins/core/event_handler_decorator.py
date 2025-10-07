def subscribe_to_event(event_type):
    """
    A decorator to register event handlers for Wayfire events.
    Usage:
        @subscribe_to_event("view-focused")
        def on_view_focused(self, event):
            ...
    """

    def decorator(func):
        func._is_event_handler = True
        func._event_type = event_type
        return func

    return decorator


def get_plugin_metadata(_):
    return {
        "enabled": True,
        "priority": 1,
        "deps": ["event_manager"],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    import inspect

    class EventHandlerDecoratorPlugin(BasePlugin):
        def __init__(self, panel_instance):
            """Initialize the plugin to register event handlers for the Compositor events.
            This plugin scans other plugins for decorated event handler functions
            and registers them with the event manager for dispatching when matching
            events occur.
            Args:
                panel_instance: The main panel object providing access to shared resources,
                                including the logger and loaded plugins.
            """
            super().__init__(panel_instance)

        def on_start(self):
            self._register_handlers()

        def _register_handlers(self) -> None:
            """Register all decorated event handlers from other plugins."""
            if "event_manager" not in self.obj.plugins:
                self.logger.error("Event Manager is not available.")
                return
            event_manager = self.obj.plugins["event_manager"]
            registered = set()
            for plugin_name, plugin in self.obj.plugins.items():
                if plugin_name == "event_handler_decorator":
                    continue
                try:
                    for attr_name, attr in inspect.getmembers(
                        plugin, predicate=inspect.isroutine
                    ):
                        if hasattr(attr, "_is_event_handler") and getattr(
                            attr, "_is_event_handler"
                        ):
                            event_type = getattr(attr, "_event_type")
                            key = (plugin_name, attr_name, event_type)
                            if key in registered:
                                continue
                            registered.add(key)
                            sig = inspect.signature(attr)
                            params = list(sig.parameters.values())
                            if len(params) < 1:
                                self.logger.warning(
                                    f"Handler {plugin_name}.{attr_name} has incorrect signature."
                                )
                                continue
                            event_manager.subscribe_to_event(event_type, attr)
                            self.logger.debug(
                                f"Subscribed {plugin_name}.{attr_name} to '{event_type}'"
                            )
                except Exception as e:
                    self.logger.error(
                        f"Error registering handlers for plugin {plugin_name}: {e}"
                    )

    return EventHandlerDecoratorPlugin
