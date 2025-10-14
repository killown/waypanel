def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.color_picker",
        "name": "Color Picker",
        "version": "1.0.0",
        "enabled": True,
        "description": "Configuration for the Color Picker plugin, enabling the global keybind.",
    }


def get_plugin_class():
    KEYBIND_FALLBACK = "<super><shift> KEY_C"
    from src.plugins.core._base import BasePlugin

    class ColorPickerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.keybind = self.get_plugin_setting_add_hint(
                ["keybind"],
                "<ctrl><super><alt> BTN_LEFT",
                (
                    "The key or mouse button combination used to launch the color picker."
                    "Format: <modifier> KEY_NAME or <modifier> BTN_NAME. Example: <super><shift> KEY_C"
                ),
            )
            self.register_keybinding()

        def register_keybinding(self):
            self.wf_helper.register_wayctl_binding(
                self.keybind, KEYBIND_FALLBACK, "--colorpicker"
            )

    return ColorPickerPlugin
