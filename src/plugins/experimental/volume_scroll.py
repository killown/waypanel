def get_plugin_metadata(_):
    about = (
        "A plugin that allows volume control via the scroll wheel and",
        "displays a floating on-screen display (OSD).",
    )
    return {
        "id": "org.waypanel.plugin.volume_scroll",
        "name": "Volume Scroll",
        "version": "1.0.2",
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
    import subprocess
    import typing

    class VolumeScrollPlugin(BasePlugin):
        """
        Provides non-blocking volume control via scroll wheel and a floating OSD.
        """

        def __init__(self, panel_instance):
            """
            Initialize the plugin.
            """
            super().__init__(panel_instance)
            self.add_hint(["Configuration for the Volume Scroll OSD plugin."], None)
            self.widget = None
            self.hide_timeout_id = None
            self.timeout_in_seconds = self.get_plugin_setting(["popup_timeout"], 1)
            self.add_hint(
                [
                    "The duration in seconds the OSD window remains visible after the last volume change."
                ],
                "popup_timeout",
            )
            self.slider = None
            self.icon = None
            self.label = None
            self.max_volume = self.get_plugin_setting(["max_volume"], 150)
            self.add_hint(
                [
                    "The maximum volume percentage allowed for the slider/scroll. Must be > 100."
                ],
                "max_volume",
            )
            self.slider_handler_id = None
            self.run_in_thread(self.update_max_volume)
            self.run_in_thread(self.setup_scroll_event)
            self.add_hint(
                [
                    "Settings controlling the position and size of the floating OSD volume widget."
                ],
                ["layout"],
            )
            self.default_anchor_edge = self.get_plugin_setting(
                ["layout", "anchor_edge", "default"], ["TOP"]
            )
            self.add_hint(
                [
                    "A list of edges to anchor the floating OSD window to (TOP, BOTTOM, LEFT, RIGHT)."
                ],
                ["layout", "anchor_edge", "default"],
            )
            self.anchor_edge_top = self.get_plugin_setting(
                ["layout", "anchor_edge", "top"], 0
            )
            self.add_hint(
                ["Margin (in pixels) from the top edge."],
                ["layout", "anchor_edge", "top"],
            )
            self.anchor_edge_bottom = self.get_plugin_setting(
                ["layout", "anchor_edge", "bottom"], 0
            )
            self.add_hint(
                ["Margin (in pixels) from the bottom edge."],
                ["layout", "anchor_edge", "bottom"],
            )
            self.anchor_edge_left = self.get_plugin_setting(
                ["layout", "anchor_edge", "left"], 0
            )
            self.add_hint(
                ["Margin (in pixels) from the left edge."],
                ["layout", "anchor_edge", "left"],
            )
            self.anchor_edge_right = self.get_plugin_setting(
                ["layout", "anchor_edge", "right"], 0
            )
            self.add_hint(
                ["Margin (in pixels) from the right edge."],
                ["layout", "anchor_edge", "right"],
            )
            self.add_hint(
                ["Settings for the default size of the floating OSD volume widget."],
                ["layout", "popup_size"],
            )
            self.popup_width = self.get_plugin_setting(
                ["layout", "popup_size", "width"], 200
            )
            self.add_hint(
                ["The default width of the floating OSD volume widget (in pixels)."],
                ["layout", "popup_size", "width"],
            )
            self.popup_height = self.get_plugin_setting(
                ["layout", "popup_size", "height"], 100
            )
            self.add_hint(
                ["The default height of the floating OSD volume widget (in pixels)."],
                ["layout", "popup_size", "height"],
            )

        def update_max_volume(self) -> None:
            """
            Fetch the maximum volume supported by the system.
            """
            try:
                with pulsectl.Pulse("volume-increaser") as pulse:
                    for sink in pulse.sink_list():
                        if "RUNNING" in str(sink.state).upper():
                            self.max_volume = round(
                                sink.volume.values[0]
                                * self.max_volume
                                * sink.base_volume
                                / sink.volume.value_flat
                            )
                            break
            except Exception as e:
                self.logger.error(f"Error fetching maximum volume: {e}")
                self.max_volume = 150

        def setup_scroll_event(self) -> None:
            """
            Set up the scroll event listener.
            """
            scroll_controller = self.gtk.EventControllerScroll.new(
                self.gtk.EventControllerScrollFlags.BOTH_AXES
            )
            scroll_controller.connect("scroll", self.on_scroll)
            self.obj.top_panel_box_full.add_controller(scroll_controller)

        def on_scroll(self, controller, dx: float, dy: float) -> bool:
            """
            Handle scroll events to adjust the volume.
            FIX: Calculates the new absolute target volume and clamps it.
            """
            try:
                current_volume = self.get_current_volume()
                delta = -10.0 if dy > 0 else 10.0
                new_volume = current_volume + delta
                target_volume = max(0.0, min(new_volume, float(self.max_volume)))
                print(target_volume, new_volume, float(self.max_volume))
                self.adjust_volume(target_volume)
            except Exception as e:
                self.logger.error(f"Error handling scroll event: {e}")
            return False

        def _update_ui_post_adjustment(self, current_volume: float) -> bool:
            """
            Safely updates the GTK UI elements from the main thread after
            a volume change has occurred in a background thread.
            """
            self.set_volume(current_volume)
            self.show_widget()
            return False

        def adjust_volume(self, target_volume: typing.Union[str, float]) -> None:
            """
            Offloads volume adjustment (blocking I/O) to a background thread.
            Always sets the volume absolutely using the provided target percentage.
            Args:
                target_volume: The volume target, either as a float (from scroll)
                               or an absolute percentage string (from slider, e.g., "150%").
            """

            def _blocking_task():
                """
                The blocking operations executed on a worker thread.
                """
                cmd = ""
                pactl_arg: str
                try:
                    if isinstance(target_volume, str) and target_volume.endswith("%"):
                        pactl_arg = target_volume
                    elif isinstance(target_volume, float):
                        pactl_arg = f"{int(round(target_volume))}%"
                    else:
                        self.logger.error(
                            f"Invalid volume adjustment input: {target_volume}"
                        )
                        return
                    cmd = [
                        "pactl",
                        "--",
                        "set-sink-volume",
                        "@DEFAULT_SINK@",
                        pactl_arg,
                    ]
                    self.logger.info(f"Executing volume change: {' '.join(cmd)}")
                    self.subprocess.run(cmd, check=True, capture_output=True)
                    current_volume = self.get_current_volume()
                    self.glib.idle_add(self._update_ui_post_adjustment, current_volume)
                except ValueError as e:
                    self.logger.error(
                        f"Volume calculation failed due to invalid input: {e} in adjustment: {target_volume}",
                        exc_info=True,
                    )
                except subprocess.CalledProcessError as e:
                    error_output = e.stderr.decode("utf-8").strip()
                    self.logger.error(
                        f"pactl failed with exit code {e.returncode} for command '{' '.join(cmd)}'. Error: {error_output}",
                        exc_info=True,
                    )
                except Exception as e:
                    self.logger.error(
                        f"Error adjusting volume in thread: {e}", exc_info=True
                    )

            self.run_in_thread(_blocking_task)

        def get_current_volume(self) -> float:
            """
            Get the current volume level using `pulsectl`.
            Returns the raw floating-point percentage.
            """
            try:
                with pulsectl.Pulse("volume-increaser") as pulse:
                    for sink in pulse.sink_list():
                        if "RUNNING" in str(sink.state).upper():
                            volume = sink.volume.values[0] * 100
                            return volume
                return 0.0
            except Exception as e:
                self.logger.error(f"Error fetching current volume: {e}")
                return 0.0

        def create_floating_widget(self) -> None:
            """
            Create the floating volume widget with icon, label, and slider in one horizontal row.
            """
            self.widget = self.gtk.Window()
            self.layer_shell.init_for_window(self.widget)
            self.layer_shell.set_layer(self.widget, self.layer_shell.Layer.TOP)
            if "TOP" in self.default_anchor_edge:
                self.layer_shell.set_anchor(
                    self.widget, self.layer_shell.Edge.TOP, True
                )
            if "BOTTOM" in self.default_anchor_edge:
                self.layer_shell.set_anchor(
                    self.widget, self.layer_shell.Edge.BOTTOM, True
                )
            if "LEFT" in self.default_anchor_edge:
                self.layer_shell.set_anchor(
                    self.widget, self.layer_shell.Edge.LEFT, True
                )
            if "RIGHT" in self.default_anchor_edge:
                self.layer_shell.set_anchor(
                    self.widget, self.layer_shell.Edge.RIGHT, True
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
            hbox = self.gtk.Box(orientation=self.gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(5)
            hbox.set_margin_bottom(5)
            hbox.set_margin_start(10)
            hbox.set_margin_end(10)
            self.icon = self.gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
            self.icon.set_pixel_size(24)
            hbox.append(self.icon)
            self.label = self.gtk.Label(label="100%")
            self.label.set_valign(self.gtk.Align.CENTER)
            hbox.append(self.label)
            self.slider = self.gtk.Scale.new_with_range(
                self.gtk.Orientation.HORIZONTAL, 0, self.max_volume, 1
            )
            self.slider.set_value(self.max_volume)
            self.slider.set_hexpand(True)
            self.slider.set_halign(self.gtk.Align.FILL)
            self.slider.set_valign(self.gtk.Align.CENTER)
            hbox.append(self.slider)
            self.slider_handler_id = self.slider.connect(
                "value-changed", self.on_slider_changed
            )
            self.widget.set_child(hbox)
            self.widget.set_default_size(self.popup_width, 1)
            self.icon.add_css_class("floating-volume-icon")
            self.slider.add_css_class("floating-volume-slider")
            self.label.add_css_class("floating-volume-label")
            hbox.add_css_class("floating-volume-box")
            self.widget.add_css_class("floating-volume-widget")

        def show_widget(self) -> None:
            """Show the floating widget."""
            if not self.widget:
                self.create_floating_widget()
            if self.widget:
                self.widget.present()
                self.widget.set_opacity(1.0)
            if self.hide_timeout_id:
                self.glib.source_remove(self.hide_timeout_id)
            self.hide_timeout_id = self.glib.timeout_add_seconds(
                self.timeout_in_seconds, self.hide_widget
            )

        def hide_widget(self) -> bool:
            """
            Hide the floating widget.
            """
            if self.widget:
                self.widget.hide()
            self.hide_timeout_id = None
            return False

        def set_volume(self, volume: float) -> None:
            """
            Set the volume level and update the widget.
            """
            clamped_volume = min(volume, self.max_volume)
            if self.slider and self.slider_handler_id:
                self.slider.handler_block(self.slider_handler_id)
                self.slider.set_value(clamped_volume)
                self.slider.handler_unblock(self.slider_handler_id)
            if self.label and self.icon:
                int_clamped_volume = int(round(clamped_volume))
                int_raw_volume = int(round(volume))
                self.label.set_text(f"{int_raw_volume}%")
                if int_clamped_volume == 0:
                    icon_name = "audio-volume-muted-symbolic"
                elif int_clamped_volume < 33:
                    icon_name = "audio-volume-low-symbolic"
                elif int_clamped_volume < 66:
                    icon_name = "audio-volume-medium-symbolic"
                else:
                    icon_name = "audio-volume-high-symbolic"
                self.icon.set_from_icon_name(icon_name)

        def on_slider_changed(self, *__) -> None:
            """
            Handle slider value changes by immediately offloading the blocking
            volume adjustment to a background thread.
            """
            if self.slider:
                volume = self.slider.get_value()
                self.adjust_volume(f"{int(round(volume))}%")

        def code_explanation(self) -> str:
            """
            Provides a detailed explanation of the plugin's architecture and logic.
            """
            return """
            This plugin provides a dynamic and temporary visual feedback
            for volume changes triggered by the scroll wheel.
            Its core logic is centered on **event-driven volume control and
            dynamic UI display**:
            1.  **Scroll Control Fix**: The `on_scroll` method now calculates the new absolute target volume (current +/- 8%), clamps it to `self.max_volume` (150%), and passes this float value to `adjust_volume`. This guarantees scroll events respect the 150% ceiling and avoid the 100% cap.
            2.  **Slider Control**: `on_slider_changed` passes the absolute percentage set by the slider (up to 150%) as a string, which the background task uses for an absolute `pactl` set.
            3.  **UI Consistency**: The `set_volume` method continues to use the true system volume for the label display, while clamping the slider position and icon logic to the defined 150% maximum.
            """

    return VolumeScrollPlugin
