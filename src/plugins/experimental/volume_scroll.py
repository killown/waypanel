def get_plugin_metadata(_):
    about = (
        "A plugin that allows volume control via the scroll wheel and",
        "displays a floating on-screen display (OSD).",
    )
    return {
        "id": "org.waypanel.plugin.volume_scroll",
        "name": "Volume Scroll",
        "version": "1.0.3",
        "deps": ["top_panel"],
        "enabled": True,
        "description": about,
    }


def get_plugin_class():
    """
    The main plugin class entry point. ALL imports are deferred here
    to comply with the Waypanel loading architecture.
    Returns:
        type: The VolumeScrollPlugin class.
    """
    from src.plugins.core._base import BasePlugin
    import pulsectl
    import typing

    class VolumeScrollPlugin(BasePlugin):
        """
        Provides non-blocking volume control via scroll wheel and a floating OSD.
        """

        def __init__(self, panel_instance):
            """
            Initialize the plugin and setup configuration hints.
            Args:
                panel_instance: The main panel controller instance.
            """
            super().__init__(panel_instance)
            self.add_hint(["Configuration for the Volume Scroll OSD plugin."], None)
            self.widget = None
            self.hide_timeout_id = None
            self.timeout_in_seconds = self.get_plugin_setting(["popup_timeout"], 1)
            self.add_hint(
                ["The duration in seconds the OSD window remains visible."],
                "popup_timeout",
            )
            self.slider = None
            self.icon = None
            self.label = None
            self.max_volume_limit = self.get_plugin_setting(["max_volume"], 150)
            self.add_hint(
                ["The maximum volume percentage allowed. Must be > 100."],
                "max_volume",
            )
            self.slider_handler_id = None
            self.run_in_thread(self.setup_scroll_event)
            self.add_hint(["Settings for OSD position and size."], ["layout"])
            self.default_anchor_edge = self.get_plugin_setting(
                ["layout", "anchor_edge", "default"], ["TOP"]
            )
            self.anchor_edge_top = self.get_plugin_setting(
                ["layout", "anchor_edge", "top"], 0
            )
            self.anchor_edge_bottom = self.get_plugin_setting(
                ["layout", "anchor_edge", "bottom"], 0
            )
            self.anchor_edge_left = self.get_plugin_setting(
                ["layout", "anchor_edge", "left"], 0
            )
            self.anchor_edge_right = self.get_plugin_setting(
                ["layout", "anchor_edge", "right"], 0
            )
            self.popup_width = self.get_plugin_setting(
                ["layout", "popup_size", "width"], 200
            )

        def _get_default_sink(
            self, pulse: pulsectl.Pulse
        ) -> typing.Optional[typing.Any]:
            """
            Retrieve the default system sink.
            Args:
                pulse: An active pulsectl.Pulse instance.
            Returns:
                The sink object or None if not found.
            """
            try:
                server_info = pulse.server_info()
                default_name = server_info.default_sink_name
                for sink in pulse.sink_list():
                    if sink.name == default_name:
                        return sink
            except Exception as e:
                self.logger.error(f"Failed to identify default sink: {e}")
            return None

        def setup_scroll_event(self) -> None:
            """
            Initialize the GTK event controller for scroll handling.
            """
            scroll_controller = self.gtk.EventControllerScroll.new(
                self.gtk.EventControllerScrollFlags.BOTH_AXES
            )
            scroll_controller.connect("scroll", self.on_scroll)
            self.obj.top_panel_box_full.add_controller(scroll_controller)

        def on_scroll(self, controller, dx: float, dy: float) -> bool:
            """
            Handle scroll events to adjust volume relative to current levels.
            Args:
                controller: The GTK event controller.
                dx: Horizontal scroll delta.
                dy: Vertical scroll delta.
            Returns:
                bool: False to allow further event propagation.
            """
            try:
                current_volume = self.get_current_volume()
                delta = -5.0 if dy > 0 else 5.0
                new_volume = current_volume + delta
                target_volume = max(0.0, min(new_volume, float(self.max_volume_limit)))
                self.adjust_volume(target_volume)
            except Exception as e:
                self.logger.error(f"Scroll event processing failed: {e}")
            return False

        def get_current_volume(self) -> float:
            """
            Fetch the volume of the default sink regardless of its state.
            Returns:
                float: Current volume percentage (0-100+).
            """
            try:
                with pulsectl.Pulse("volume-query") as pulse:
                    sink = self._get_default_sink(pulse)
                    if sink:
                        return sink.volume.values[0] * 100
            except Exception as e:
                self.logger.error(f"Error fetching current volume: {e}")
            return 0.0

        def adjust_volume(self, target_volume: typing.Union[str, float]) -> None:
            """
            Execute volume adjustment in a background thread to prevent UI blocking.
            Args:
                target_volume: Target level as a float or percentage string.
            """

            def _blocking_task():
                try:
                    if isinstance(target_volume, str) and target_volume.endswith("%"):
                        pactl_arg = target_volume
                    else:
                        pactl_arg = f"{int(round(float(target_volume)))}%"
                    cmd = f"pactl set-sink-volume @DEFAULT_SINK@ {pactl_arg}"
                    self.cmd.run(cmd)
                    current = self.get_current_volume()
                    self.glib.idle_add(self._update_ui_post_adjustment, current)
                except Exception as e:
                    self.logger.error(f"Background volume adjustment failed: {e}")

            self.run_in_thread(_blocking_task)

        def _update_ui_post_adjustment(self, current_volume: float) -> bool:
            """
            Update the OSD or Widget on the main thread.
            """
            if "simple-text/update-display" in self.ipc.list_methods():
                focused_output = self.ipc.get_focused_output()
                pos_x = (focused_output["geometry"]["width"] // 2) - 200
                pos_y = focused_output["workarea"]["y"] - 32
                self.ipc.update_osd(
                    text=f"Volume: {round(current_volume)}%",
                    font_size=18,
                    timeout=1000,
                    x=pos_x,
                    y=pos_y,
                )
            else:
                self.set_volume(current_volume)
                self.show_widget()
            return False

        def create_floating_widget(self) -> None:
            """
            Construct the GTK window for the OSD.
            """
            self.widget = self.gtk.Window()
            self.layer_shell.init_for_window(self.widget)
            self.layer_shell.set_layer(self.widget, self.layer_shell.Layer.TOP)
            for edge in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
                if edge in self.default_anchor_edge:
                    gtk_edge = getattr(self.layer_shell.Edge, edge)
                    self.layer_shell.set_anchor(self.widget, gtk_edge, True)
            self.layer_shell.set_margin(
                self.widget, self.layer_shell.Edge.LEFT, self.anchor_edge_left
            )
            self.layer_shell.set_margin(
                self.widget, self.layer_shell.Edge.RIGHT, self.anchor_edge_right
            )
            self.layer_shell.set_margin(
                self.widget, self.layer_shell.Edge.TOP, self.anchor_edge_top
            )
            self.layer_shell.set_margin(
                self.widget, self.layer_shell.Edge.BOTTOM, self.anchor_edge_bottom
            )
            hbox = self.gtk.Box(orientation=self.gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_start(10)
            hbox.set_margin_end(10)
            self.icon = self.gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
            self.label = self.gtk.Label(label="0%")
            self.slider = self.gtk.Scale.new_with_range(
                self.gtk.Orientation.HORIZONTAL, 0, self.max_volume_limit, 1
            )
            self.slider.set_hexpand(True)
            hbox.append(self.icon)
            hbox.append(self.label)
            hbox.append(self.slider)
            self.slider_handler_id = self.slider.connect(
                "value-changed", self.on_slider_changed
            )
            self.widget.set_child(hbox)
            self.widget.set_default_size(self.popup_width, 1)

        def show_widget(self) -> None:
            """
            Display the OSD widget with a visibility timeout.
            """
            if not self.widget:
                self.create_floating_widget()
            self.widget.present()
            if self.hide_timeout_id:
                self.glib.source_remove(self.hide_timeout_id)
            self.hide_timeout_id = self.glib.timeout_add_seconds(
                self.timeout_in_seconds, self.hide_widget
            )

        def hide_widget(self) -> bool:
            """
            Hide the OSD widget.
            """
            if self.widget:
                self.widget.hide()
            self.hide_timeout_id = None
            return False

        def set_volume(self, volume: float) -> None:
            """
            Sync the UI components with the current volume level.
            Args:
                volume: The volume percentage to display.
            """
            clamped = min(volume, self.max_volume_limit)
            if self.slider and self.slider_handler_id:
                self.slider.handler_block(self.slider_handler_id)
                self.slider.set_value(clamped)
                self.slider.handler_unblock(self.slider_handler_id)
            if self.label:
                self.label.set_text(f"{int(round(volume))}%")
            if self.icon:
                icon_map = [
                    (0, "audio-volume-muted-symbolic"),
                    (33, "audio-volume-low-symbolic"),
                    (66, "audio-volume-medium-symbolic"),
                    (101, "audio-volume-high-symbolic"),
                ]
                for threshold, name in icon_map:
                    if clamped <= threshold:
                        self.icon.set_from_icon_name(name)
                        break
                else:
                    self.icon.set_from_icon_name("audio-volume-high-symbolic")

        def on_slider_changed(self, *__) -> None:
            """
            Handle manual slider adjustments.
            """
            if self.slider:
                val = self.slider.get_value()
                self.adjust_volume(val)

    return VolumeScrollPlugin
