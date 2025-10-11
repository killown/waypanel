def get_plugin_metadata(_):
    """
    Provides the structured metadata for the Setting Timer Example plugin.
    This plugin demonstrates the lifecycle of a configuration setting.
    """
    return {
        "id": "org.waypanel.plugin.setting_timer_example",
        "name": "Setting Timer Example",
        "version": "1.0.0",
        "enabled": True,
        "index": 99,
        "container": "top-panel-center",
        "description": "A demonstration plugin for managing settings over time.",
    }


def get_plugin_class():
    """
    Provides the plugin's main class, deferring all necessary imports
    to adhere to the project's architectural standards.
    """
    from src.plugins.core._base import BasePlugin

    class SettingTimerExample(BasePlugin):
        """
        An example plugin that demonstrates the correct use of the BasePlugin's
        configuration management API.

        Upon starting, it writes a setting to the configuration file and then
        schedules a timer to remove that entire setting section after a 10-second delay.
        """

        def __init__(self, panel_instance):
            """Initializes the plugin state."""
            super().__init__(panel_instance)
            self._timer_id = None
            self._label = self.gtk.Label()
            self._label.add_css_class("example-plugin-label")

        def on_start(self):
            """
            Entry point for the plugin's lifecycle.

            This method sets an initial configuration, schedules its own cleanup,
            and initializes the UI widget.
            """
            self.logger.info("Setting Timer Example plugin has started.")

            # 1. Set the initial plugin setting.
            initial_data = {
                "status": "active",
                "creation_timestamp": self.time.time(),
                "message": "This setting will self-destruct.",
            }
            self.set_plugin_setting("session_data", initial_data)
            self.logger.info(
                f"Initial setting written for plugin '{self.plugin_id}'. "
                "It will be removed in 10 seconds."
            )
            self._label.set_text("   Setting created. Removal pending...")

            # 2. Schedule the removal of the setting using GLib's timer.
            self._timer_id = self.glib.timeout_add_seconds(
                10, self._remove_setting_callback
            )

            # 3. Define the main widget to be added to the panel.
            self.main_widget = (self._label, "append")

        def _remove_setting_callback(self):
            """
            Callback function executed by the GLib timer.

            This method calls the appropriate BasePlugin API to remove its own
            configuration section and then updates the UI to reflect the change.
            """
            self.logger.info(
                f"10-second timer elapsed. Removing settings for '{self.plugin_id}'."
            )

            # 1. Remove the entire section related to this plugin.
            self.remove_plugin_setting()

            self.logger.info("Plugin settings have been successfully removed.")
            self._label.set_text("   Setting removed.")
            self.glib.timeout_add_seconds(3, self._disable_plugin)
            self._timer_id = None

            # 2. Return False (or GLib.SOURCE_REMOVE) to stop the timer from repeating.
            return self.glib.SOURCE_REMOVE

        def _disable_plugin(self):
            self.plugin_loader.disable_plugin("example_settings")
            return False

        def on_disable(self):
            """
            Cleanup hook for when the plugin is disabled or reloaded.

            Ensures that any pending timers are cancelled to prevent callbacks
            from firing after the plugin is no longer active.
            """
            if self._timer_id:
                self.glib.source_remove(self._timer_id)
                self._timer_id = None
                self.logger.info("Pending setting removal timer has been cancelled.")

            self.logger.info("Setting Timer Example plugin has been disabled.")

    return SettingTimerExample
