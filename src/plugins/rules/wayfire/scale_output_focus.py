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

        except Exception as e:
            self.logger.error(
                f"Error handling plugin-activation-state-changed event: {e}"
            )

    def about(self):
        """
        A background plugin that manages the state of the scale view
        in a multi-monitor environment, automatically deactivating it
        on unfocused outputs.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this plugin is a reactive, event-driven
        architecture designed for multi-monitor window management.
        Its key principles are:

        1.  **Event Subscription**: The plugin operates as a background
            service, subscribing to system events using the
            `@subscribe_to_event` decorator. It specifically listens
            for `output-gain-focus` to know when a monitor becomes
            active and `plugin-activation-state-changed` to track
            the state of the `scale` plugin on each output.

        2.  **Output State Management**: It maintains an internal
            state dictionary, `self.scale_active_outputs`, which
            acts as a simple state machine. By listening to `scale`
            plugin events, it accurately tracks which outputs currently
            have the scale view active.

        3.  **Cross-Plugin Control**: When a monitor gains focus, the
            plugin references its state tracker to determine if the
            scale view was active on the *previously* focused monitor.
            If it was, it uses an Inter-Process Communication (IPC)
            method, `self.ipc.scale_toggle`, to programmatically
            deactivate the scale view on that old output, ensuring
            a clean user experience.
        """
        return self.code_explanation.__doc__
