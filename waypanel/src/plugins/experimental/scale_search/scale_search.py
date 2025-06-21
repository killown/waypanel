import subprocess
from src.plugins.core._base import BasePlugin
from gi.repository import GLib
import shutil
import os

# install https://codeberg.org/dnkl/fuzzel to enable the plugin
ENABLE_PLUGIN = shutil.which("fuzzel") is not None
DEPS = ["event_manager"]  # Depends on the event manager to receive events


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    if not ENABLE_PLUGIN:
        panel_instance.logger.info("fuzzel Watcher Plugin is disabled.")
        return None
    return fuzzelWatcherPlugin(panel_instance)


class fuzzelWatcherPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.fuzzel_process = None
        self.scale_is_active = False
        self.subscribe_to_events()

    def subscribe_to_events(self):
        """Subscribe to relevant events using the event manager."""
        if "event_manager" not in self.plugins:
            self.logger.error(
                "Event Manager Plugin is not loaded. Cannot subscribe to events."
            )
            return

        event_manager = self.plugins["event_manager"]

        # Subscribe to plugin activation state changes
        event_manager.subscribe_to_event(
            "plugin-activation-state-changed",
            self.handle_plugin_activation,
        )

        # Subscribe to view geometry changes
        event_manager.subscribe_to_event(
            "view-mapped",
            self.handle_view_mapped,
        )

    def handle_plugin_activation(self, msg):
        """
        Handle activation/deactivation of the scale plugin.
        """
        if msg.get("plugin") != "scale":
            return

        state = msg.get("state")
        if state is True:
            self.scale_is_active = True
            self._start_fuzzel()
        elif state is False:
            self.scale_is_active = False
            self._kill_fuzzel()

    def handle_view_mapped(self, msg):
        """
        Handle 'view-mapped' event.
        toggle scale off when a new view is created.
        """
        # prevent toggling scale when creating a new view when the plugin is not active
        if not self.scale_is_active:
            return

        self.logger.info("New view mapped. Toggling scale off.")
        view = msg.get("view")
        if view:
            if view["role"] == "toplevel":
                try:
                    self.ipc.scale_toggle()  # Toggle scale off
                    self.ipc.set_focus(view["id"])
                except Exception as e:
                    self.logger.error(f"Failed to toggle scale: {e}")

    def _start_fuzzel(self):
        """Start fuzzel as a forked process."""
        if self.fuzzel_process is None or self.fuzzel_process.poll() is not None:
            try:
                current_script_path = os.path.abspath(__file__)
                current_folder_path = os.path.dirname(current_script_path)
                fuzzel_config = os.path.join(current_folder_path, "fuzzel.ini")
                self.fuzzel_process = subprocess.Popen(
                    ["fuzzel", "--hide-before-typing", "--config", fuzzel_config],
                )
                self.logger.info("Started fuzzel.")
            except Exception as e:
                self.logger.error(f"Failed to start fuzzel: {e}")

    def _kill_fuzzel(self):
        """Kill the running fuzzel process."""
        subprocess.run("pkill fuzzel".split())
