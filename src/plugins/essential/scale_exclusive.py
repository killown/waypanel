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
        scale_exclusive = call_plugin_class()
        return scale_exclusive(panel_instance)


def call_plugin_class():
    from src.plugins.core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event

    class PanelScaleExclusivePlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.logger.info("PanelScaleExclusivePlugin initialized.")
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
            target_output_name = self.on_output_plugin.current_output_name
            if not target_output_name:
                target_output_name = self.on_output_plugin.primary_output_name
            focused_output_name = self.ipc.get_focused_output()["name"]
            if target_output_name and focused_output_name == target_output_name:
                self.set_panels_exclusive(exclusive=True, size=49)
            else:
                self.logger.debug(
                    f"Scale activated but on output '{focused_output_name}' != target '{target_output_name}'. "
                    "Skipping exclusive zone."
                )

        def on_scale_deactivated(self):
            """Handle scale deactivation: remove exclusive zones from all panels."""
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
            """Monitors the 'scale' plugin to enable or disable exclusive layer mode on panels."""
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin coordinates with the 'scale' plugin to manage panel layer behavior.
            Its core logic is centered on **synchronizing panel exclusivity with the scale effect**:
            1.  **Event Subscription**: It listens for activation and deactivation events from the 'scale' plugin.
            2.  **Conditional Activation**: When 'scale' is activated, the plugin checks if the
                currently focused monitor is the same as the one the panels are
                configured for.
            3.  **Exclusive Mode**: If the monitors match, it sets all four panels (top,
                bottom, left, right) to exclusive layer mode. This prevents windows from
                overlapping the panels during the 'scale' effect.
            4.  **State Reset**: When 'scale' is deactivated, the exclusive layer mode is
                removed from all panels, returning them to their normal state.
            """
            return self.code_explanation.__doc__

    return PanelScaleExclusivePlugin
