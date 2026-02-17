def get_plugin_metadata(_):
    about = "Automatically moves the panel to a valid monitor when the current one is disabled."
    return {
        "id": "org.waypanel.plugin.on_output_connect",
        "name": "Panel Output Mover",
        "version": "1.0.0",
        "enabled": True,
        "deps": ["event_manager"],
        "description": about,
    }


def get_plugin_class():
    from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore
    from src.core.create_panel import get_monitor_info, get_target_monitor
    from src.plugins.core._base import BasePlugin
    from src.plugins.core.event_handler_decorator import subscribe_to_event

    class PanelOutputMoverPlugin(BasePlugin):
        """Move the panel to the first available output when its current one is disabled."""

        PLUGIN_NAME = "panel_output_mover"

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.panel = panel_instance

        def on_start(self):
            self.current_output_name = None
            self._debounce_timeout_id = None
            self.current_output_name = None
            self.primary_output_name = self.config_handler.get_root_setting(
                ["org.waypanel.panel", "primary_output", "name"],
                self.get_first_output(),
            )
            self.add_hint(
                ["Configuration for the behavior of moving the panel between outputs."],
                None,
            )
            self.debounce_delay_ms = self.get_plugin_setting_add_hint(
                ["debounce_delay_ms"],
                100,
                "Delay (in milliseconds) before moving the panel after an output layout change. This prevents flickering during transient monitor state changes.",
            )
            if self.primary_output_name:
                self.logger.info(
                    f"Primary output preference set to: {self.primary_output_name}"
                )
            else:
                self.logger.info(
                    "No primary output set. Will use first available output."
                )
                self.primary_output_name = self.get_first_output()

            self.glib.idle_add(self._apply_initial_output)

        def get_first_output(self):
            outputs = self.ipc.list_outputs()
            return outputs[0]["name"]

        def _apply_initial_output(self):
            """Assign panel to the best available output on startup."""
            try:
                self._set_panel_on_output()
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Initial output assignment completed."
                )
            except Exception as e:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Error during initial assignment: {e}"
                )

        @subscribe_to_event("output-layout-changed")
        def on_output_layout_changed(self, event_message):
            """React when outputs layout change."""
            self.logger.debug(
                f"[{self.PLUGIN_NAME}] Output layout changed. Re-evaluating."
            )
            outputs = event_message["configuration"]
            if not outputs:
                self.logger.warning("No outputs detected after layout change.")
                return
            current_output = next(
                (i for i in outputs if i["name"] == self.primary_output_name), None
            )
            if not current_output:
                self.logger.warning(
                    f"Primary output '{self.primary_output_name}' not found. Falling back to first available output."
                )
                first_available = next(
                    (i for i in outputs if i.get("source") != "dpms"), None
                )
                if first_available:
                    self.current_output_name = first_available["name"]
                else:
                    self.logger.error("No available outputs to move the panel to.")
                    return
            else:
                is_enabled = (
                    current_output.get("output-id", -1) != -1
                    and current_output.get("source") != "dpms"
                )
                if not is_enabled:
                    self.logger.info(
                        f"Primary output '{self.primary_output_name}' is disabled. Finding a new output."
                    )
                    first_available = next(
                        (i for i in outputs if i.get("source") != "dpms"), None
                    )
                    if first_available:
                        self.current_output_name = first_available["name"]
                    else:
                        self.logger.error(
                            "Primary output is disabled and no other outputs are available."
                        )
                        return
                else:
                    self.current_output_name = self.primary_output_name
            if self._debounce_timeout_id:
                self.glib.source_remove(self._debounce_timeout_id)
            target_output = next(
                (i for i in outputs if i["name"] == self.current_output_name), None
            )
            if target_output and not self.wf_helper.has_output_fullscreen_view(
                target_output["output-id"]
            ):
                self._debounce_timeout_id = self.glib.timeout_add(
                    self.debounce_delay_ms, self._debounced_update
                )
            else:
                self.logger.debug("Fullscreen view detected, not moving panel.")

        def _debounced_update(self):
            """Perform the actual update after debounce delay."""
            self._debounce_timeout_id = None
            try:
                self._set_panel_on_output()
            except Exception as e:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Error updating panel output: {e}"
                )
            return False

        def _set_panel_on_output(self):
            """Update the GTK Layer Shell monitor for the panel window."""
            monitors = get_monitor_info()
            monitor = get_target_monitor(self.config_handler.config_data, monitors)
            if not monitor:
                self.logger.error("Target monitor not found. Cannot set panel output.")
                return
            monitor_gdk_obj = monitor.get("monitor")
            if not monitor_gdk_obj:
                self.logger.warning("on_output_connect could not get the output")
            monitor_name = monitor_gdk_obj.get_connector()  # pyright: ignore
            output = next(
                (i for i in self.ipc.list_outputs() if i["name"] == monitor_name), None
            )
            if not output:
                self.logger.error(f"IPC output for monitor '{monitor_name}' not found.")
                return
            geo = output.get("geometry")
            if not geo:
                self.logger.error(f"Geometry for output '{monitor_name}' not found.")
                return
            output_width = geo.get("width")
            user_defined_height_top_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "top", "height"], default_value=32
            )
            user_defined_width_top_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "top", "width"],
                default_value=output_width,
            )
            user_defined_height_left_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "left", "height"], default_value=32
            )
            user_defined_width_left_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "left", "width"], default_value=32
            )
            user_defined_height_right_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "right", "height"], default_value=32
            )
            user_defined_width_right_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "right", "width"], default_value=32
            )
            user_defined_height_bottom_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "bottom", "height"], default_value=32
            )
            user_defined_width_bottom_panel = self.config_handler.get_root_setting(
                key_path=["org.waypanel.panel", "bottom", "width"],
                default_value=output_width,
            )
            LayerShell.set_monitor(self.top_panel, monitor_gdk_obj)
            LayerShell.set_monitor(self.left_panel, monitor_gdk_obj)
            LayerShell.set_monitor(self.right_panel, monitor_gdk_obj)
            LayerShell.set_monitor(self.bottom_panel, monitor_gdk_obj)
            self.top_panel.set_default_size(
                user_defined_width_top_panel, user_defined_height_top_panel
            )
            self.left_panel.set_default_size(
                user_defined_width_left_panel, user_defined_height_left_panel
            )
            self.right_panel.set_default_size(
                user_defined_width_right_panel, user_defined_height_right_panel
            )
            self.bottom_panel.set_default_size(
                user_defined_width_bottom_panel, user_defined_height_bottom_panel
            )

        def code_explanation(self):
            """
            This plugin ensures the panel remains visible by automatically moving it
            to an active output when the current one is disconnected or disabled.
            The core logic involves:
            1.  **Initial Assignment:** On startup, the panel is placed on a preferred
                (if configured) or the first available monitor.
            2.  **Event Listening:** It subscribes to an "output-layout-changed" event,
                t # pyright: ignoreriggering a re-evaluation of the display setup whenever a monitor's
                status changes.
            3.  **Dynamic Relocation:** If the primary or current monitor is no longer
                active, the plugin finds the first available, non-DPMS output and
                reassigns the panel to it using LayerShell.
            4.  **Debouncing:** A configurable delay is used to prevent the panel from
                rapidly flickering during transient display changes.
            """
            return self.code_explanation.__doc__

    return PanelOutputMoverPlugin
