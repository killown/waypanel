def get_plugin_metadata(_):
    about = (
        "Registers global keybinds using the Wayfire IPC to quickly capture "
        "screenshots of the screen, a focused window, or a selected area."
    )
    return {
        "id": "org.waypanel.plugin.screenshot",
        "name": "Screenshot",
        "version": "1.0.0",
        "enabled": True,
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    DEFAULT_FOCUSED_VIEW = "KEY_SYSRQ"
    DEFAULT_FOCUSED_OUTPUT = "<ctrl><shift> KEY_SYSRQ"
    DEFAULT_SLURP = "<alt> KEY_SYSRQ"
    DEFAULT_SLURP_FOCUSED_VIEW = "<ctrl><alt> KEY_SYSRQ"

    class ScreenshotPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.add_hint(
                [
                    "Configuration for the keybinds that trigger various screenshot modes."
                ],
                None,
            )
            self.keybind_focused_view = self.get_plugin_setting_add_hint(
                ["keybind_focused_view"],
                DEFAULT_FOCUSED_VIEW,
                "Keybind to capture the currently focused window/view. (Default: SYSRQ/PrtScn)",
            )
            self.keybind_focused_output = self.get_plugin_setting_add_hint(
                ["keybind_focused_output"],
                DEFAULT_FOCUSED_OUTPUT,
                "Keybind to capture the currently focused output (monitor).",
            )
            self.keybind_slurp = self.get_plugin_setting_add_hint(
                ["keybind_slurp"],
                DEFAULT_SLURP,
                "Keybind to capture a user-selected area of the screen (using slurp).",
            )
            self.keybind_slurp_focused_view = self.get_plugin_setting_add_hint(
                ["keybind_slurp_focused_view"],
                DEFAULT_SLURP_FOCUSED_VIEW,
                "Keybind to open slurp in view-select mode, capturing a specific window after selection.",
            )
            self.logger.info("ScreenshotPlugin initialized.")
            self.register_keybindings()

        def register_keybindings(self):
            self.wf_helper.register_wayctl_binding(
                self.keybind_focused_view, None, "--screenshot focused view"
            )
            self.wf_helper.register_wayctl_binding(
                self.keybind_focused_output, None, "--screenshot focused output"
            )
            self.wf_helper.register_wayctl_binding(
                self.keybind_slurp, None, "--screenshot slurp"
            )
            self.wf_helper.register_wayctl_binding(
                self.keybind_slurp_focused_view,
                None,
                "--screenshot slurp focused view",
            )

    return ScreenshotPlugin
