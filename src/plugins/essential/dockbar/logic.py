"""Logic engine for the Dockbar plugin."""


class DockLogic:
    def __init__(self, plugin):
        self.p = plugin

    def is_scale_enabled(self):
        plugins = self.p.ipc.get_option_value("core/plugins")["value"].split()
        return "scale" in plugins

    def get_orientation(self):
        # Access metadata to determine container-based orientation
        from .dockbar import get_plugin_metadata

        meta = get_plugin_metadata(self.p._panel_instance)
        container = meta["container"]

        if "top-panel" in container or "bottom-panel" in container:
            return self.p.gtk.Orientation.HORIZONTAL
        return (
            self.p.gtk.Orientation.HORIZONTAL
            if self.p.panel_orientation.lower() == "h"
            else self.p.gtk.Orientation.VERTICAL
        )

    def on_left_click(self, cmd):
        self.p.cmd.run(cmd)
        if (
            not self.p.layer_always_exclusive
            and self.is_scale_enabled()
            and self.p.left_click_toggles_scale
        ):
            self.p.ipc.scale_toggle()

    def on_right_click(self, cmd):
        if not self.p.right_click_to_next_output:
            self.p.cmd.run(cmd)
            return
        try:
            outputs = self.p.ipc.list_outputs()
            focused = self.p.ipc.get_focused_output()
            idx = next(
                (i for i, o in enumerate(outputs) if o["id"] == focused["id"]), -1
            )
            next_output = outputs[(idx + 1) % len(outputs)]
            self.p.wf_helper.move_cursor_middle_output(next_output["id"])
            self.p.ipc.click_button("S-BTN_LEFT", "full")
            self.p.cmd.run(cmd)
        except Exception as e:
            self.p.logger.error(f"Error in right-click action: {e}")

    def on_middle_click(self, cmd):
        if self.p.middle_click_to_empty_workspace:
            coords = self.p.wf_helper.find_empty_workspace()
            if coords:
                self.p.ipc.scale_toggle()
                self.p.ipc.set_workspace(*coords)
                self.p.cmd.run(cmd)
                return
        self.p.cmd.run(cmd)

    def setup_file_watcher(self):
        config_file = self.p.config_handler.config_file
        try:
            self.p.gio_config_file = self.p.gio.File.new_for_path(str(config_file))
            self.p._config_observer = self.p.gio_config_file.monitor_file(
                self.p.gio.FileMonitorFlags.NONE, None
            )
            self.p._config_observer.connect(
                "changed", self.p._on_gio_config_file_changed
            )
            self.p._last_config_mod_time = self.p.os.path.getmtime(config_file)
        except Exception:
            pass
