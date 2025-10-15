def get_plugin_metadata(_):
    about = """
            A background plugin designed for multi-monitor Wayland environments.
            It ensures that the 'scale' view (window overview) automatically
            deactivates on a monitor when focus shifts to a different monitor,
            preventing stale scale views on unfocused outputs.
            """
    return {
        "id": "org.waypanel.plugin.scale_output",
        "name": "Scale Output",
        "version": "1.0.0",
        "enabled": True,
        "container": "background",
        "deps": ["event_manager"],
        "description": about,
    }


def get_plugin_class():
    """
    The factory function for the ScaleFocusManagerPlugin class.
    All necessary imports are deferred here to ensure fast top-level loading.
    """
    from src.plugins.core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event
    from typing import Dict, Any, Optional

    class ScaleFocusManagerPlugin(BasePlugin):
        """
        A reactive background service that manages the scale view state across
        multiple monitors by toggling the scale view off on the previously focused
        output when focus shifts to a new one.
        """

        def __init__(self, panel_instance: Any):
            """
            Initializes the plugin state. Lifecycle methods on_start and on_stop
            handle activation/deactivation logic.
            Args:
                panel_instance: The main panel instance.
            """
            super().__init__(panel_instance)
            self.scale_active_outputs: Dict[str, bool] = {}
            self.last_focused_output_id: Optional[str] = None

        def on_start(self) -> None:
            """Logs plugin startup."""
            self.logger.info("ScaleFocusManagerPlugin initialized and started.")

        def on_stop(self) -> None:
            """
            The primary deactivation method. Cleans up internal state.
            Note: We do not attempt to forcibly deactivate any remaining scale views,
            as the user may be relying on the compositor's own cleanup. We just clear state.
            """
            self.logger.info("ScaleFocusManagerPlugin stopping. Clearing state.")
            self.scale_active_outputs.clear()
            self.last_focused_output_id = None

        @subscribe_to_event("output-gain-focus")
        def on_output_gain_focus(self, event_message: Dict[str, Any]) -> None:
            """
            Handles when an output gains focus. Checks if the previous output
            had scale active and toggles it off if necessary.
            """
            try:
                current_output: Optional[Dict[str, Any]] = event_message.get("output")
                if not current_output:
                    return
                current_output_id: Optional[str] = current_output.get("id")
                if (
                    self.last_focused_output_id
                    and self.last_focused_output_id != current_output_id
                ):
                    prev_id = self.last_focused_output_id
                    if self.scale_active_outputs.get(prev_id, False):
                        self.logger.info(
                            f"Scale was active on output {prev_id}, toggling it off due to focus shift."
                        )

                        def run_scale_toggle(output_id: str):
                            try:
                                self.ipc.scale_toggle(output_id)
                            except Exception as e:
                                self.logger.error(
                                    f"Failed to toggle scale off on {output_id}: {e}"
                                )

                        self.run_in_thread(run_scale_toggle, prev_id)
                        self.scale_active_outputs[prev_id] = False
                if current_output_id:
                    self.last_focused_output_id = current_output_id
            except Exception as e:
                self.logger.error(f"Error handling output-gain-focus event: {e}")

        @subscribe_to_event("plugin-activation-state-changed")
        def on_plugin_activation_changed(self, event_message: Dict[str, Any]) -> None:
            """
            Handles plugin activation state changes, specifically tracking the
            scale plugin's state per output.
            """
            try:
                if event_message.get("plugin") != "scale":
                    return
                output_id: Optional[str] = event_message.get("output")
                state: Optional[bool] = event_message.get("state")
                if output_id is not None and state is not None:
                    self.scale_active_outputs[output_id] = state
            except Exception as e:
                self.logger.error(
                    f"Error handling plugin-activation-state-changed event: {e}"
                )

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
                tracks the activation state of the scale feature for
                each physical output (monitor). It also tracks the
                `self.last_focused_output_id`.
            3.  **Cross-Plugin Control**: When the focused output changes,
                the `on_output_gain_focus` method checks if the previous
                output had an active scale view. If so, it uses the IPC
                method `self.ipc.scale_toggle` (run in a separate thread
                via `self.run_in_thread` to avoid blocking the event loop)
                to programmatically deactivate the scale view on that old
                output, ensuring a clean user experience across monitors.
            """
            return self.code_explanation.__doc__

    return ScaleFocusManagerPlugin
