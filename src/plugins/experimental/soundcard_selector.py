from subprocess import Popen, check_output

import pulsectl
import soundcard as sc
from gi.repository import Gtk
from src.plugins.core._base import BasePlugin


ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 2
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        card = SoundCardDashboard(panel_instance)
        card.create_menu_popover_soundcard()
        return card


class SoundCardDashboard(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_dashboard = None
        self.soundcard_combobox = None
        self.mic_combobox = None
        self.menubutton_dashboard = None

    def get_view_id_by_pid(self, pid):
        lviews = self.ipc.list_views()
        for view in lviews:
            if pid == view["pid"]:
                return view["id"]

    def get_active_audio_app_info(self):
        audio_apps = {}

        with pulsectl.Pulse("list-sink-inputs") as pulse:
            for sink_input in pulse.sink_input_list():
                if not sink_input.mute and sink_input.volume.value_flat > 0.0:
                    app_name = sink_input.proplist.get("application.name", "Unknown")
                    pid = int(
                        sink_input.proplist.get("application.process.id", "Unknown")
                    )

                    audio_apps[pid] = {
                        "application_name": app_name,
                        "index": sink_input.index,
                        "view_id": self.get_view_id_by_pid(pid),
                    }
        return audio_apps

    def get_soundcard_list(self):
        return sc.all_speakers()

    def get_mic_list(self):
        return sc.all_microphones()

    def get_soundcard_list_names(self):
        blacklist = self.config_handler.config_data.get("soundcard", {}).get(
            "blacklist", []
        )
        soundcard_list = []

        # Add default soundcard if it's not blacklisted
        default_name = self.get_default_soundcard_name()
        if not any(b in default_name for b in blacklist):
            soundcard_list.append(default_name)

        # Add other soundcards, skipping duplicates and blacklisted names
        for soundcard in self.get_soundcard_list():
            name = soundcard.name
            if name not in soundcard_list and not any(b in name for b in blacklist):
                soundcard_list.append(name)

        return soundcard_list

    def get_mic_list_names(self):
        mic_list = []
        blacklist = self.config_handler.config_data.get("microphone", {}).get(
            "blacklist", []
        )

        default_mic = self.get_default_mic_name()
        mic_list_names = [mic.name for mic in self.get_mic_list()]

        # Add default mic if it's not blacklisted
        if default_mic in mic_list_names and not any(
            b in default_mic for b in blacklist
        ):
            mic_list.append(default_mic)

        # Add other mics, skipping duplicates and blacklisted names
        for mic in mic_list_names:
            if mic not in mic_list and not any(b in mic for b in blacklist):
                mic_list.append(mic)

        return mic_list

    def find_soundcard_id_by_name(self, name):
        scl = self.get_soundcard_list()
        id_found = [s.id for s in scl if name == s.name]

        if id_found:
            return id_found[0]
        return None

    def find_mic_id_by_name(self, name):
        micl = self.get_mic_list()
        id_found = [m.id for m in micl if name == m.name]

        if id_found:
            return id_found[0]

    def get_default_soundcard_id(self):
        return sc.default_speaker().id

    def get_default_soundcard_name(self):
        return sc.default_speaker().name

    def get_default_mic_id(self):
        return sc.default_microphone().id

    def get_default_mic_name(self):
        return sc.default_microphone().name

    def set_default_soundcard(self, id):
        cmd = "pactl set-default-sink {0}".format(id).split()
        Popen(cmd)

    def set_default_mic(self, id):
        cmd = "pactl set-default-source {0}".format(id).split()
        self.logger.info(cmd)
        Popen(cmd)

    def create_menu_popover_soundcard(self):
        self.menubutton_dashboard = Gtk.Button()
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        icon_name = self.gtk_helper.set_widget_icon_name(
            "soundcard",
            [
                "audio-volume-high-symbolic",
                "gnome-sound-properties-symbolic",
                "sound-symbolic",
                "audio-volume-high",
            ],
        )
        self.menubutton_dashboard.set_icon_name(icon_name)
        self.main_widget = (self.menubutton_dashboard, "append")
        self.gtk_helper.add_cursor_effect(self.menubutton_dashboard)
        return self.menubutton_dashboard

    def create_popover_soundcard(self, *_):
        # Create the popover dashboard if it doesn't exist yet
        if self.popover_dashboard is None:
            # Create the popover dashboard once
            self.popover_dashboard = Gtk.Popover.new()
            self.popover_dashboard.connect("closed", self.popover_is_closed)
            self.popover_dashboard.connect("notify::visible", self.popover_is_open)

            # Create a box to hold the elements vertically
            box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_margin_start(12)
            box.set_margin_end(12)
            box.set_margin_top(12)
            box.set_margin_bottom(12)

            # Create a horizontal box to hold the sound card icon and ComboBox
            sc_hbox = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            # Create the sound card icon
            sound_card_icon = Gtk.Image.new_from_icon_name("audio-card-symbolic")

            # Create the soundcard ComboBox if it doesn't exist
            if self.soundcard_combobox is None:
                self.soundcard_combobox = Gtk.ComboBoxText()
                self.soundcard_combobox.set_active(0)
                self.soundcard_combobox.connect("changed", self.on_soundcard_changed)

            # Create a horizontal box to hold the microphone icon and ComboBox
            mic_hbox = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            # Create the microphone icon
            mic_icon = Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic")

            # Create the microphone ComboBox if it doesn't exist
            if self.mic_combobox is None:
                self.mic_combobox = Gtk.ComboBoxText()
                self.mic_combobox.set_active(0)
                self.mic_combobox.connect("changed", self.on_mic_changed)

            # Add icon and ComboBox to the horizontal boxes
            sc_hbox.append(self.soundcard_combobox)
            sc_hbox.append(sound_card_icon)
            mic_hbox.append(self.mic_combobox)
            mic_hbox.append(mic_icon)

            # Add the horizontal boxes to the vertical box
            box.append(sc_hbox)
            box.append(mic_hbox)

            self.soundcard_combobox.set_active(0)
            self.mic_combobox.set_active(0)

            # Set the box as the child of the popover
            self.popover_dashboard.set_child(box)

        # Update the soundcard and mic lists every time the popover is opened
        self.update_soundcard_list()
        self.update_mic_list()

        # Set the parent widget of the popover and display it
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()

        return self.popover_dashboard

    def update_soundcard_list(self):
        """Update the soundcard list in the combobox."""
        self.soundcard_combobox.remove_all()

        soundcards = self.get_soundcard_list_names()
        for soundcard in soundcards:
            self.soundcard_combobox.append_text(soundcard)

        if soundcards:
            self.soundcard_combobox.set_active(0)  # select first item if available

    def update_mic_list(self):
        """Update the microphone list in the combobox."""
        self.mic_combobox.remove_all()
        for mic in self.get_mic_list_names():
            self.mic_combobox.append_text(mic)
        self.mic_combobox.set_active(0)

    def on_soundcard_changed(self, combobox):
        selected_option = combobox.get_active_text()
        id = self.find_soundcard_id_by_name(selected_option)
        self.set_default_soundcard(id)

    def on_mic_changed(self, combobox):
        selected_option = combobox.get_active_text()
        id = self.find_mic_id_by_name(selected_option)
        self.set_default_mic(id)

    def playerctl_list(self):
        cmd = "playerctl -l".split()
        return check_output(cmd).decode()

    def run_app_from_dashboard(self, x):
        selected_text, filename = x.get_child().MYTEXT
        cmd = "gtk-launch {}".format(filename)
        self.logger.info(cmd)
        Popen(cmd)

    def open_popover_dashboard(self, *_):
        self.create_popover_soundcard()

    def popover_is_open(self, *_):
        pass

    def popover_is_closed(self, *_):
        pass

    def show_audio_info(self):
        audio_apps = self.get_active_audio_app_info()
        for app_info in audio_apps.values():
            pass

    def on_start(self):
        pass

    def about(self):
        """
        A plugin that provides a quick dashboard to switch default sound
        output and input devices (sound cards and microphones).
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin serves as a central hub for managing audio devices
        via a dashboard popover.

        Its core logic is centered on **device discovery, UI management,
        and system-level control**:

        1.  **Device Discovery**: It uses external libraries like
            `soundcard` and `pulsectl` to discover all available audio
            output devices (speakers) and input devices (microphones)
            connected to the system. It also identifies active audio
            applications by their process ID (PID).
        2.  **Dynamic UI**: It creates a `Gtk.Popover` containing
            two `Gtk.ComboBoxText` widgets. These widgets are dynamically
            populated with the names of the discovered sound cards and
            microphones, providing a user-friendly way to select the
            desired device.
        3.  **System-Level Control**: When a user selects a new device from a
            combobox, the plugin uses `subprocess.Popen` to execute
            `pactl` commands. These commands directly interact with the
            PulseAudio server to set the newly selected sound card or
            microphone as the default system device.
        """
        return self.code_explanation.__doc__
