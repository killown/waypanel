from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

KEYBIND_PRIMARY = "<super> KEY_TAB"
KEYBIND_FALLBACK = "<super><ctrl> KEY_TAB"


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    """Initialize the plugin if enabled."""
    if ENABLE_PLUGIN:
        return MoveViewToEmptyWorkspacePlugin(panel_instance)
    return None


class MoveViewToEmptyWorkspacePlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.utils.register_wayctl_binding(
            KEYBIND_PRIMARY, KEYBIND_FALLBACK, "--move-view-to-empty-workspace"
        )
