import re
from waypanel.src.plugins.core._base import BasePlugin
from waypanel.src.core.create_panel import (
    unset_layer_position_exclusive,
    set_layer_position_exclusive,
)


class HideTopBarPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger.info("Initializing HideTopBar Plugin.")
        self.hidden = False  # Tracks whether the top bar is hidden
        self.title_patterns = [
            r"Steam",  # Example: Match specific titles
            r"Game Mode",
        ]
        self.top_bar_widget = None  # Reference to the top bar widget
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        """Subscribe to relevant events."""
        event_manager = self.plugin_loader.plugins.get("event_manager")
        if event_manager:
            event_manager.subscribe_to_event(
                "view-focused", self.on_view_focused, plugin_name="hide_top_bar"
            )

        # Subscribe to scale activation/deactivation events
        event_manager.subscribe_to_event(
            "plugin-activation-state-changed",
            self.handle_scale_event,
            plugin_name="scale",
        )

    def on_view_focused(self, event_message):
        """Handle when a view gains focus."""
        try:
            view = event_message.get("view")
            if not view:
                return

            title = view.get("title", "")
            should_hide = any(
                re.search(pattern, title) for pattern in self.title_patterns
            )

            if should_hide and not self.hidden:
                self.hide_top_bar()
            elif not should_hide and self.hidden:
                self.restore_top_bar()
        except Exception as e:
            self.logger.error(f"Error handling 'view-focused' event: {e}")

    def handle_scale_event(self, event_message):
        try:
            plugin = event_message.get("plugin")
            state = event_message.get("state")

            if plugin != "scale":
                return

            if state:  # Scale activated
                self.on_scale_activated()
            else:  # Scale deactivated
                self.on_scale_deactivated()

        except Exception as e:
            self.logger.error_handler.handle(f"Error handling scale event: {e}")

    def hide_top_bar(self):
        """Hide the top bar."""
        self.logger.info("Hiding the top bar.")
        self.hidden = True

        # Unset layer position to remove exclusive space
        self.utils.update_widget(unset_layer_position_exclusive, self.top_panel)

        # Hide the top bar completely
        self.top_panel.hide()

    def restore_top_bar(self):
        """Restore the top bar."""
        self.logger.info("Restoring the top bar.")
        self.hidden = False

        # Set layer position back to exclusive
        set_layer_position_exclusive(self.top_panel, 32)

        # Show the top bar again
        self.top_panel.show()

    def enable(self):
        """Enable the plugin."""
        self.logger.info("Enabling HideTopBar Plugin.")

    def disable(self):
        """Disable the plugin and restore the top bar."""
        self.logger.info("Disabling HideTopBar Plugin.")
        if self.hidden:
            self.restore_top_bar()

    def on_scale_activated(self):
        try:
            # set_layer_position_exclusive(self.top_panel, 32)
            # self.top_panel.show()
            print()
        except Exception as e:
            self.logger.error_handler.handle(f"Error handling scale activation: {e}")

    def on_scale_deactivated(self):
        try:
            if self.hidden:
                print()
                # self.utils.update_widget(unset_layer_position_exclusive, self.top_panel)
                # self.top_panel.hide()
        except Exception as e:
            self.logger.error_handler.handle(f"Error handling scale deactivation: {e}")


# Metadata for the plugin
ENABLE_PLUGIN = False
DEPS = ["event_manager"]  # Depends on the event manager plugin


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    """Initialize the plugin."""
    if ENABLE_PLUGIN:
        return HideTopBarPlugin(panel_instance)
