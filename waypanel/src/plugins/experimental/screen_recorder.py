import shutil
import os
import asyncio
from gi.repository import Gtk, Gio, GLib
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop
from src.core.compositor.ipc import IPC

# Enable or disable the plugin
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 100
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return RecordingPlugin(panel_instance)
    return None


class RecordingPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover = None
        self.button = None
        self.record_processes = []
        self.output_files = []
        self.video_dir = f"/tmp/wfrec_{os.getpid()}"
        self.final_dir = self._get_user_videos_dir()
        self.is_recording = False
        self.record_audio = False
        self._setup_directories()
        self.button = self.create_widget()
        self.main_widget = (self.button, "append")

    def _setup_directories(self):
        if os.path.exists(self.video_dir):
            shutil.rmtree(self.video_dir)
        os.makedirs(self.video_dir, exist_ok=True)
        self.logger.info(f"Recording directory: {self.video_dir}")
        os.makedirs(self.final_dir, exist_ok=True)
        self.logger.info(f"Final output folder: {self.final_dir}")

    def _get_user_videos_dir(self):
        try:
            user_dirs_file = os.path.expanduser("~/.config/user-dirs.dirs")
            if os.path.exists(user_dirs_file):
                with open(user_dirs_file, "r") as f:
                    for line in f:
                        if line.startswith("XDG_VIDEOS_DIR"):
                            path = line.split("=")[1].strip().strip('"')
                            return os.path.expandvars(path)
        except Exception as e:
            self.logger.warning(f"Failed to read ~/.config/user-dirs.dirs: {e}")
        return os.path.join(os.path.expanduser("~"), "Videos")

    def create_widget(self):
        button = Gtk.Button()
        button.set_icon_name(
            self.utils.set_widget_icon_name(
                "screen_recorder",
                [
                    "deepin-screen-recorder-symbolic",
                    "simplescreenrecorder-panel",
                    "media-record-symbolic",
                ],
            )
        )
        button.set_tooltip_text("Start/Stop Screen Recording")
        self.utils.add_cursor_effect(button)
        button.connect("clicked", self.open_popover)
        return button

    def open_popover(self, widget):
        if self.popover and self.popover.is_visible():
            self.popover.popdown()
        else:
            self.create_popover()
            self.popover.popup()

    def popdown(self):
        self.popover.popdown()

    def create_popover(self):
        if self.popover:
            child = self.popover.get_child()
            if child:
                child.unparent()
        else:
            self.popover = Gtk.Popover()
            self.popover.set_has_arrow(True)
            self.popover.connect("closed", self.popover_is_closed)

        outputs = self.ipc.list_outputs()
        if not outputs:
            label = Gtk.Label(label="No outputs detected.")
            self.popover.set_child(label)
            return

        output_names = [output["name"] for output in outputs]
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)

        record_all_btn = Gtk.Button(label="Record All Outputs")
        record_all_btn.connect(
            "clicked", lambda x: global_loop.create_task(self.on_record_all_clicked())
        )
        record_all_btn.add_css_class("record-all-button")
        self.utils.add_cursor_effect(record_all_btn)
        main_box.append(record_all_btn)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator)

        for name in output_names:
            btn = Gtk.Button(label=f"Record Output: {name}")
            btn.connect(
                "clicked",
                lambda x, n=name: global_loop.create_task(
                    self.on_record_output_clicked(n)
                ),
            )
            btn.add_css_class("record-output-button")
            self.utils.add_cursor_effect(btn)
            main_box.append(btn)

        separator2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator2)

        slurp_btn = Gtk.Button(label="Record Region (slurp)")
        slurp_btn.connect(
            "clicked", lambda x: global_loop.create_task(self.on_record_slurp_clicked())
        )
        slurp_btn.add_css_class("record-slurp-button")
        self.utils.add_cursor_effect(slurp_btn)
        main_box.append(slurp_btn)

        audio_switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        audio_switch_label = Gtk.Label(label="Record Audio:")
        audio_switch_label.set_halign(Gtk.Align.START)
        audio_switch_box.append(audio_switch_label)

        self.audio_switch = Gtk.Switch()
        self.audio_switch.set_active(self.record_audio)
        self.audio_switch.connect("state-set", self.on_audio_switch_toggled)
        audio_switch_box.append(self.audio_switch)
        main_box.append(audio_switch_box)

        separator3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator3)

        stop_join_btn = Gtk.Button(label="Stop All & Join Videos")
        stop_join_btn.connect(
            "clicked",
            lambda x: global_loop.create_task(self.on_stop_and_join_clicked()),
        )
        stop_join_btn.add_css_class("stop-join-button")
        self.utils.add_cursor_effect(stop_join_btn)
        main_box.append(stop_join_btn)

        self.popover.set_child(main_box)
        self.popover.set_parent(self.button)

    async def on_record_all_clicked(self):
        self.popover.popdown()
        if self.is_recording:
            self.logger.info("Already recording. Stop first.")
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
            path = os.path.join(self.video_dir, f"{name}.mp4")
            self.output_files.append(path)

            cmd = ["wf-recorder", "-f", path, "-o", name]
            if self.record_audio:
                cmd.append("--audio")

            self.logger.info(
                f"Starting wf-recorder for {name} -> {path} {'with audio' if self.record_audio else ''}"
            )
            try:
                proc = await asyncio.create_subprocess_exec(*cmd)
                self.record_processes.append(proc)
            except Exception as e:
                self.logger.error(f"Failed to start wf-recorder for {name}: {e}")

        self.is_recording = True
        self.button.set_icon_name(
            self.utils.set_widget_icon_name(
                "screen_recorder",
                [
                    "simplescreenrecorder-recording",
                    "media-record",
                ],
            )
        )
        self.button.set_tooltip_text("Stop Recording")
        self.logger.info("All recordings started.")

    async def on_record_output_clicked(self, output_name):
        self.popover.popdown()
        if self.is_recording:
            self.logger.info("Already recording. Stop first.")
            return

        outputs = self.ipc.list_outputs()
        output_exists = any(o["name"] == output_name for o in outputs)
        if not output_exists:
            self.logger.error(f"Output '{output_name}' not found.")
            return

        self.record_processes = []
        self.output_files = []

        path = os.path.join(self.final_dir, f"{output_name}.mp4")
        self.output_files.append(path)

        cmd = ["wf-recorder", "-f", path, "-o", output_name]
        if self.record_audio:
            cmd.append("--audio")

        self.logger.info(
            f"Starting wf-recorder for output '{output_name}' -> {path} {'with audio' if self.record_audio else ''}"
        )
        try:
            proc = await asyncio.create_subprocess_exec(*cmd)
            self.record_processes.append(proc)
            self.is_recording = True
            self.button.set_icon_name(
                self.utils.set_widget_icon_name(
                    "screen_recorder",
                    ["simplescreenrecorder-recording", "media-playback-stop-symbolic"],
                )
            )
            self.button.set_tooltip_text("Stop Recording")
            self.logger.info(f"Recording started for {output_name}.")
        except Exception as e:
            self.logger.error(f"Failed to start wf-recorder for {output_name}: {e}")

    async def on_record_slurp_clicked(self):
        self.popover.popdown()
        if self.is_recording:
            self.logger.info("Already recording. Stop first.")
            return

        self.record_processes = []
        self.output_files = []

        try:
            # Use asyncio for slurp as well
            proc = await asyncio.create_subprocess_exec(
                "slurp", stdout=asyncio.subprocess.PIPE
            )
            geometry_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            geometry = geometry_bytes.decode("utf-8").strip()

            if proc.returncode != 0:
                raise Exception(f"slurp exited with non-zero code: {proc.returncode}")
            if not geometry:
                self.logger.error("slurp returned empty geometry.")
                return
        except asyncio.TimeoutError:
            self.logger.error("slurp timed out. Make sure you select a region.")
            return
        except FileNotFoundError:
            self.logger.error("slurp command not found. Please install slurp.")
            return
        except Exception as e:
            self.logger.error(f"Failed to run slurp: {e}")
            return

        timestamp = GLib.DateTime.new_now_utc().format("%Y%m%d_%H%M%S")
        path = os.path.join(self.final_dir, f"region_{timestamp}.mp4")
        self.output_files.append(path)

        cmd = ["wf-recorder", "-f", path, "-g", geometry]
        if self.record_audio:
            cmd.append("--audio")

        self.logger.info(
            f"Starting wf-recorder for region '{geometry}' -> {path} {'with audio' if self.record_audio else ''}"
        )
        try:
            proc = await asyncio.create_subprocess_exec(*cmd)
            self.record_processes.append(proc)
            self.is_recording = True
            self.button.set_icon_name(
                self.utils.set_widget_icon_name(
                    "screen_recorder",
                    ["simplescreenrecorder-recording", "media-record"],
                )
            )
            self.button.set_tooltip_text("Stop Recording")
            self.logger.info(f"Recording started for region {geometry}.")
        except Exception as e:
            self.logger.error(f"Failed to start wf-recorder for region: {e}")

    def on_audio_switch_toggled(self, switch, state):
        self.record_audio = state
        self.logger.info(f"Audio recording {'enabled' if state else 'disabled'}.")

    async def on_stop_and_join_clicked(self):
        self.popover.popdown()
        if not self.is_recording:
            self.logger.info("No recordings are currently running.")
            return

        await self._stop_recorders()

        if len(self.output_files) == 2:
            global_loop.create_task(self._join_with_ffmpeg())
        elif len(self.output_files) > 2:
            self.logger.info(
                f"Joined {len(self.output_files)} files into {self.final_dir}. Use ffmpeg manually for complex layouts."
            )
        else:
            self.logger.info("Only one recording file found. Skipping join.")
        self.popover.popdown()

    async def _stop_recorders(self):
        self.popover.popdown()
        if not self.record_processes:
            self.logger.info("No recording processes to stop.")
            return

        self.logger.info("Stopping all wf-recorder processes...")
        # Terminate all processes first
        for p in self.record_processes:
            try:
                p.terminate()
            except Exception as e:
                self.logger.warning(f"Failed to terminate process: {e}")

        # Await for processes to finish, with a timeout
        stop_tasks = [asyncio.create_task(p.wait()) for p in self.record_processes]
        done, pending = await asyncio.wait(stop_tasks, timeout=5)

        # Kill any processes that didn't terminate and are still pending
        for task in pending:
            self.logger.warning("Process did not terminate gracefully, killing...")
            task.cancel()  # Cancel the task

        self.record_processes.clear()
        self.is_recording = False
        self.button.set_icon_name(
            self.utils.set_widget_icon_name(
                "screen_recorder",
                [
                    "deepin-screen-recorder-symbolic",
                    "simplescreenrecorder-panel",
                    "media-record-symbolic",
                ],
            )
        )
        self.button.set_tooltip_text("Start/Stop Screen Recording")
        self.logger.info("All recordings stopped.")

    async def _join_with_ffmpeg(self):
        if not self.output_files:
            self.logger.info("No output files to join.")
            return

        # Find the lowest height from the detected outputs
        outputs = self.ipc.list_outputs()
        if not isinstance(outputs, list) or not all(
            isinstance(o, dict) for o in outputs
        ):
            self.logger.error(
                "IPC call did not return a list of dictionaries. Cannot determine resolution."
            )
            return

        min_height = min(output["geometry"]["height"] for output in outputs)
        num_outputs = len(self.output_files)

        out_path = os.path.join(self.final_dir, "joined.mp4")
        if os.path.exists(out_path):
            os.remove(out_path)

        # Build the filter_complex string dynamically
        filter_complex = ""
        input_video_streams = ""
        # Create the scale filter for each input video
        for i in range(num_outputs):
            filter_complex += f"[{i}:v]scale=-1:{min_height},setsar=1[v{i}];"
            input_video_streams += f"[v{i}]"

        # Build the hstack filter chain
        if num_outputs > 1:
            hstack_chain = f"hstack=inputs={num_outputs}"
            filter_complex += f"{input_video_streams}{hstack_chain}"
        elif num_outputs == 1:
            # If only one video, just use it without hstack
            filter_complex = f"[0:v]scale=-1:{min_height},setsar=1[v0]"

        cmd = [
            "ffmpeg",
            "-vsync",
            "2",
            *(
                [
                    arg
                    for pair in zip(["-i"] * num_outputs, self.output_files)
                    for arg in pair
                ]
            ),
            "-filter_complex",
            filter_complex,
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "veryfast",
        ]

        # Add audio sync if audio is being recorded
        if self.record_audio:
            # Create a channel map for each audio stream and join them
            audio_streams = "".join(f"[{i}:a]" for i in range(num_outputs))
            audio_filter = f"{audio_streams}amerge=inputs={num_outputs}[aout]"
            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex + f";{audio_filter}",
                    "-map",
                    f"[aout]",
                ]
            )

        cmd.append(out_path)

        self.logger.info(f"Starting ffmpeg: {' '.join(cmd)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stderr=asyncio.subprocess.PIPE
            )
            _, stderr_bytes = await proc.communicate()
            stderr = stderr_bytes.decode("utf-8")

            if proc.returncode == 0:
                self.logger.info(f"ffmpeg finished successfully: {out_path}")
                self.utils.notify_send(
                    "Recording Complete", f"Videos joined: {out_path}"
                )
            else:
                self.logger.error(
                    f"ffmpeg failed with return code {proc.returncode}: {stderr}"
                )
                self.utils.notify_send(
                    "Join Failed", f"ffmpeg error: {stderr[:100]}..."
                )
        except FileNotFoundError:
            self.logger.error("ffmpeg not found. Please install ffmpeg.")
            self.utils.notify_send("Join Failed", "ffmpeg not installed.")
        except Exception as e:
            self.logger.error(f"Unexpected error during ffmpeg: {e}")
            self.utils.notify_send("Join Failed", f"Error: {str(e)}")

    def popover_is_closed(self, *_):
        pass
