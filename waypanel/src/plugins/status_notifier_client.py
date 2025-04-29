# The MIT License (MIT)
#
# Copyright (c) 2023 Thiago <24453+killown@users.noreply.github.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from gi.repository import Gtk

# Local imports
from waypanel.src.plugins.core._base import BasePlugin

# Enable or disable the plugin
ENABLE_PLUGIN = True

# Define plugin dependencies (if any)
DEPS = [
    "event_manager",
    "top_panel",
    "status_notifier_server",
]  # Ensure EventManagerPlugin is loaded first


def get_plugin_placement(panel_instance):
    return "top-panel-right", 10, 10


def initialize_plugin(panel_instance):
    """
    Initialize the plugin and return its instance.
    Args:
        panel_instance: The main panel object from panel.py.
    """
    if not ENABLE_PLUGIN:
        panel_instance.logger.info("SystrayClientPlugin is disabled.")
        return None

    # Ensure EventManagerPlugin is loaded
    if "event_manager" not in panel_instance.plugins:
        panel_instance.logger.error("EventManagerPlugin is not loaded. Cannot proceed.")
        return None

    # Create and return the plugin instance
    plugin = SystrayClientPlugin(panel_instance)
    return plugin


class SystrayClientPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.status_notifier_watcher = (
            None  # Will hold the StatusNotifierWatcher instance
        )
        self.subscribe_to_icon_updates()
        self.subscribe_to_removal_events()
        self.status_notifier_host = self.plugins["status_notifier_server"].host
        self.tray_box = Gtk.Box()
        self.main_widget = (self.tray_box, "append")
        self.tray_list = {}

    def subscribe_to_icon_updates(self):
        """
        Subscribe to 'icon_name_updated' events from the IPC server.
        """
        self.ipc_server.add_event_subscriber(
            event_type="tray_icon_name_updated", callback=self.on_icon_name_updated
        )

    def subscribe_to_removal_events(self):
        """
        Subscribe to tray icon removal events.
        """
        self.ipc_server.add_event_subscriber(
            event_type="tray_icon_removed", callback=self.on_tray_icon_removed
        )

    async def on_tray_icon_removed(self, message):
        """
        Handle the removal of a tray icon.
        Args:
            item (StatusNotifierItem): The removed tray icon.
        """
        service_name = message["data"]["service_name"]
        print(f"Tray icon removed for service: {service_name}")
        # remove button from tray
        self.tray_list[service_name].unparent()

    def create_button(self, icon_name):
        button = Gtk.Button.new()
        button.set_icon_name(icon_name)
        self.tray_box.append(button)
        return button

    async def on_icon_name_updated(self, message):
        """
        Handle the 'icon_name_updated' event.
        Args:
            message (dict): The broadcasted message containing the updated icon name.
        """
        self.logger.info(f"Received icon name update: {message}")

        # Extract details from the message
        icon_name = message["data"]["icon_name"]
        object_path = message["data"]["object_path"]
        service_name = message["data"]["service_name"]
        if service_name not in self.tray_list:
            button = self.create_button(icon_name)
            self.tray_list[service_name] = button

    def on_start(self):
        """
        Called when the plugin is started.
        """
        self.logger.info("SystrayClientPlugin has started.")

    def on_stop(self):
        """
        Called when the plugin is stopped or unloaded.
        """
        self.logger.info("SystrayClientPlugin has stopped.")

    def on_reload(self):
        """
        Called when the plugin is reloaded dynamically.
        """
        self.logger.info("SystrayClientPlugin has been reloaded.")

    def on_cleanup(self):
        """
        Called before the plugin is completely removed.
        """
        self.logger.info("SystrayClientPlugin is cleaning up resources.")
