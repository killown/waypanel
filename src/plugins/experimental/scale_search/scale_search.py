import subprocess
from src.plugins.core._base import BasePlugin
import shutil
import os

# install https://codeberg.org/dnkl/fuzzel to enable the plugin
ENABLE_PLUGIN = shutil.which("fuzzel") is not None


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

    def about(self):
        """
        This is a background plugin that integrates the `fuzzel` application
        launcher with the `scale` Wayfire plugin. Its primary function is to
        launch `fuzzel` when `scale` is activated and automatically close it
        when `scale` is deactivated or when a new application window is opened.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The `fuzzelWatcherPlugin` operates as an **event-driven background service**.
        It uses the `event_manager` to monitor the state of the Wayfire compositor.

        The core logic is implemented in two main event handlers:

        1.  **`handle_plugin_activation`**: This method listens for changes in
            the `plugin-activation-state-changed` event. When the
            `scale` plugin is activated (the state is `True`), it triggers
            the private method `_start_fuzzel()` to launch the `fuzzel`
            process. Conversely, if `scale` is deactivated, it calls
            `_kill_fuzzel()` to terminate `fuzzel`, ensuring it only runs
            when needed.

        2.  **`handle_view_mapped`**: This handler responds to the
            `view-mapped` event, which is emitted whenever a new window
            is created. The plugin checks if the newly mapped view is a
            `toplevel` window. If it is and the `scale` plugin is currently
            active, it automatically toggles `scale` off and moves focus
            to the new window using the `self.ipc.scale_toggle()` and
            `self.ipc.set_focus()` calls. This creates a seamless workflow
            where activating `scale` opens `fuzzel` and selecting an
            application from `fuzzel` closes `scale` and focuses the new app.
        """
        return self.code_explanation.__doc__
