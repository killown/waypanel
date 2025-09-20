import os
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True

# DEPS list is where you add required plugins to load before this example_quick_actions plugin loads,
# Adding DEPS isn't mandatory, but if top_panel doesn't load before example_quick_actions,
# example_quick_actions will fail too.
DEPS = ["top_panel"]


# Define the plugin's position and order
def get_plugin_placement(panel_instance):
    """
    Define where the plugin should be placed in the panel and its order.
    plugin_loader will use this metadata to append the widget to the panel instance.

    Returns:
        tuple: (position, order, priority) for UI plugins
        str: "background" for non-UI/background plugins

    Valid Positions:
        - Top Panel:
            "top-panel-left"
            "top-panel-center"
            "top-panel-right"
            "top-panel-systray"
            "top-panel-after-systray"

        - Bottom Panel:
            "bottom-panel-left"
            "bottom-panel-center"
            "bottom-panel-right"

        - Left Panel:
            "left-panel-top"
            "left-panel-center"
            "left-panel-bottom"

        - Right Panel:
            "right-panel-top"
            "right-panel-center"
            "right-panel-bottom"

        - Background:
            "background"  # For plugins that don't have a UI

    Parameters:
        panel_instance: The main panel object. Can be used to access config or other panels.
    """
    position = "top-panel-center"
    order = 900  # High order to place it towards the end
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the Quick Actions plugin."""
    if ENABLE_PLUGIN:
        quick_actions = QuickActionsPlugin(panel_instance)
        panel_instance.logger.info("Quick Actions plugin initialized.")
        return quick_actions


class QuickActionsPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover = None

        # Create the main button and set it as the plugin's widget
        self.menu_button = Gtk.MenuButton()
        self.menu_button.set_icon_name("system-shutdown-symbolic")
        self.menu_button.add_css_class("quick-actions-button")

        # The main widget must always be set after the main widget container to which we want to append the target_box.
        # The available actions are `append` to append widgets to the top_panel and `set_content`,
        # which is used to set content in other panels such as the left-panel or right-panel.
        # This part of the code is highly important, as the plugin loader strictly requires this metadata.
        self.main_widget = (self.menu_button, "append")

        # Create the popover menu
        self.create_menu_popover()

    def create_menu_popover(self):
        """Create the popover menu for quick actions."""
        self.popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Define actions
        actions = [
            ("Lock Screen", self.lock_screen),
            ("Log Out", self.logout),
            ("Restart", self.restart),
            ("Shut Down", self.shutdown),
        ]

        for label, callback in actions:
            button = Gtk.Button(label=label)
            button.connect("clicked", callback)
            vbox.append(button)

        self.popover.set_child(vbox)
        self.menu_button.set_popover(self.popover)

    def lock_screen(self, widget):
        os.system("loginctl lock-session &")

    def logout(self, widget):
        os.system("swaymsg exit &")

    def restart(self, widget):
        os.system("systemctl reboot &")

    def shutdown(self, widget):
        os.system("systemctl poweroff &")

    def about(self):
        """A plugin that provides a popover menu with quick actions to control the system (e.g., lock, log out, shut down)."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin creates a quick actions menu with buttons to control the system.
        It's designed to be a convenient one-click way for users to lock their screen,
        log out, restart, or shut down.

        The core logic is centered on **popover menu creation and system command execution**:

        1.  **UI Creation**: It creates a `Gtk.MenuButton` and a `Gtk.Popover` widget.
            The button acts as the anchor for the popover menu.
        2.  **Action Buttons**: Inside the popover, it dynamically creates buttons
            for common actions like "Lock Screen" and "Shut Down."
        3.  **Command Execution**: Each button is connected to a handler method that
            executes a corresponding shell command using `os.system()`. For example,
            the "Shut Down" button runs `systemctl poweroff`.
        4.  **Placement**: The `get_plugin_placement` function sets the plugin's
            position on the `top-panel-center`, with a high order to place it
            to the right of other plugins.
        """
        return self.code_explanation.__doc__
