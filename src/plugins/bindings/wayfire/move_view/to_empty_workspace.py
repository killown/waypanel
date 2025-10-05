ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    """Initialize the plugin if enabled."""
    if ENABLE_PLUGIN:
        mv_view = call_plugin_class()
        return mv_view(panel_instance)


def call_plugin_class():
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
