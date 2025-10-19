def get_plugin_metadata(panel):
    """
    Defines the static metadata for the Main Example plugin.
    Metadata must be deterministic and must not rely on runtime configuration,
    ensuring predictable loading and placement by the plugin manager. This
    function is the contract that allows the plugin loader to understand the
    plugin's requirements and identity before instantiating it.
    Returns:
        dict: A dictionary containing the plugin's core metadata.
    """

    id = "org.waypanel.plugin.main_example"
    default_container = "top-panel-center"

    # check for user config containers, this is not necessary for background plugins
    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Main Example",
        "version": "2.3.0",
        "enabled": True,
        "container": container,
        "index": 1,
        "deps": ["event_manager"],
        "description": "A robust, production-grade example using the Dashboard Popover helper.",
    }


def get_plugin_class():
    """
    Factory function that returns the main plugin class.
    To comply with Waypanel's lazy-loading architecture, all necessary
    imports are deferred until this function is called. This minimizes the
    application's startup time by ensuring module code is only loaded into
    memory when the plugin is actually needed.
    Returns:
        type: The `ComprehensiveBaseExample` class definition.
    """
    from typing import Any, Optional
    from src.plugins.core._base import BasePlugin
    from gi.repository import Gtk, GLib  # pyright: ignore

    class ComprehensiveBaseExample(BasePlugin):
        """
        A corrected example demonstrating the robust and safe usage of the
        `create_dashboard_popover` helper and the broader BasePlugin API.
        """

        def __init__(self, panel_instance: Any):
            """Initializes the plugin's state."""
            super().__init__(panel_instance)
            self.popover: Optional[Gtk.Popover] = None
            self.main_button: Optional[Gtk.Button] = None
            self.timeout_id: Optional[int] = None
            self.logger.info("ComprehensiveBaseExample initialized.")

        def on_start(self) -> None:
            """Asynchronous entry point for the plugin's lifecycle."""
            self.logger.info("Lifecycle: ComprehensiveBaseExample starting.")
            self._setup_ui()
            self.timeout_id = GLib.timeout_add_seconds(30, self._demo_timeout_check)

        def on_stop(self) -> None:
            """Asynchronous cleanup hook for the plugin's lifecycle."""
            self.logger.info("Lifecycle: ComprehensiveBaseExample stopping.")
            if self.timeout_id:
                GLib.source_remove(self.timeout_id)
                self.timeout_id = None
            self.logger.info("Lifecycle: ComprehensiveBaseExample cleanup complete.")

        def _setup_ui(self) -> None:
            """Constructs and configures the main GTK widget for the plugin."""
            icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
            self.main_button = Gtk.Button(child=icon)
            self.main_button.set_tooltip_text("BasePlugin Comprehensive Demo")
            self.main_button.connect("clicked", self._on_main_button_click)
            self.add_cursor_effect(self.main_button)
            self.main_widget = (self.main_button, "append")

        def _on_main_button_click(self, button: Gtk.Button) -> None:
            """Handles clicks, creating and showing the popover."""
            if self.popover and self.popover.is_visible():
                self.popover.popdown()
                return
            if not self.popover:
                button_config = {
                    "Run Blocking Task": {
                        "icons": ["system-run-symbolic"],
                        "summary": "3s delay in a thread",
                        "category": "default",
                    },
                    "Run Async IPC Query": {
                        "icons": ["network-transmit-receive-symbolic"],
                        "summary": "Non-blocking Wayfire call",
                        "category": "default",
                    },
                    "Toggle Setting": {
                        "icons": ["preferences-system-symbolic"],
                        "summary": "Saves to config file",
                        "category": "default",
                    },
                    "Run Command": {
                        "icons": ["utilities-terminal-symbolic"],
                        "summary": "Execute a shell command",
                        "category": "default",
                    },
                    "Panel Access": {
                        "icons": ["view-grid-symbolic"],
                        "summary": "Inspect panel state",
                        "category": "default",
                    },
                }
                self.popover = self.create_dashboard_popover(
                    parent_widget=button,
                    popover_closed_handler=self._on_popover_closed,
                    popover_visible_handler=self._on_popover_visible,
                    action_handler=self._on_dashboard_action,
                    button_config=button_config,
                    module_name="main-example",
                    max_children_per_line=2,
                )
            else:
                self.popover.popup()

        def _on_dashboard_action(self, _, action_label: str) -> None:
            """Single action handler for all buttons inside the dashboard popover."""
            self.logger.info(f"Dashboard action triggered: '{action_label}'")
            self.popover.popdown()
            action_map = {
                "Run Blocking Task": self._demo_run_thread,
                "Run Async IPC Query": self._demo_run_async,
                "Toggle Setting": self._demo_update_config,
                "Run Command": self._demo_run_command,
                "Panel Access": self._demo_panel_access,
            }
            demo_function = action_map.get(action_label)
            if demo_function:
                demo_function()
            else:
                self.logger.warning(f"No action defined for '{action_label}'")

        def _on_popover_closed(self, *args) -> None:
            """Callback for popover closure. Accepts arbitrary arguments."""
            self.logger.debug("Popover closed.")

        def _on_popover_visible(self, *args) -> None:
            """Callback for popover visibility. Accepts arbitrary arguments."""
            self.logger.debug("Popover is now visible.")

        def _demo_run_thread(self) -> None:
            """Demonstrates running a blocking task in a background thread."""
            self.run_in_thread(self.time.sleep, 3).add_done_callback(
                lambda _: self.schedule_in_gtk_thread(
                    self.notify_send,
                    "Threading Demo",
                    "Blocking task finished after 3s",
                    "system-run",
                )
            )

        def _demo_run_async(self) -> None:
            """Demonstrates running an `async` task correctly."""

            async def _query():
                """A simple example of an awaitable operation."""
                self.logger.debug("Coroutine `_query` is executing.")
                outputs = self.ipc.list_outputs()
                return f"Found {len(outputs)} outputs."

            coro = _query()
            self.run_in_async_task(
                coro,
                lambda result: self.notify_send(
                    "Async IPC", result, "network-transmit-receive"
                ),
            )

        def _demo_update_config(self) -> None:
            """Demonstrates reading and writing to the plugin's namespaced config."""
            new_value = not self.get_plugin_setting("demo_setting", True)
            self.set_plugin_setting(["demo_setting"], new_value)
            self.notify_send(
                "Config Saved", f"Toggled to: {new_value}", "preferences-system"
            )

        def _demo_run_command(self) -> None:
            """Demonstrates using the command runner."""
            self.run_cmd("echo 'Helper demo finished.'")
            self.notify_send(
                "Command Runner", "Shell command executed", "utilities-terminal"
            )

        def _demo_panel_access(self) -> None:
            """Demonstrates introspection of the panel and other plugins."""
            details = f"Total Plugins Loaded: {len(self.plugins)}"
            self.notify_send("Panel Introspection", details, "view-grid")

        def _demo_timeout_check(self) -> bool:
            """A recurring task scheduled via GLib.timeout_add_seconds."""
            self.logger.debug("GLib Timeout: Running recurring check.")
            return GLib.SOURCE_CONTINUE

    return ComprehensiveBaseExample
