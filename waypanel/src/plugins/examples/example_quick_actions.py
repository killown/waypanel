import os
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


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

        # Define the main widget for the plugin loader
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
