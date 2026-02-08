def get_plugin_metadata(_):
    about = (
        "A plugin that allows volume control via the scroll wheel and",
        "displays a floating on-screen display (OSD).",
    )
    return {
        "id": "org.waypanel.plugin.volume_scroll",
        "name": "Volume Scroll",
        "version": "1.0.6",
        "deps": ["top_panel", "css_generator"],
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
            Initialize the plugin instance.
            """
            super().__init__(panel_instance)
            self.widget = None
            self.hide_timeout_id = None
            self.slider = None
            self.icon = None
            self.label = None
            self.slider_handler_id = None

        def on_start(self):
            """
            Setup configuration, lifecycle-dependent objects, and UI hooks.
            """
            self.timeout_in_seconds = self.get_plugin_setting_add_hint(
                ["popup_timeout"], 1, "The duration in seconds the OSD remains visible."
            )
            self.max_volume_limit = self.get_plugin_setting_add_hint(
                ["max_volume"],
                150,
                "The maximum volume percentage allowed. Must be > 100.",
            )

            # Layout Settings
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
                ["layout", "popup_size", "width"], 400
            )

            self.plugins["css_generator"].install_css("volume-scroll.css")
            self.run_in_thread(self.setup_scroll_event)

        def _get_default_sink(
            self, pulse: pulsectl.Pulse
        ) -> typing.Optional[typing.Any]:
            """
            Retrieve the default system sink.
            """
            try:
                server_info = pulse.server_info()
                default_name = server_info.default_sink_name  # pyright: ignore
                for sink in pulse.sink_list():
                    if sink.name == default_name:
                        return sink
            except Exception as e:
                self.logger.error(f"Failed to identify default sink: {e}")
            return None

        def setup_scroll_event(self) -> None:
            """
            Initialize the GTK event controller for scroll handling on the panel.
            """
            scroll_controller = self.gtk.EventControllerScroll.new(
                self.gtk.EventControllerScrollFlags.BOTH_AXES
            )
            scroll_controller.connect("scroll", self.on_scroll)
            self.obj.top_panel_box_full.add_controller(scroll_controller)

        def on_scroll(self, controller, dx: float, dy: float) -> bool:
            """
            Handle scroll events to adjust volume.
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
            Fetch the current volume level via PulseAudio.
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
            Set volume in a background thread to prevent UI micro-stutters.
            """

            def _blocking_task():
                try:
                    if isinstance(target_volume, str) and target_volume.endswith("%"):
                        pactl_arg = target_volume
                    else:
                        pactl_arg = f"{int(round(float(target_volume)))}%"
                    self.cmd.run(f"pactl set-sink-volume @DEFAULT_SINK@ {pactl_arg}")
                    current = self.get_current_volume()
                    self.glib.idle_add(self._update_ui, current)
                except Exception as e:
                    self.logger.error(f"Background volume adjustment failed: {e}")

            self.run_in_thread(_blocking_task)

        def _update_ui(self, current_volume: float) -> bool:
            """
            Update the OSD state.
            """
            self.set_volume(current_volume)
            self.show_widget()
            return False

        def create_floating_widget(self) -> None:
            """
            Construct the OSD window using the Layer Shell protocol.
            """
            self.widget = self.gtk.Window()
            self.widget.add_css_class("floating-volume-widget")
            self.layer_shell.init_for_window(self.widget)
            self.layer_shell.set_layer(self.widget, self.layer_shell.Layer.TOP)

            for edge in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
                if edge in self.default_anchor_edge:
                    self.layer_shell.set_anchor(
                        self.widget, getattr(self.layer_shell.Edge, edge), True
                    )

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

            container = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL)
            container.add_css_class("volume-osd-container")

            hbox = self.gtk.Box(orientation=self.gtk.Orientation.HORIZONTAL, spacing=20)
            hbox.set_margin_start(24)
            hbox.set_margin_end(24)
            hbox.set_margin_top(18)
            hbox.set_margin_bottom(18)

            self.icon = self.gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
            self.icon.add_css_class("floating-volume-icon")

            self.label = self.gtk.Label(label="0%")
            self.label.add_css_class("floating-volume-label")

            self.slider = self.gtk.Scale.new_with_range(
                self.gtk.Orientation.HORIZONTAL, 0, self.max_volume_limit, 1
            )
            self.slider.add_css_class("floating-volume-slider")
            self.slider.set_hexpand(True)

            hbox.append(self.icon)
            hbox.append(self.label)
            hbox.append(self.slider)

            self.slider_handler_id = self.slider.connect(
                "value-changed", self.on_slider_changed
            )

            container.append(hbox)
            self.widget.set_child(container)
            self.widget.set_default_size(self.popup_width, 1)

        def show_widget(self) -> None:
            """
            Show the OSD with a visibility timeout.
            """
            if not self.widget:
                self.create_floating_widget()
            self.widget.present()  # pyright: ignore
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
            Synchronize UI state with volume data.
            """
            clamped = min(volume, self.max_volume_limit)
            if self.slider and self.slider_handler_id:
                self.slider.handler_block(self.slider_handler_id)
                self.slider.set_value(clamped)
                self.slider.handler_unblock(self.slider_handler_id)
            if self.label:
                self.label.set_text(f"{int(round(volume))}%")
            if self.icon:
                icon_name = "audio-volume-muted-symbolic"
                if clamped > 66:
                    icon_name = "audio-volume-high-symbolic"
                elif clamped > 33:
                    icon_name = "audio-volume-medium-symbolic"
                elif clamped > 0:
                    icon_name = "audio-volume-low-symbolic"
                self.icon.set_from_icon_name(icon_name)

        def on_slider_changed(self, *__) -> None:
            """
            Handle manual volume slider changes.
            """
            if self.slider:
                self.adjust_volume(self.slider.get_value())

    return VolumeScrollPlugin
