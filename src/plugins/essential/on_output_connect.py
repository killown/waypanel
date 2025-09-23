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
        self.current_output_name = None
        self.primary_output_name = (
            self.config_handler.config_data.get("panel", {})
            .get("primary_output")
            .get("output_name")
        )
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
        self.logger.debug(f"[{self.PLUGIN_NAME}] Output layout changed. Re-evaluating.")
        outputs = event_message["configuration"]
        output = [i for i in outputs if i["name"] == self.primary_output_name][0]
        default_output_enabled = output["output-id"] != -1
        default_output_enabled = output["source"] != "dpms"

        self.current_output_name = self.primary_output_name

        if not default_output_enabled:
            self.current_output = [i for i in outputs if i["source"] != "dpms"][0]
            if self.current_output:
                self.current_output_name = self.current_output["name"]

        if self._debounce_timeout_id:
            GLib.source_remove(self._debounce_timeout_id)

        current_output = [i for i in outputs if i["name"] == self.current_output_name][
            0
        ]
        # panel wont move to the current output if the current workspace has any fullscreen view
        if not self.wf_helper.has_output_fullscreen_view(current_output["output-id"]):
            self._debounce_timeout_id = GLib.timeout_add(100, self._debounced_update)

    def _debounced_update(self):
        """Perform the actual update after debounce delay."""
        self._debounce_timeout_id = None
        try:
            self._set_panel_on_output()
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

    def _set_panel_on_output(self):
        """Update the GTK Layer Shell monitor for the panel window."""
        monitors = get_monitor_info()
        monitor = self.get_target_monitor(monitors)
        monitor_gdk_obj = monitor["monitor"]  # pyright: ignore[]
        monitor_name = monitor_gdk_obj.get_connector()
        output = [i for i in self.ipc.list_outputs() if i["name"] == monitor_name][0]
        geo = output["geometry"]
        output_width = geo["width"]
        user_defined_height_top_panel = (
            self.config_handler.config_data("panel", {})
            .get("top", {})
            .get("height", 32)
        )

        user_defined_width_top_panel = (
            self.config_handler.config_data("panel", {})
            .get("top", {})
            .get("width", output_width)
        )
        user_defined_height_left_panel = (
            self.config_handler.config_data("panel", {})
            .get("left", {})
            .get("height", 32)
        )
        user_defined_width_left_panel = (
            self.config_handler.config_data("panel", {})
            .get("left", {})
            .get("width", 32)
        )
        user_defined_height_right_panel = (
            self.config_handler.config_data("panel", {})
            .get("right", {})
            .get("height", 32)
        )
        user_defined_width_right_panel = (
            self.config_handler.config_data("panel", {})
            .get("right", {})
            .get("width", 32)
        )
        user_defined_height_bottom_panel = (
            self.config_handler.config_data("panel", {})
            .get("bottom", {})
            .get("height", 32)
        )
        user_defined_width_bottom_panel = (
            self.config_handler.config_data("panel", {})
            .get("bottom", {})
            .get("width", output_width)
        )
        user_defined_height_bottom_panel = (
            self.config_handler.config_data("panel", {})
            .get("bottom", {})
            .get("height", 32)
        )
        user_defined_width_bottom_panel = (
            self.config_handler.config_data("panel", {})
            .get("bottom", {})
            .get("width", output_width)
        )

        if monitor:
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

    def about(self):
        """Automatically moves the panel to a valid monitor when the current one is disabled."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin ensures the panel remains visible by automatically moving it
        to an active output when the current one is disconnected or disabled.

        The core logic involves:
        1.  **Initial Assignment:** On startup, the panel is placed on a preferred
            (if configured) or the first available monitor.
        2.  **Event Listening:** It subscribes to an "output-layout-changed" event,
            triggering a re-evaluation of the display setup whenever a monitor's
            status changes.
        3.  **Dynamic Relocation:** If the primary or current monitor is no longer
            active, the plugin finds the first available, non-DPMS output and
            reassigns the panel to it using LayerShell.
        4.  **Debouncing:** A brief delay is used to prevent the panel from
            rapidly flickering during transient display changes.
        """
        return self.code_explanation.__doc__
