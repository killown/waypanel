from src.plugins.core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event

ENABLE_PLUGIN = True
DEPS = ["event_manager"]


def get_plugin_placement(panel_instance):
    """This is a background plugin with no UI."""
    return "background"


def initialize_plugin(panel_instance):
    """Initialize the plugin if enabled."""
    if ENABLE_PLUGIN:
        return ScaleFocusManagerPlugin(panel_instance)
    return None


class ScaleFocusManagerPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger.info("ScaleFocusManagerPlugin initialized.")
        self.scale_active_outputs = {}  # Track which outputs have scale active
        self.last_focused_output_id = None  # Track the last focused output

    @subscribe_to_event("output-gain-focus")
    def on_output_gain_focus(self, event_message):
        """Handle when an output gains focus."""
        try:
            if "output" not in event_message:
                return

            current_output = event_message["output"]
            current_output_id = current_output["id"]

            # If we have a previous focused output and scale was active on it
            if (
                self.last_focused_output_id
                and self.last_focused_output_id != current_output_id
            ):
                if (
                    self.last_focused_output_id in self.scale_active_outputs
                    and self.scale_active_outputs[self.last_focused_output_id]
                ):
                    self.logger.info(
                        f"Scale was active on output {self.last_focused_output_id}, toggling it off"
                    )
                    # Toggle scale off on the previous output
                    self.ipc.scale_toggle(self.last_focused_output_id)

                    # the issue is that the last focused output id toggle will make the current view lose focus
                    # so we toggle twice so fast that will not take any toggle effect and yet fix the current view focus
                    # NOTE: set_focus() is not working in this case
                    self.ipc.scale_toggle(current_output_id)
                    self.ipc.scale_toggle(current_output_id)
                    # Update our tracking
                    self.scale_active_outputs[self.last_focused_output_id] = False

            # Update last focused output
            self.last_focused_output_id = current_output_id

        except Exception as e:
            self.logger.error(f"Error handling output-gain-focus event: {e}")

    @subscribe_to_event("plugin-activation-state-changed")
    def on_plugin_activation_changed(self, event_message):
        """Handle plugin activation state changes, specifically for scale plugin."""
        try:
            if event_message.get("plugin") != "scale":
                return

            output_id = event_message.get("output")
            state = event_message.get("state")

            if output_id is not None:
                # Track scale state for this output
                self.scale_active_outputs[output_id] = state
                state_str = "activated" if state else "deactivated"
                self.logger.info(f"Scale plugin {state_str} on output {output_id}")

        except Exception as e:
            self.logger.error(
                f"Error handling plugin-activation-state-changed event: {e}"
            )
