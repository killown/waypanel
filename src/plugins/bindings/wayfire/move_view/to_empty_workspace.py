def get_plugin_metadata(_):
    about = (
        "Registers a global keybind to quickly move the currently focused "
        "view (window) to the next available empty Wayfire workspace."
    )
    return {
        "id": "org.waypanel.plugin.to_empty_workspace",
        "name": "View to Empty Workspace",
        "version": "1.0.0",
        "enabled": True,
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    KEYBIND_FALLBACK_DEFAULT = "<super><ctrl> KEY_TAB"

    class MoveViewToEmptyWorkspacePlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

        def delay_on_start(self):
            self.add_hint(
                [
                    "Configuration for the keybinds that move a window to an empty workspace."
                ],
                None,
            )
            self.keybind = self.get_plugin_setting_add_hint(
                ["keybind"],
                "<super> KEY_TAB",
                "The primary key or button combination to move the active window to an empty workspace. Format: <modifier> KEY_NAME or <modifier> BTN_NAME (e.g., <super> KEY_W).",
            )
            self.wf_helper.register_wayctl_binding(
                self.keybind,
                KEYBIND_FALLBACK_DEFAULT,
                "--move-view-to-empty-workspace",
            )
            return False

        def on_start(self):
            self.glib.timeout_add_seconds(3, self.delay_on_start)

    return MoveViewToEmptyWorkspacePlugin
