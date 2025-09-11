# NOTE: the following config must to be set.
# [panel]
# primary_output = "Output-Name"
#
from gi.repository import GLib
from gi.repository import Gtk4LayerShell as LayerShell
from src.core.create_panel import (
    get_monitor_info,
)
from src.plugins.core._base import BasePlugin
from src.plugins.core.event_handler_decorator import subscribe_to_event

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return PanelOutputMoverPlugin(panel_instance)
    return None


class PanelOutputMoverPlugin(BasePlugin):
    """Move the panel to the first available output when its current one is disabled."""

    PLUGIN_NAME = "panel_output_mover"

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.panel = panel_instance
        self.current_output_name = None
        self._debounce_timeout_id = None

        self.primary_output_name = self.config.get("panel", {}).get("primary_output")
        if self.primary_output_name:
            self.logger.info(
                f"Primary output preference set to: {self.primary_output_name}"
            )
        else:
            self.logger.info("No primary output set. Will use first available output.")
            self.primary_output_name = [i for i in self.ipc.list_outputs()][0]["name"]

        # Schedule initial output assignment
        GLib.idle_add(self._apply_initial_output)

    def _apply_initial_output(self):
        """Assign panel to the best available output on startup."""
        try:
            self._set_panel_monitor()
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
        self.logger.debug(f"[{self.PLUGIN_NAME}] Output layout changed. Re-evaluating.")
        outputs = event_message["configuration"]
        output = [i for i in outputs if i["name"] == self.primary_output_name][0]
        default_output_enabled = output["output-id"] != -1
        default_output_enabled = output["source"] != "dpms"
        self.current_output_name = self.primary_output_name

        if not default_output_enabled:
            self.current_output_name = [i for i in outputs if i["source"] != "dpms"][0][
                "name"
            ]

        if self._debounce_timeout_id:
            GLib.source_remove(self._debounce_timeout_id)

        self._debounce_timeout_id = GLib.timeout_add(100, self._debounced_update)

    def _debounced_update(self):
        """Perform the actual update after debounce delay."""
        self._debounce_timeout_id = None
        try:
            self._set_panel_monitor()
        except Exception as e:
            self.logger.error(f"[{self.PLUGIN_NAME}] Error updating panel output: {e}")
        return False  # Run only once

    def get_target_monitor(self, monitors):
        """Determine which monitor will be the default"""

        return next(
            (
                monitor
                for name, monitor in monitors.items()
                if name == self.current_output_name
            ),
            None,
        )

    def _set_panel_monitor(self):
        """Update the GTK Layer Shell monitor for the panel window."""
        monitors = get_monitor_info()
        monitor = self.get_target_monitor(monitors)
        if monitor:
            LayerShell.set_monitor(self.top_panel, monitor["monitor"])
            LayerShell.set_monitor(self.left_panel, monitor["monitor"])
            LayerShell.set_monitor(self.right_panel, monitor["monitor"])
            LayerShell.set_monitor(self.bottom_panel, monitor["monitor"])
