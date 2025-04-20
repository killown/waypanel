import os
import subprocess
from gi.repository import Gtk

import toml

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """
    Define the plugin's position and order.
    Returns:
        tuple: (position, order)
    """
    position = "center"
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


class SwayNCTogglePlugin:
    def __init__(self, panel_instance):
        """
        Initialize the plugin.
        Args:
            obj: The main panel object from panel.py
            app: The main application instance
        """
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.utils = self.obj.utils
        self._setup_config_paths()

    def append_widget(self):
        return self.button_swaync

    def _setup_config_paths(self):
        """
        Set up configuration paths based on the user's home directory.
        """
        self.home = os.path.expanduser("~")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.waypanel_cfg = os.path.join(self.config_path, "waypanel.toml")

    def create_swaync_button(self):
        """
        Create the SwayNC toggle button.
        """
        # Create the Button
        self.button_swaync = Gtk.Button()
        self.button_swaync.set_icon_name(
            "preferences-system-notifications-symbolic"
        )  # Default icon
        self.button_swaync.add_css_class("top_right_widgets")

        # Load custom icon from config if available
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
        if os.path.exists(waypanel_config_path):
            with open(waypanel_config_path, "r") as f:
                config = toml.load(f)
            swaync_icon = (
                config.get("panel", {})
                .get("top", {})
                .get("swaync_icon", "liteupdatesnotify")
            )
            self.button_swaync.set_icon_name(
                self.utils.get_nearest_icon_name(swaync_icon)
            )

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
