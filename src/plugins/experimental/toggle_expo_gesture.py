def get_plugin_metadata(_):
    """
    Return metadata for the Toggle Expo plugin.
    """
    about = (
        "A plugin that toggles the Wayfire Expo mode, showing all workspaces "
        "in a wall view for easier navigation."
    )
    return {
        "id": "org.waypanel.plugin.toggle_expo",
        "name": "Expo Mode",
        "version": "1.0.1",
        "enabled": True,
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class ToggleExpoPlugin(BasePlugin):
        """
        Plugin that enables toggling the Wayfire expo view via panel gestures.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.gestures_setup_plugin = None

        def on_start(self):
            """
            Initialize the plugin setup.
            """
            self.setup_plugin()

        def setup_plugin(self):
            """
            Start the periodic check for the gestures setup plugin.
            """
            self.glib.timeout_add_seconds(1, self.check_for_gestures_setup)

        def check_for_gestures_setup(self):
            """
            Check if the gestures_setup plugin is loaded and attach the action.

            Returns:
                bool: True if the plugin is not yet found (to continue the timer),
                      False otherwise.
            """
            if "gestures_setup" in self.obj.plugin_loader.plugins:
                self.gestures_setup_plugin = self.plugins["gestures_setup"]
                self.append_middle_click_action()
                return False
            return True

        def toggle_expo(self):
            """
            Execute the toggle expo IPC command.
            """
            self.ipc.toggle_expo()

        def append_middle_click_action(self):
            """
            Append the 'toggle_expo' action to the middle-click gesture
            in the full section of the top panel.
            """
            callback_name = "pos_full_middle_click"
            if self.gestures_setup_plugin:
                self.gestures_setup_plugin.append_action(  # pyright: ignore
                    callback_name=callback_name,
                    action=self.toggle_expo,
                )

    return ToggleExpoPlugin
