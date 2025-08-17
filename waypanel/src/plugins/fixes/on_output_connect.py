# This plugin will restart Waypanel when the primary output is reconnected
# or disconnected.

# NOTE: the following config must to be set.
# [panel]
# primary_output = "Output-Name"

import sys
import os
from gi.repository import GLib
from src.plugins.core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return RestartOnMovePlugin(panel_instance)
    return None


class RestartOnMovePlugin(BasePlugin):
    """Restart Waypanel when the primary output disconnects or reconnects."""

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self._debounce_timeout_id = None
        self.primary_output_name = self.config.get("panel", {}).get("primary_output")
        if not self.primary_output_name:
            self.logger.warning(
                "No 'primary_output' set in config. Plugin will not trigger restarts."
            )
        else:
            self.logger.info(
                f"Monitoring for primary output connect/disconnect: {self.primary_output_name}"
            )

    @subscribe_to_event("output-wset-changed")
    def on_output_wset_changed(self, event_message):
        """React when the primary output connects or disconnects."""
        if not self.primary_output_name:
            return

        try:
            output_data = event_message.get("output-data", {})
            output_name = output_data.get("name")

            if not output_name:
                return

            # Only care about events on the primary output
            if output_name != self.primary_output_name:
                return

            self.logger.info(
                f"output-wset-changed detected on primary output '{output_name}'. Scheduling restart check."
            )

            # Cancel any pending restart
            if self._debounce_timeout_id:
                GLib.source_remove(self._debounce_timeout_id)

            # Use 1000ms to allow full disconnect/reconnect settle
            self._debounce_timeout_id = GLib.timeout_add(1000, self._check_and_restart)

        except Exception as e:
            self.logger.error(f"Error in on_output_wset-changed: {e}", exc_info=True)

    def _check_and_restart(self):
        """After delay, check if primary output is missing or present, then restart."""
        self._debounce_timeout_id = None

        try:
            outputs_list = self.ipc.list_outputs()
            active_output_names = [o.get("name") for o in outputs_list if o.get("name")]

            # If primary output is NOT in active outputs → it was disconnected
            # If primary output IS in active outputs → it was connected
            # In both cases, we want to restart to reinitialize panel on correct output
            if self.primary_output_name not in active_output_names:
                self.logger.info(
                    f"Primary output '{self.primary_output_name}' is now disconnected. Restarting Waypanel."
                )
            else:
                self.logger.info(
                    f"Primary output '{self.primary_output_name}' is now active. Restarting Waypanel."
                )

            # Always restart if event was triggered for primary output
            # If the panel is moved to another output, it will be restarted,
            # the reason is because another output could have a different resolution
            # and the panel would still keep the same size from the last output is was connected
            # to prevent that behaviour, restart the panel on the available output
            self.restart_application()

        except Exception as e:
            self.logger.error(f"Error in delayed restart check: {e}", exc_info=True)

        return False  # Required: stop GLib from repeating

    def restart_application(self):
        """Restart the current Waypanel process."""
        self.logger.info("Restarting Waypanel...")
        try:
            python = sys.executable
            script_path = sys.argv[0]
            if script_path:
                os.execl(python, python, script_path, *sys.argv[1:])
            else:
                os.execl(python, python, *sys.argv)
        except Exception as e:
            self.logger.critical(f"Failed to restart Waypanel: {e}", exc_info=True)
