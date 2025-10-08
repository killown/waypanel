def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.screenshot",
        "name": "Screenshot",
        "version": "1.0.0",
        "enabled": True,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    BINDING_SCREENSHOT_FOCUSED_VIEW = "KEY_SYSRQ"
    BINDING_SCREENSHOT_FOCUSED_OUTPUT = "<ctrl><shift> KEY_SYSRQ"
    BINDING_SCREENSHOT_SLURP = "<alt> KEY_SYSRQ"
    BINDING_SCREENSHOT_SLURP_FOCUSED_VIEW = "<ctrl><alt> KEY_SYSRQ"

    class ScreenshotPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.logger.info("ScreenshotPlugin initialized.")
            self.register_keybindings()

        def register_keybindings(self):
            self.wf_helper.register_wayctl_binding(
                BINDING_SCREENSHOT_FOCUSED_VIEW, None, "--screenshot focused view"
            )
            self.wf_helper.register_wayctl_binding(
                BINDING_SCREENSHOT_FOCUSED_OUTPUT, None, "--screenshot focused output"
            )
            self.wf_helper.register_wayctl_binding(
                BINDING_SCREENSHOT_SLURP, None, "--screenshot slurp"
            )
            self.wf_helper.register_wayctl_binding(
                BINDING_SCREENSHOT_SLURP_FOCUSED_VIEW,
                None,
                "--screenshot slurp focused view",
            )

    return ScreenshotPlugin
