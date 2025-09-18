from src.plugins.core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event

ENABLE_PLUGIN = True

DEPS = [
    "event_manager",
    "on_output_connect",
    "top_panel",
    "bottom_panel",
    "left_panel",
    "right_panel",
]


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return PanelScaleExclusivePlugin(panel_instance)
    return None


class PanelScaleExclusivePlugin(BasePlugin):
    """
    A background plugin that monitors the 'scale' plugin's activation state.
    When scale is activated, it enables exclusive layer mode on ALL four panels (top, bottom, left, right)
    ONLY if the currently focused output matches the output specified by on_output_connect.current_output_name.
    When scale is deactivated, it removes the exclusive layer mode from all panels.
    """

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger.info("PanelScaleExclusivePlugin initialized.")
        # Track current state of exclusive zones to avoid redundant calls
        self.exclusive_state = {
            "top": False,
            "bottom": False,
            "left": False,
            "right": False,
        }
        self.on_output_plugin = self.plugins["on_output_connect"]

    def set_panels_exclusive(self, exclusive=True, size=49):
        """Helper method to set/unset exclusive mode on all four panels."""
        actions = [
            (
                self.top_panel,
                self.set_layer_pos_exclusive
                if exclusive
                else self.unset_layer_pos_exclusive,
            ),
            (
                self.bottom_panel,
                self.set_layer_pos_exclusive
                if exclusive
                else self.unset_layer_pos_exclusive,
            ),
            (
                self.left_panel,
                self.set_layer_pos_exclusive
                if exclusive
                else self.unset_layer_pos_exclusive,
            ),
            (
                self.right_panel,
                self.set_layer_pos_exclusive
                if exclusive
                else self.unset_layer_pos_exclusive,
            ),
        ]

        for panel, action in actions:
            if exclusive:
                self.update_widget_safely(action, panel, size)
            else:
                self.update_widget_safely(action, panel)

        # Update internal state
        state_value = True if exclusive else False
        self.exclusive_state.update(
            {
                "top": state_value,
                "bottom": state_value,
                "left": state_value,
                "right": state_value,
            }
        )

    def on_scale_activated(self):
        """Handle scale activation: enable exclusive zones only if focused output matches on_output_connect's target."""
        # 1. Get the output name that the panels are bound to (REQUIRED SOURCE OF TRUTH)
        target_output_name = self.on_output_plugin.current_output_name
        if not target_output_name:
            target_output_name = self.on_output_plugin.primary_output_name

        # 2. Get the currently focused output
        focused_output_name = self.ipc.get_focused_output()["name"]

        # 3. Only enable exclusive mode if they match
        if target_output_name and focused_output_name == target_output_name:
            self.logger.info(
                f"Scale activated on target output '{target_output_name}'. Enabling exclusive zones."
            )
            self.set_panels_exclusive(exclusive=True, size=49)
        else:
            self.logger.debug(
                f"Scale activated but on output '{focused_output_name}' != target '{target_output_name}'. "
                "Skipping exclusive zone."
            )

    def on_scale_deactivated(self):
        """Handle scale deactivation: remove exclusive zones from all panels."""
        self.logger.info("Scale deactivated. Disabling exclusive zones on all panels.")
        self.set_panels_exclusive(exclusive=False)

    @subscribe_to_event("plugin-activation-state-changed")
    def handle_plugin_event(self, msg):
        """Subscribe to 'plugin-activation-state-changed' events."""
        if msg["event"] == "plugin-activation-state-changed":
            if msg["plugin"] == "scale":
                if msg["state"] is True:
                    self.on_scale_activated()
                elif msg["state"] is False:
                    self.on_scale_deactivated()
                else:
                    self.logger.warning(
                        f"Unknown state value for scale plugin: {msg['state']}"
                    )

    def about(self):
        """
        Panel Scale-Exclusive Plugin
        ============================

        Purpose
        -------
        This plugin was created to solve a layout conflict that appears when using
        the Scale effect (the overview of all windows) in a multi-panel setup.
        During Scale, normal panels can overlap or allow other surfaces to intrude,
        breaking the visual clarity of the workspace.

        Reason for Creation
        -------------------
        By temporarily placing every panel (top, bottom, left and right) in
        exclusive layer mode only while Scale is active—and only on the monitor
        where Scale is running—the plugin ensures that panels keep their reserved
        screen space. This prevents accidental overlaps, keeps the Scale grid clean
        and consistent, and restores the panels to normal as soon as the effect ends.

        Benefit
        -------
        Users experience a smooth and unobstructed Scale animation without panels
        jumping or being covered, while still regaining the usual flexible panel
        behavior once Scale deactivates.
        """
        return self.about.__doc__
