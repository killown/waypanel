def get_plugin_metadata(panel):
    """
    Define the plugin's properties, dependencies, and panel placement.

    Args:
        panel: The main Panel instance, used here to access config_handler.
               (Type: The specific Panel application class.)
    """
    id = "org.waypanel.plugin.example_quick_actions"
    default_container = "top-panel-center"

    # check for user config containers, this is not necessary for background plugins
    container, id = panel.config_handler.get_plugin_container(default_container, id)
    return {
        "id": id,
        "name": "Quick Actions",
        "version": "2.0.0",
        "enabled": True,
        "container": container,
        "index": 900,
        "description": "Provides a popover menu with safe, non-blocking system actions.",
    }


def get_plugin_class():
    """Factory function that returns the main plugin class."""
    from typing import Any, Optional
    from src.plugins.core._base import BasePlugin
    from gi.repository import Gtk  # pyright: ignore

    class QuickActionsPlugin(BasePlugin):
        """
        A plugin that provides a popover menu with quick actions to control
        the system (e.g., lock, log out, shut down).
        """

        def __init__(self, panel_instance: Any):
            """
            Initializes the plugin's state. Defers all heavy lifting and
            UI construction to the `on_start` lifecycle hook.
            """
            super().__init__(panel_instance)
            self.popover: Optional[Gtk.Popover] = None
            self.menu_button: Optional[Gtk.MenuButton] = None
            self.logger.info("QuickActionsPlugin initialized.")

        def on_start(self) -> None:
            """
            Asynchronous entry point. Creates the UI and sets up the plugin.
            """
            self.logger.info("Lifecycle: QuickActionsPlugin starting.")
            self._setup_ui()

        def on_stop(self) -> None:
            """
            Asynchronous cleanup hook.
            """
            self.logger.info("Lifecycle: QuickActionsPlugin stopped.")

        def _setup_ui(self) -> None:
            """
            Constructs the main menu button and assigns it to `self.main_widget`.
            The popover itself is created lazily on the first click.
            """
            self.menu_button = Gtk.Button()  # pyright: ignore
            self.menu_button.set_icon_name("system-shutdown-symbolic")  # pyright: ignore
            self.menu_button.add_css_class("quick-actions-button")  # pyright: ignore
            self.menu_button.connect("clicked", self._on_menu_button_click)  # pyright: ignore
            self.add_cursor_effect(self.menu_button)
            self.main_widget = (self.menu_button, "append")

        def _on_menu_button_click(self, button: Gtk.MenuButton) -> None:
            """
            Handles the menu button click, creating the popover on demand
            using the shared `create_dashboard_popover` helper.
            """
            if self.popover:
                self.popover.popup()
                return
            button_config = {
                "Lock Screen": {
                    "icons": ["system-lock-screen-symbolic"],
                    "summary": "Lock the current session",
                    "category": "Session",
                },
                "Log Out": {
                    "icons": ["system-log-out-symbolic"],
                    "summary": "End the current session",
                    "category": "Session",
                },
                "Restart": {
                    "icons": ["system-reboot-symbolic"],
                    "summary": "Reboot the system",
                    "category": "Power",
                },
                "Shut Down": {
                    "icons": ["system-shutdown-symbolic"],
                    "summary": "Power off the system",
                    "category": "Power",
                },
            }
            self.popover = self.create_dashboard_popover(
                parent_widget=button,
                popover_closed_handler=lambda _: self.logger.debug(
                    "Quick Actions popover closed."
                ),
                popover_visible_handler=lambda _: None,
                action_handler=self._on_action,
                button_config=button_config,
                module_name="quick-actions",
                max_children_per_line=2,
            )

        def _on_action(self, _, action_label: str) -> None:
            """
            Handles clicks from within the dashboard popover and executes the
            appropriate system command safely using the plugin's command runner.
            """
            self.logger.info(f"Executing quick action: {action_label}")
            if self.popover:
                self.popover.popdown()
            command_map = {
                "Lock Screen": "loginctl lock-session",
                "Log Out": "swaymsg exit",
                "Restart": "systemctl reboot",
                "Shut Down": "systemctl poweroff",
            }
            command = command_map.get(action_label)
            if command:
                self.run_cmd(command)
            else:
                self.logger.warning(f"No command defined for action: '{action_label}'")

        def code_explanation(self):
            """
            This plugin creates a quick actions menu using the framework's best practices.
            1.  **Asynchronous Lifecycle**: All UI setup is deferred to the `on_start`
                method, ensuring the GTK environment is fully initialized. `__init__`
                is kept lightweight for fast plugin loading.
            2.  **Reusable UI Component**: Instead of manually building a popover, it
                uses the `self.create_dashboard_popover` helper. The UI is defined
                declaratively via the `button_config` dictionary, promoting consistency
                and reducing boilerplate.
            3.  **Centralized Action Handling**: A single `_on_action` method serves as
                a dispatcher, mapping button labels to their corresponding system commands.
                This is cleaner and more maintainable than connecting a separate callback
                for each button.
            4.  **Safe Command Execution**: All shell commands are executed via `self.run_cmd(...)`.
                This is the architecturally correct approach, as it uses the `BasePlugin`'s
                `CommandRunner` which runs commands in a non-blocking background thread,
                preventing the UI from freezing. It is a direct, safer replacement for `os.system`.
            """
            return self.code_explanation.__doc__

    return QuickActionsPlugin
