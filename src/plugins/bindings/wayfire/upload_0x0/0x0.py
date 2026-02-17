def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.uplo0x0",
        "name": "0x0 Uploader",
        "version": "1.0.0",
        "enabled": True,
        "container": "background",
        "deps": ["event_manager"],
        "description": "Background clipboard uploader for 0x0.st using wayctl.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class Uplo0x0Plugin(BasePlugin):
        def delay_on_start(self):
            """Lifecycle hook to register the binding."""
            self.keybind = self.get_plugin_setting_add_hint(
                ["keybind"],
                "<ctrl><super><alt> KEY_0",
                "Key combination to upload clipboard to 0x0.st",
            )

            self.register_keybinding()
            return False

        def on_start(self):
            self.glib.timeout_add_seconds(3, self.delay_on_start)

        def register_keybinding(self):
            """
            Registers the binding via wf_helper.
            The command executed will be: wayctl --pastebin
            """
            self.wf_helper.register_wayctl_binding(
                self.keybind, "<ctrl><super><alt> KEY_0", "--pastebin"
            )

    return Uplo0x0Plugin
