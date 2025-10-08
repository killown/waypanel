def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.to_empty_workspace",
        "name": "View to Empty Workspace",
        "version": "1.0.0",
        "enabled": True,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    KEYBIND_PRIMARY = "<super> KEY_TAB"
    KEYBIND_FALLBACK = "<super><ctrl> KEY_TAB"

    class MoveViewToEmptyWorkspacePlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.wf_helper.register_wayctl_binding(
                KEYBIND_PRIMARY, KEYBIND_FALLBACK, "--move-view-to-empty-workspace"
            )

    return MoveViewToEmptyWorkspacePlugin
