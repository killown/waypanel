from gi.repository import Gtk, Gio, GLib
import subprocess
import shutil
import os
from src.plugins.core._base import BasePlugin
from src.core.compositor.ipc import IPC

# Enable or disable the plugin
ENABLE_PLUGIN = True


# Define where the plugin should appear
def get_plugin_placement(panel_instance):
    """
    Define where the plugin should be placed in the panel and its order.
    Returns:
        tuple: (position, order) for UI plugins
    """
    position = "top-panel-systray"
    order = 100  # High order to place it at the end of the systray
    return position, order


def initialize_plugin(panel_instance):
    """
    Initialize the plugin and return its instance.
    Args:
        panel_instance: The main panel object from panel.py.
    """
    if ENABLE_PLUGIN:
        return RecordingPlugin(panel_instance)
    return None


class RecordingPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover = None
        self.button = None
        self.record_processes = []  # Track running wf-recorder processes
        self.output_files = []  # Track output file paths
        self.video_dir = f"/tmp/wfrec_{os.getpid()}"  # Unique temp folder
        self.final_dir = self._get_user_videos_dir()  # User's Videos directory
        self.is_recording = False
        self.record_audio = False  # NEW: State of the audio switch (OFF by default)
        self._setup_directories()
        # IMPORTANT: Create the button widget here, but DO NOT create/populate the popover yet.
        # We'll create the popover lazily when needed.
        self.button = self.create_widget()
        self.main_widget = (self.button, "append")

    def _setup_directories(self):
        """Ensure video directories exist."""
        # Clean up any old temporary directory
        if os.path.exists(self.video_dir):
            shutil.rmtree(self.video_dir)
        os.makedirs(self.video_dir, exist_ok=True)
        self.logger.info(f"Recording directory: {self.video_dir}")

        # Ensure final output directory exists
        os.makedirs(self.final_dir, exist_ok=True)
        self.logger.info(f"Final output folder: {self.final_dir}")

    def _get_user_videos_dir(self):
        """Get the user's Videos directory, respecting localization."""
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
        # Fallback
        return os.path.join(os.path.expanduser("~"), "Videos")

    def create_widget(self):
        """Create the main widget for the plugin (the button)."""
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
        """Open or close the recording control popover."""
        if self.popover and self.popover.is_visible():
            self.popover.popdown()
        else:
            # Create the popover content ONLY when we are about to show it.
            # This ensures all widgets are created in the context of the realized parent.
            self.create_popover()
            self.popover.popup()

    def popdown(self):
        self.popover.popdown()

    def create_popover(self):
        """Create and configure the recording control popover."""
        if self.popover:
            # If it already exists, just clear its children to avoid memory leaks
            # and rebuild the content dynamically each time.
            child = self.popover.get_child()
            if child:
                del child
        else:
            # Create the Popover only once
            self.popover = Gtk.Popover()
            self.popover.set_has_arrow(True)
            self.popover.connect("closed", self.popover_is_closed)

        outputs = self.ipc.list_outputs()
        if not outputs:
            label = Gtk.Label(label="No outputs detected.")
            self.popover.set_child(label)
            return

        output_names = [output["name"] for output in outputs]

        # Main vertical box for the popover content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)

        # Add "Record All" button
        record_all_btn = Gtk.Button(label="Record All Outputs")
        record_all_btn.connect("clicked", self.on_record_all_clicked)
        record_all_btn.add_css_class("record-all-button")
        self.utils.add_cursor_effect(record_all_btn)
        main_box.append(record_all_btn)

        # Add separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator)

        # Add individual output buttons
        for name in output_names:
            btn = Gtk.Button(label=f"Record Output: {name}")
            btn.connect("clicked", self.on_record_output_clicked, name)
            btn.add_css_class("record-output-button")
            self.utils.add_cursor_effect(btn)
            main_box.append(btn)

        # Add separator
        separator2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator2)

        # NEW: Add "Record Region (slurp)" button
        slurp_btn = Gtk.Button(label="Record Region (slurp)")
        slurp_btn.connect("clicked", self.on_record_slurp_clicked)
        slurp_btn.add_css_class("record-slurp-button")
        self.utils.add_cursor_effect(slurp_btn)
        main_box.append(slurp_btn)

        # NEW: Add Audio Switch
        audio_switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        audio_switch_label = Gtk.Label(label="Record Audio:")
        audio_switch_label.set_halign(Gtk.Align.START)
        audio_switch_box.append(audio_switch_label)

        self.audio_switch = Gtk.Switch()
        self.audio_switch.set_active(self.record_audio)  # Set initial state
        self.audio_switch.connect("state-set", self.on_audio_switch_toggled)
        audio_switch_box.append(self.audio_switch)
        main_box.append(audio_switch_box)

        # Add separator
        separator3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator3)

        # Add "Stop All & Join" button
        stop_join_btn = Gtk.Button(label="Stop All & Join Videos")
        stop_join_btn.connect("clicked", self.on_stop_and_join_clicked)
        stop_join_btn.add_css_class("stop-join-button")
        self.utils.add_cursor_effect(stop_join_btn)
        main_box.append(stop_join_btn)

        # Set the main box as the child of the popover
        # This is CRITICAL: We set the child *after* building the entire UI.
        # This ensures the Popover's parent (self.button) is already realized.
        self.popover.set_child(main_box)

        # Attach the popover to its parent widget (the button)
        # This must be done *after* setting the child.
        self.popover.set_parent(self.button)

    def on_record_all_clicked(self, button):
        """Handle the 'Record All' button click."""
        self.popover.popdown()
        if self.is_recording:
            self.logger.info("Already recording. Stop first.")
            return

        self._start_recording_all()

    def _start_recording_all(self):
        """Start recording on all outputs."""
        self.popover.popdown()
        if self.is_recording:
            return

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
            # NEW: Add --audio flag if switch is ON
            if self.record_audio:
                cmd.append("--audio")

            self.logger.info(
                f"Starting wf-recorder for {name} -> {path} {'with audio' if self.record_audio else ''}"
            )
            try:
                proc = subprocess.Popen(cmd)
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

    def on_record_output_clicked(self, button, output_name):
        """Handle the 'Record Output: <name>' button click."""
        self.popover.popdown()
        if self.is_recording:
            self.logger.info("Already recording. Stop first.")
            return

        # Check if output exists
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
        # NEW: Add --audio flag if switch is ON
        if self.record_audio:
            cmd.append("--audio")

        self.logger.info(
            f"Starting wf-recorder for output '{output_name}' -> {path} {'with audio' if self.record_audio else ''}"
        )
        try:
            proc = subprocess.Popen(cmd)
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

    def on_record_slurp_clicked(self, button):
        """Handle the 'Record Region (slurp)' button click."""
        self.popover.popdown()
        if self.is_recording:
            self.logger.info("Already recording. Stop first.")
            return

        self.record_processes = []
        self.output_files = []

        # Get the region using slurp
        try:
            result = subprocess.run(
                ["slurp"], capture_output=True, text=True, check=True
            )
            geometry = result.stdout.strip()
            if not geometry:
                self.logger.error("slurp returned empty geometry.")
                return
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to run slurp: {e.stderr}")
            return
        except FileNotFoundError:
            self.logger.error("slurp command not found. Please install slurp.")
            return

        # Generate unique filename
        timestamp = GLib.DateTime.new_now_utc().format("%Y%m%d_%H%M%S")
        path = os.path.join(self.final_dir, f"region_{timestamp}.mp4")
        self.output_files.append(path)

        cmd = ["wf-recorder", "-f", path, "-g", geometry]
        # NEW: Add --audio flag if switch is ON
        if self.record_audio:
            cmd.append("--audio")

        self.logger.info(
            f"Starting wf-recorder for region '{geometry}' -> {path} {'with audio' if self.record_audio else ''}"
        )
        try:
            proc = subprocess.Popen(cmd)
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
        """Handle the audio switch toggle."""
        self.record_audio = state
        self.logger.info(f"Audio recording {'enabled' if state else 'disabled'}.")

    def on_stop_and_join_clicked(self, button):
        """Handle the 'Stop All & Join Videos' button click."""
        self.popover.popdown()
        if not self.is_recording:
            self.logger.info("No recordings are currently running.")
            return

        self._stop_recorders()

        # Only attempt join if we have exactly 2 files
        # FIXME: make it support more than 2 outputs
        if len(self.output_files) == 2:
            GLib.idle_add(self._join_with_ffmpeg)
        elif len(self.output_files) > 2:
            self.logger.info(
                f"Joined {len(self.output_files)} files into {self.final_dir}. Use ffmpeg manually for complex layouts."
            )
        else:
            self.logger.info("Only one recording file found. Skipping join.")
        self.popover.popdown()

    def _stop_recorders(self):
        """Stop all running wf-recorder processes."""

        self.popover.popdown()
        if not self.record_processes:
            self.logger.info("No recording processes to stop.")
            return

        self.logger.info("Stopping all wf-recorder processes...")
        for p in self.record_processes:
            try:
                p.terminate()
            except Exception as e:
                self.logger.warning(f"Failed to terminate process: {e}")

        # Wait for processes to finish gracefully
        for p in self.record_processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.logger.warning("Process did not terminate gracefully, killing...")
                p.kill()

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
            ),
        )
        self.button.set_tooltip_text("Start/Stop Screen Recording")
        self.logger.info("All recordings stopped.")

    def _join_with_ffmpeg(self):
        """Join two video files side-by-side using ffmpeg."""
        if len(self.output_files) != 2:
            return

        self.popover.popdown()
        output_path = os.path.join(self.final_dir, "joined.mp4")
        if os.path.exists(output_path):
            os.remove(output_path)

        out_path = os.path.join(self.final_dir, "joined.mp4")
        cmd = [
            "ffmpeg",
            "-i",
            self.output_files[0],
            "-i",
            self.output_files[1],
            "-filter_complex",
            "[0:v][1:v]hstack=inputs=2",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "veryfast",
            out_path,
        ]

        self.logger.info(f"Starting ffmpeg: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info(f"ffmpeg finished successfully: {out_path}")
                self.utils.notify_send(
                    "Recording Complete", f"Videos joined: {out_path}"
                )
            else:
                self.logger.error(
                    f"ffmpeg failed with return code {result.returncode}: {result.stderr}"
                )
                self.utils.notify_send(
                    "Join Failed", f"ffmpeg error: {result.stderr[:100]}..."
                )
        except FileNotFoundError:
            self.logger.error("ffmpeg not found. Please install ffmpeg.")
            self.utils.notify_send("Join Failed", "ffmpeg not installed.")
        except Exception as e:
            self.logger.error(f"Unexpected error during ffmpeg: {e}")
            self.utils.notify_send("Join Failed", f"Error: {str(e)}")

        return False  # stop idle_add

    def popover_is_closed(self, *_):
        """Callback when the popover is closed."""
        # No need to do anything special here, the popover will be recreated next time.
        pass
