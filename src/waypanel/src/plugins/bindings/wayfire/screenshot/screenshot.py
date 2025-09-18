from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

# Keybindings
BINDING_SCREENSHOT_FOCUSED_VIEW = "KEY_SYSRQ"
BINDING_SCREENSHOT_FOCUSED_OUTPUT = "<ctrl><shift> KEY_SYSRQ"
BINDING_SCREENSHOT_SLURP = "<alt> KEY_SYSRQ"
BINDING_SCREENSHOT_SLURP_FOCUSED_VIEW = "<ctrl><alt> KEY_SYSRQ"


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return ScreenshotPlugin(panel_instance)
    return None


class ScreenshotPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger.info("ScreenshotPlugin initialized.")
        self.register_keybindings()

    def register_keybindings(self):
        self.utils.register_wayctl_binding(
            BINDING_SCREENSHOT_FOCUSED_VIEW, None, "--screenshot focused view"
        )
        self.utils.register_wayctl_binding(
            BINDING_SCREENSHOT_FOCUSED_OUTPUT, None, "--screenshot focused output"
        )
        self.utils.register_wayctl_binding(
            BINDING_SCREENSHOT_SLURP, None, "--screenshot slurp"
        )
        self.utils.register_wayctl_binding(
            BINDING_SCREENSHOT_SLURP_FOCUSED_VIEW,
            None,
            "--screenshot slurp focused view",
        )
