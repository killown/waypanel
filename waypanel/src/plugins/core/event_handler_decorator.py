from src.plugins.core._base import BasePlugin
import logging
import inspect

ENABLE_PLUGIN = True
DEPS = ["event_manager"]


def subscribe_to_event(event_type):
    """
    A decorator to register event handlers for Wayfire events.

    Usage:
        @subscribe_to_event("view-focused")
        def on_view_focused(self, event):
            ...
    """

    def decorator(func):
        # Attach metadata directly to the original function
        func._is_event_handler = True
        func._event_type = event_type
        return func

    return decorator


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if not ENABLE_PLUGIN:
        panel_instance.logger.info("Event Handler Decorator Plugin is disabled.")
        return None

    return EventHandlerDecoratorPlugin(panel_instance)


class EventHandlerDecoratorPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger = logging.getLogger(__name__)
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
                continue  # Skip self

            try:
                # Use inspect.getmembers() to get only callable members
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

                        # Validate signature
                        sig = inspect.signature(attr)
                        params = list(sig.parameters.values())
                        if len(params) < 1:
                            self.logger.warning(
                                f"Handler {plugin_name}.{attr_name} has incorrect signature."
                            )
                            continue

                        # Subscribe
                        event_manager.subscribe_to_event(event_type, attr)
                        self.logger.debug(
                            f"Subscribed {plugin_name}.{attr_name} to '{event_type}'"
                        )

            except Exception as e:
                self.logger.error(
                    f"Error registering handlers for plugin {plugin_name}: {e}"
                )
