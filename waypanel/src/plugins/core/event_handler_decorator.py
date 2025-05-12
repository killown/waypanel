from src.plugins.core._base import BasePlugin
import logging

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

    def _register_handlers(self):
        """Register all decorated event handlers from other plugins."""
        if "event_manager" not in self.obj.plugins:
            self.logger.error("Event Manager is not available.")
            return

        event_manager = self.obj.plugins["event_manager"]

        # Loop through all loaded plugins
        for plugin_name, plugin in self.obj.plugins.items():
            if plugin == self:
                continue  # Skip self

            try:
                # Check all methods of the plugin
                for attr_name in dir(plugin):
                    attr = getattr(plugin, attr_name)

                    # Only consider bound methods (has __func__ means it's a bound method)
                    if hasattr(attr, "__func__"):
                        func = attr.__func__

                        if hasattr(func, "_is_event_handler"):
                            event_type = getattr(func, "_event_type")
                            handler_func = attr  # Use the bound method

                            # Subscribe
                            event_manager.subscribe_to_event(event_type, handler_func)
                            self.logger.debug(
                                f"Subscribed {plugin_name}.{attr_name} to '{event_type}'"
                            )

            except Exception as e:
                self.logger.error(
                    f"Error registering handlers for plugin {plugin_name}: {e}"
                )
