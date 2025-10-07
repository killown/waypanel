def get_plugin_metadata(_):
    return {
        "enabled": True,
    }


def get_plugin_class():
    KEYBIND_PRIMARY = "<ctrl><super><alt> BTN_LEFT"
    KEYBIND_FALLBACK = "<super><shift> KEY_C"
    from src.plugins.core._base import BasePlugin

    class ColorPickerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

            self.logger.info("ColorPickerPlugin initialized.")
            self.register_keybinding()

        def register_keybinding(self):
            self.wf_helper.register_wayctl_binding(
                KEYBIND_PRIMARY, KEYBIND_FALLBACK, "--colorpicker"
            )

    return ColorPickerPlugin
