ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 100
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        screen_recorder = call_plugin_class()
        return screen_recorder(panel_instance)


def call_plugin_class():
    from gi.repository import Gtk  # pyright: ignore
    from src.plugins.core._base import BasePlugin
    import shutil
    import urllib.parse

    class RecordingPopover(Gtk.Box):
        """
        A dedicated container (Gtk.Box) for selecting recording options.
        Its content will be placed inside the Gtk.Popover created by BasePlugin.
        """

        def __init__(self, main_plugin):
            super().__init__(
                orientation=main_plugin.gtk.Orientation.VERTICAL, spacing=6
            )
            self.main_plugin = main_plugin
            self.set_margin_top(10)
            self.set_margin_bottom(10)
            self.set_margin_start(10)
            self.set_margin_end(10)
            self.build_ui()

        def build_ui(self):
            """Builds the main popover content."""
            outputs = self.main_plugin.ipc.list_outputs()
            if not outputs:
                label = self.main_plugin.gtk.Label(label="No outputs detected.")
                self.set_child(label)  # pyright: ignore
                self.append(label)
                return
            output_names = [output["name"] for output in outputs]
            record_all_btn = self.main_plugin.gtk.Button(label="Record All Outputs")
            record_all_btn.connect(
                "clicked",
                lambda x: self.main_plugin.global_loop.create_task(
                    self.main_plugin.on_record_all_clicked()
                ),
            )
            record_all_btn.add_css_class("record-all-button")
            self.main_plugin.gtk_helper.add_cursor_effect(record_all_btn)
            self.append(record_all_btn)
            separator = self.main_plugin.gtk.Separator(
                orientation=self.main_plugin.gtk.Orientation.HORIZONTAL
            )
            self.append(separator)
            for name in output_names:
                btn = self.main_plugin.gtk.Button(label=f"Record Output: {name}")
                btn.connect(
                    "clicked",
                    lambda x, n=name: self.main_plugin.global_loop.create_task(
                        self.main_plugin.on_record_output_clicked(n)
                    ),
                )
                btn.add_css_class("record-output-button")
                self.main_plugin.gtk_helper.add_cursor_effect(btn)
                self.append(btn)
            separator2 = self.main_plugin.gtk.Separator(
                orientation=self.main_plugin.gtk.Orientation.HORIZONTAL
            )
            self.append(separator2)
            slurp_btn = self.main_plugin.gtk.Button(label="Record Region (slurp)")
            slurp_btn.connect(
                "clicked",
                lambda x: self.main_plugin.global_loop.create_task(
                    self.main_plugin.on_record_slurp_clicked()
                ),
            )
            slurp_btn.add_css_class("record-slurp-button")
            self.main_plugin.gtk_helper.add_cursor_effect(slurp_btn)
            self.append(slurp_btn)
            audio_switch_box = self.main_plugin.gtk.Box(
                orientation=self.main_plugin.gtk.Orientation.HORIZONTAL, spacing=10
            )
            audio_switch_label = self.main_plugin.gtk.Label(label="Record Audio:")
            audio_switch_label.set_halign(self.main_plugin.gtk.Align.START)
            audio_switch_box.append(audio_switch_label)
            self.audio_switch = self.main_plugin.gtk.Switch()
            self.audio_switch.set_active(self.main_plugin.record_audio)
            self.audio_switch.connect(
                "state-set", self.main_plugin.on_audio_switch_toggled
            )
            audio_switch_box.append(self.audio_switch)
            self.append(audio_switch_box)
            separator3 = self.main_plugin.gtk.Separator(
                orientation=self.main_plugin.gtk.Orientation.HORIZONTAL
            )
            self.append(separator3)
            stop_join_btn = self.main_plugin.gtk.Button(label="Stop All & Join Videos")
            stop_join_btn.connect(
                "clicked",
                lambda x: self.main_plugin.global_loop.create_task(
                    self.main_plugin.on_stop_and_join_clicked()
                ),
            )
            stop_join_btn.add_css_class("stop-join-button")
            self.main_plugin.gtk_helper.add_cursor_effect(stop_join_btn)
            self.append(stop_join_btn)

    class RecordingPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover = None
            self.button = None
            self.record_processes = []
            self.output_files = []
            self.video_dir = f"/tmp/wfrec_{self.os.getpid()}"
            self.final_dir = self._get_user_videos_dir()
            self.is_recording = False
            self.record_audio = False
            self._setup_directories()
            self.button = self.create_widget()
            self.main_widget = (self.button, "append")

        def _setup_directories(self):
            if self.os.path.exists(self.video_dir):
                try:
                    shutil.rmtree(self.video_dir)
                except Exception as e:
                    self.logger.exception(
                        f"Failed to remove temporary directory {self.video_dir}: {e}"
                    )
            try:
                self.os.makedirs(self.video_dir, exist_ok=True)
                self.logger.info(f"Recording directory: {self.video_dir}")
                self.os.makedirs(self.final_dir, exist_ok=True)
                self.logger.info(f"Final output folder: {self.final_dir}")
            except Exception as e:
                self.logger.exception(f"Failed to create necessary directories: {e}")

        def _get_user_videos_dir(self):
            try:
                user_dirs_file = self.os.path.expanduser("~/.config/user-dirs.dirs")
                if self.os.path.exists(user_dirs_file):
                    with open(user_dirs_file, "r") as f:
                        for line in f:
                            if line.startswith("XDG_VIDEOS_DIR"):
                                path = line.split("=")[1].strip().strip('"')
                                return self.os.path.expandvars(path)
            except Exception as e:
                self.logger.exception(f"Failed to read ~/.config/user-dirs.dirs: {e}")
            return self.os.path.join(self.os.path.expanduser("~"), "Videos")

        def create_widget(self):
            button = self.gtk.Button()
            button.set_icon_name(
                self.gtk_helper.icon_exist(
                    "screen_recorder",
                    [
                        "deepin-screen-recorder-symbolic",
                        "simplescreenrecorder-panel",
                        "media-record-symbolic",
                    ],
                )
            )
            button.set_tooltip_text("Start/Stop Screen Recording")
            self.gtk_helper.add_cursor_effect(button)
            button.connect("clicked", self.open_popover)
            return button

        def open_popover(self, widget):
            """
            Handles popover logic: hides if visible, otherwise creates (via base utility) and shows.
            """
            if self.popover and self.popover.is_visible():
                self.popover.popdown()
            else:
                self.popover = self.create_popover(
                    parent_widget=self.button, closed_handler=self.popover_is_closed
                )
                popover_content = RecordingPopover(self)
                self.popover.set_child(popover_content)
                self.popover.popup()

        def popdown(self):
            """Hides the popover."""
            if self.popover:
                self.popover.popdown()

        def popover_is_closed(self, popover):
            """Handler for the 'closed' signal, as required by BasePlugin.create_popover."""
            self.popover = None
            self.logger.info("Recording popover closed.")

        async def on_record_all_clicked(self):
            self.popdown()
            if self.is_recording:
                self.logger.info("Already recording. Stop first.")
                self.notifier.notify_send(
                    "Recording Already Running",
                    "Stop the current recording first.",
                    "record",
                )
                return
            await self._start_recording_all()

        async def _start_recording_all(self):
            self.record_processes = []
            self.output_files = []
            outputs = self.ipc.list_outputs()
            if not outputs:
                self.logger.error("No outputs found to record.")
                return
            self.logger.info(
                f"Starting recording on {len(outputs)} outputs: {[o['name'] for o in outputs]}"
            )
            for output in outputs:
                name = output["name"]
                path = self.os.path.join(self.video_dir, f"{name}.mp4")
                self.output_files.append(path)
                cmd = ["wf-recorder", "-f", path, "-o", name]
                if self.record_audio:
                    cmd.append("--audio")
                self.logger.info(
                    f"Starting wf-recorder for {name} -> {path} {'with audio' if self.record_audio else ''}"
                )
                try:
                    proc = await self.asyncio.create_subprocess_exec(*cmd)
                    self.record_processes.append(proc)
                except Exception as e:
                    self.logger.exception(
                        f"Failed to start wf-recorder for {name}: {e}"
                    )
            self.is_recording = True
            self.button.set_icon_name(  # pyright: ignore
                self.gtk_helper.icon_exist(
                    "screen_recorder",
                    [
                        "simplescreenrecorder-recording",
                        "media-record",
                    ],
                )
            )
            self.button.set_tooltip_text("Stop Recording")  # pyright: ignore
            self.logger.info("All recordings started.")

        async def on_record_output_clicked(self, output_name):
            self.popdown()
            if self.is_recording:
                self.logger.info("Already recording. Stop first.")
                self.notifier.notify_send(
                    "Recording Already Running",
                    "Stop the current recording first.",
                    "record",
                )
                return
            outputs = self.ipc.list_outputs()
            output_exists = any(o["name"] == output_name for o in outputs)
            if not output_exists:
                self.logger.error(f"Output '{output_name}' not found.")
                self.notifier.notify_send(
                    "Recording Failed", f"Output '{output_name}' not found.", "record"
                )
                return
            self.record_processes = []
            self.output_files = []
            timestamp = self.glib.DateTime.new_now_utc().format("%Y%m%d_%H%M%S")
            path = self.os.path.join(self.final_dir, f"{output_name}_{timestamp}.mp4")
            self.output_files.append(path)
            cmd = ["wf-recorder", "-f", path, "-o", output_name]
            if self.record_audio:
                cmd.append("--audio")
            self.logger.info(
                f"Starting wf-recorder for output '{output_name}' -> {path} {'with audio' if self.record_audio else ''}"
            )
            try:
                proc = await self.asyncio.create_subprocess_exec(*cmd)
                self.record_processes.append(proc)
                self.is_recording = True
                self.button.set_icon_name(  # pyright: ignore
                    self.gtk_helper.icon_exist(
                        "screen_recorder",
                        [
                            "simplescreenrecorder-recording",
                            "media-playback-stop-symbolic",
                        ],
                    )
                )
                self.button.set_tooltip_text("Stop Recording")  # pyright: ignore
                self.logger.info(f"Recording started for {output_name}.")
            except Exception as e:
                self.logger.exception(
                    f"Failed to start wf-recorder for {output_name}: {e}"
                )

        async def on_record_slurp_clicked(self):
            self.popdown()
            if self.is_recording:
                self.logger.info("Already recording. Stop first.")
                self.notifier.notify_send(
                    "Recording Already Running",
                    "Stop the current recording first.",
                    "record",
                )
                return
            self.record_processes = []
            self.output_files = []
            try:
                proc = await self.asyncio.create_subprocess_exec(
                    "slurp", stdout=self.asyncio.subprocess.PIPE
                )
                geometry_bytes, _ = await self.asyncio.wait_for(
                    proc.communicate(), timeout=5
                )
                geometry = geometry_bytes.decode("utf-8").strip()
                if proc.returncode != 0:
                    raise Exception(
                        f"slurp exited with non-zero code: {proc.returncode}"
                    )
                if not geometry:
                    self.logger.error("slurp returned empty geometry.")
                    return
            except self.asyncio.TimeoutError:
                self.logger.error("slurp timed out. Make sure you select a region.")
                self.notifier.notify_send(
                    "Region Select Failed",
                    "Slurp timed out. No region selected.",
                    "record",
                )
                return
            except FileNotFoundError:
                self.logger.error("slurp command not found. Please install slurp.")
                self.notifier.notify_send(
                    "Region Select Failed",
                    "Slurp command not found. Please install slurp.",
                    "record",
                )
                return
            except Exception as e:
                self.logger.exception(f"Failed to run slurp: {e}")
                self.notifier.notify_send(
                    "Region Select Failed", f"Failed to run slurp: {e}.", "record"
                )
                return
            timestamp = self.glib.DateTime.new_now_utc().format("%Y%m%d_%H%M%S")
            path = self.os.path.join(self.final_dir, f"region_{timestamp}.mp4")
            self.output_files.append(path)
            cmd = ["wf-recorder", "-f", path, "-g", geometry]
            if self.record_audio:
                cmd.append("--audio")
            self.logger.info(
                f"Starting wf-recorder for region '{geometry}' -> {path} {'with audio' if self.record_audio else ''}"
            )
            try:
                proc = await self.asyncio.create_subprocess_exec(*cmd)
                self.record_processes.append(proc)
                self.is_recording = True
                self.button.set_icon_name(  # pyright: ignore
                    self.gtk_helper.icon_exist(
                        "screen_recorder",
                        ["simplescreenrecorder-recording", "media-record"],
                    )
                )
                self.button.set_tooltip_text("Stop Recording")  # pyright: ignore
                self.logger.info(f"Recording started for region {geometry}.")
            except Exception as e:
                self.logger.exception(f"Failed to start wf-recorder for region: {e}")

        def on_audio_switch_toggled(self, switch, state):
            self.record_audio = state
            self.logger.info(f"Audio recording {'enabled' if state else 'disabled'}.")

        async def on_stop_and_join_clicked(self):
            if not self.is_recording:
                self.logger.info("No recordings are currently running.")
                return
            await self._stop_recorders()
            valid_output_files = [
                f for f in self.output_files if self.os.path.exists(f)
            ]
            num_files = len(valid_output_files)
            canonical_path = self.os.path.realpath(self.final_dir)
            quoted_path_segment = urllib.parse.quote(canonical_path)
            directory_uri = f"file://{quoted_path_segment}"
            if num_files > 1:
                self.global_loop.create_task(self._join_with_ffmpeg())
            elif num_files == 1:
                self.logger.info(
                    f"Single recording file saved to: {valid_output_files[0]}. Skipping join."
                )
                self.notifier.notify_send(
                    "Recording Complete",
                    f"Video saved to: {valid_output_files[0]}",
                    "record",
                    hints={"uri": directory_uri},
                )
            else:
                self.logger.info("No video files were successfully recorded or found.")

        async def _stop_recorders(self):
            self.popdown()
            if not self.record_processes:
                self.logger.info("No recording processes to stop.")
                return
            self.logger.info("Stopping all wf-recorder processes...")
            for p in self.record_processes:
                try:
                    p.terminate()
                except Exception as e:
                    self.logger.exception(f"Failed to terminate process: {e}")
            stop_tasks = [
                self.asyncio.create_task(p.wait()) for p in self.record_processes
            ]
            done, pending = await self.asyncio.wait(stop_tasks, timeout=5)
            for task in pending:
                self.logger.warning("Process did not terminate gracefully, killing...")
                task.cancel()
            self.record_processes.clear()
            self.is_recording = False
            self.button.set_icon_name(  # pyright: ignore
                self.gtk_helper.icon_exist(
                    "screen_recorder",
                    [
                        "deepin-screen-recorder-symbolic",
                        "simplescreenrecorder-panel",
                        "media-record-symbolic",
                    ],
                )
            )
            self.button.set_tooltip_text("Start/Stop Screen Recording")  # pyright: ignore
            self.logger.info("All recordings stopped.")

        async def _join_with_ffmpeg(self):
            files_to_join = [
                f
                for f in self.output_files
                if self.os.path.exists(f) and f.startswith(self.video_dir)
            ]
            if not files_to_join:
                self.logger.info("No output files in temp directory to join.")
                return
            outputs = self.ipc.list_outputs()
            geometries = [
                output["geometry"]
                for output in outputs
                if "geometry" in output and "height" in output["geometry"]
            ]
            if not geometries:
                self.logger.error(
                    "Output geometry not available from IPC. Cannot proceed with joining videos."
                )
                return
            min_height = min(g["height"] for g in geometries)
            num_outputs = len(files_to_join)
            timestamp = self.glib.DateTime.new_now_utc().format("%Y%m%d_%H%M%S")
            out_path = self.os.path.join(self.final_dir, f"joined_{timestamp}.mp4")
            if self.os.path.exists(out_path):
                self.os.remove(out_path)
            filter_complex_parts = []
            input_video_streams = ""
            for i in range(num_outputs):
                filter_complex_parts.append(
                    f"[{i}:v]scale=-1:{min_height},setsar=1[v{i}]"
                )
                input_video_streams += f"[v{i}]"
            if num_outputs > 1:
                hstack_chain = f"hstack=inputs={num_outputs}"
                filter_complex_parts.append(
                    f"{input_video_streams}{hstack_chain}[v_out]"
                )
            elif num_outputs == 1:
                filter_complex_parts[-1] += "[v_out]"
            filter_complex = ";".join(filter_complex_parts)
            cmd = [
                "ffmpeg",
                "-vsync",
                "2",
            ]
            for f in files_to_join:
                cmd.extend(["-i", f])
            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[v_out]",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "23",
                    "-preset",
                    "veryfast",
                ]
            )
            if self.record_audio and num_outputs > 0:
                audio_streams = "".join(f"[{i}:a]" for i in range(num_outputs))
                audio_filter = f"{audio_streams}amerge=inputs={num_outputs}[aout]"
                filter_complex_audio = f"{filter_complex};{audio_filter}"
                try:
                    idx = cmd.index("-filter_complex")
                    cmd[idx : idx + 2] = ["-filter_complex", filter_complex_audio]
                except ValueError:
                    pass
                cmd.extend(
                    [
                        "-map",
                        "[aout]",
                    ]
                )
            cmd.append(out_path)
            self.logger.info(f"Starting ffmpeg: {' '.join(cmd)}")
            try:
                proc = await self.asyncio.create_subprocess_exec(
                    *cmd, stderr=self.asyncio.subprocess.PIPE
                )
                _, stderr_bytes = await proc.communicate()
                stderr = stderr_bytes.decode("utf-8")
                if proc.returncode == 0:
                    self.logger.info(f"ffmpeg finished successfully: {out_path}")
                    canonical_path = self.os.path.realpath(self.final_dir)
                    quoted_path_segment = urllib.parse.quote(canonical_path)
                    directory_uri = f"file://{quoted_path_segment}"
                    self.notifier.notify_send(
                        "Recording Complete",
                        f"Videos joined: {out_path}",
                        "record",
                        hints={"uri": directory_uri},
                    )
                else:
                    self.logger.error(
                        f"ffmpeg failed with return code {proc.returncode}: {stderr}"
                    )
                    self.notifier.notify_send(
                        "Join Failed", f"ffmpeg error: {stderr[:100]}...", "record"
                    )
            except FileNotFoundError:
                self.logger.error("ffmpeg not found. Please install ffmpeg.")
                self.notifier.notify_send(
                    "Join Failed", "ffmpeg not installed.", "record"
                )
            except Exception as e:
                self.logger.exception(f"Unexpected error during ffmpeg: {e}")
                self.notifier.notify_send("Join Failed", f"Error: {str(e)}", "record")
            try:
                shutil.rmtree(self.video_dir)
                self.logger.info(f"Cleaned up temporary directory: {self.video_dir}")
            except Exception as e:
                self.logger.exception(
                    f"Failed to clean up temporary directory {self.video_dir}: {e}"
                )
            self._setup_directories()

        def about(self):
            """
            A plugin that provides a simple screen and audio recording utility for Wayland,
            using wf-recorder, slurp, and ffmpeg.
            """
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin acts as a screen and audio recording tool tailored for Wayland
            compositors, integrating with the system's graphical and command-line
            utilities.
            **Refactoring Notes (BasePlugin Utility Adherence):**
            1.  **BasePlugin Utility Use:** The `open_popover` method now correctly uses
                `self.create_popover(parent_widget=self.button, closed_handler=self.popover_is_closed)`
                from the `BasePlugin` to handle the generic setup (instantiation,
                parenting, arrow, and signal connections) of the `Gtk.Popover`.
            2.  **UI/Logic Separation (`RecordingPopover`):** The custom `RecordingPopover`
                class was refactored to inherit from `Gtk.Box`. This makes it a pure
                content container.
            3.  **Content Insertion:** The `open_popover` method then sets this new
                content container as the child of the popover instance returned by
                the base utility: `self.popover.set_child(popover_content)`.
            4.  **Helper Access:** The `RecordingPopover` accesses all required Waypanel
                components (GTK, IPC, loop) through the `main_plugin` instance passed
                to its constructor.
            """
            return self.code_explanation.__doc__

    return RecordingPlugin
