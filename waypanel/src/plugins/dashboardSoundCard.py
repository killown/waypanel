import os
import random
import gi
from gi.repository import Gio, Gtk, Adw
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen, check_output
from ..core.utils import Utils
import toml
import soundcard as sc
import pulsectl

from wayfire.ipc import WayfireSocket
addr = os.getenv("WAYFIRE_SOCKET")
sock = WayfireSocket(addr)

class SoundCardDashboard(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_dashboard = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()
        self.utils = Utils(application_id="com.github.utils")
        self.sock = sock

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.scripts = os.path.join(self.home, ".config/hypr/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.topbar_dashboard_config = os.path.join(
            self.config_path, "topbar-launcher.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}

    def get_view_id_by_pid(self, pid):
        lviews = self.sock.list_views()
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
        soundcard_list = []
        soundcard_list.append(self.get_default_soundcard_name())
        for soundcard in self.get_soundcard_list():
            name = soundcard.name
            if name not in soundcard_list:
                soundcard_list.append(name)
        return soundcard_list

    def get_mic_list_names(self):
        mic_list = []
        default_mic = self.get_default_mic_name()
        # sometimes it will return a non existent default mic
        # and in the mic list hold the right inputs available
        mic_list_names = [mic.name for mic in self.get_mic_list()]
        if default_mic in mic_list_names:
            mic_list.append(default_mic)
        for mic in mic_list_names:
            if mic not in mic_list:
                mic_list.append(mic)
        return mic_list

    def find_soundcard_id_by_name(self, name):
        scl = self.get_soundcard_list()
        id_found = [s.id for s in scl if name == s.name]

        if id_found:
            return id_found[0]

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
        print(cmd)
        Popen(cmd)

    def create_menu_popover_soundcard(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        self.menubutton_dashboard = Gtk.Button()
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        self.menubutton_dashboard.set_icon_name("audio-volume-high")
        return self.menubutton_dashboard

    def create_popover_soundcard(self, *_):
        # FIXME: the popup does not update the list of cards

        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.set_has_arrow(False)
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.connect("notify::visible", self.popover_is_open)

        # Set width and height of the popover dashboard
        # self.popover_dashboard.set_size_request(600, 400)

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

        # Create a ComboBox
        soundcard_combobox = Gtk.ComboBoxText()

        # Populate ComboBox with audio options
        for soundcard in self.get_soundcard_list_names():
            soundcard_combobox.append_text(soundcard)

        # Set the first option as active
        soundcard_combobox.set_active(0)

        # Connect the changed signal to a callback function
        soundcard_combobox.connect("changed", self.on_soundcard_changed)

        # Create a horizontal box to hold the sound card icon and ComboBox
        mic_hbox = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Create the sound card icon
        mic_icon = Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic")

        # Create a ComboBox
        mic_combobox = Gtk.ComboBoxText()

        # Populate ComboBox with audio options
        for mic in self.get_mic_list_names():
            mic_combobox.append_text(mic)

        # Set the first option as active
        mic_combobox.set_active(0)

        # Connect the changed signal to a callback function
        mic_combobox.connect("changed", self.on_mic_changed)

        # Add icon and ComboBox to the horizontal box
        sc_hbox.append(soundcard_combobox)
        sc_hbox.append(sound_card_icon)
        mic_hbox.append(mic_combobox)
        mic_hbox.append(mic_icon)

        # Add the horizontal box to the vertical box
        box.append(sc_hbox)
        box.append(mic_hbox)

        # apps_playing = self.get_active_audio_app_info()
        # for playing in apps_playing:
        #     title = apps_playing[playing]["application_name"]
        #     view_id = apps_playing[playing]["view_id"]
        #     # button.connect(
        #     #    "clicked", lambda *_: self.sock.go_workspace_set_focus(view_id)
        #     # )
        #     app_id = self.sock.get_view(view_id)["app-id"]
        #     icon = self.utils.get_icon(app_id, title, title)
        #     button = self.utils.create_clickable_image(
        #         icon, None, app_id, title, title, view_id
        #     )
        #
        #     box.append(button)

        # Set the box as the child of the popover
        self.popover_dashboard.set_child(box)

        # Set the parent widget of the popover and display it
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()

        return self.popover_dashboard

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
        self.utils.run_app(cmd)
        self.popover_dashboard.popdown()

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()
        if self.popover_dashboard and not self.popover_dashboard.is_visible():
            self.popover_dashboard.popup()
        if not self.popover_dashboard:
            self.popover_dashboard = self.create_popover_soundcard(self.app)

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar
