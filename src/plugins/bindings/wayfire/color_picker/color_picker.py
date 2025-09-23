from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

KEYBIND_PRIMARY = "<ctrl><super><alt> BTN_LEFT"
KEYBIND_FALLBACK = "<super><shift> KEY_C"


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    """Initialize the plugin if enabled."""
    if ENABLE_PLUGIN:
        return ColorPickerPlugin(panel_instance)
    return None


class ColorPickerPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

        self.logger.info("ColorPickerPlugin initialized.")
        self.register_keybinding()

    def register_keybinding(self):
        self.wf_helper.register_wayctl_binding(
            KEYBIND_PRIMARY, KEYBIND_FALLBACK, "--colorpicker"
        )
