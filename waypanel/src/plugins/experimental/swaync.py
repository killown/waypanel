import os
import subprocess
from gi.repository import Gtk

import toml

from waypanel.src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """
    Define the plugin's position and order.
    Returns:
        tuple: (position, order)
    """
    position = "top-panel-center"
    order = 7
    return position, order


def initialize_plugin(panel_instance):
    """
    Initialize the SwayNC Toggle plugin.
    Args:
        obj: The main panel object (Panel instance).
        app: The main application instance.
    """
    if ENABLE_PLUGIN:
        swaync_plugin = SwayNCTogglePlugin(panel_instance)
        swaync_plugin.create_swaync_button()
        return swaync_plugin


class SwayNCTogglePlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """
        Initialize the plugin.
        Args:
            obj: The main panel object from panel.py
            app: The main application instance
        """

    def create_swaync_button(self):
        """
        Create the SwayNC toggle button.
        """
        # Create the Button
        self.button_swaync = Gtk.Button()
        self.main_widget = (self.button_swaync, "append")
        self.button_swaync.set_icon_name(
            "preferences-system-notifications-symbolic"
        )  # Default icon
        self.button_swaync.add_css_class("top_right_widgets")

        # Load custom icon from config if available
        swaync_icon = (
            self.config.get("panel", {})
            .get("top", {})
            .get("swaync_icon", "liteupdatesnotify")
        )
        self.button_swaync.set_icon_name(self.utils.get_nearest_icon_name(swaync_icon))

        # Connect the button to toggle SwayNC using the "clicked" signal
        self.button_swaync.connect("clicked", self.toggle_swaync)

    def toggle_swaync(self, *_):
        """
        Toggle SwayNC using the `swaync-client -t` command.
        """
        try:
            subprocess.run(["swaync-client", "-t"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error toggling SwayNC: {e}")
