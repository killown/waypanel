def get_plugin_metadata(panel):
    return {
        "id": "org.waypanel.notifier_example",
        "name": "Notifier Integration",
        "description": "Demonstrates the correct usage of the internal Notifier helper.",
        "version": "1.0.0",
        # "background" means a logic-only service. No UI, no GTK container,
        # and no dynamic layout resolution via config_handler.
        "container": "background",
        # CRITICAL: Always define dependencies if the current plugin requires certain plugin to be loaded first
        # WARNING: Missing dependencies can cause plugins to fail loading.
        "deps": ["notify_client", "notify_server"],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    # Import the helper here inside the class getter
    # Assuming the helper is located in src.shared.notifier or similar
    # from src.shared.notifier import Notifier

    class NotifierExamplePlugin(BasePlugin):
        def on_start(self):
            """Initialize the helper once when the plugin is loaded."""
            # In a real scenario, ensure the import path matches your project structure
            # self.notifier = Notifier()
            pass

        def on_enable(self):
            """Use the helper to send a notification when the plugin is enabled."""
            # Example of the helper's notify_send method
            self.notifier.notify_send(
                title="System Alert",
                message="The plugin has been enabled and the Notifier is active.",
                icon="view-refresh-symbolic",
                app_name="Waypanel",
                expire_timeout=3000,
                hints={"urgency": 1},
            )

        def on_disable(self):
            """
            The Notifier uses a daemon thread for its GLib loop,
            so it will clean up with the process, but we log the exit.
            """
            self.logger.info("Notifier Example Plugin disabled.")

    return NotifierExamplePlugin
