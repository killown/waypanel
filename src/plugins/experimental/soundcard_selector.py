from subprocess import Popen, DEVNULL
import pulsectl
import soundcard as sc
from gi.repository import Gtk  # pyright: ignore
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """
    Defines the placement and order of the plugin on the panel.
    """
    position = "top-panel-systray"
    order = 3
    return position, order


def initialize_plugin(panel_instance):
    """
    Initializes and returns the plugin instance.
    """
    if ENABLE_PLUGIN:
        card = SoundCardDashboard(panel_instance)
        card.create_menu_popover_soundcard()
        return card


class SoundCardDashboard(BasePlugin):
    """
    A plugin for managing sound cards and microphones via a dashboard popover.
    """

    def __init__(self, panel_instance):
        """
        Initializes the SoundCardDashboard plugin.
        """
        super().__init__(panel_instance)
        self.popover_dashboard = None
        self.soundcard_dropdown = None
        self.mic_dropdown = None
        self.menubutton_dashboard = None
        self.soundcard_handler_id = None
        self.mic_handler_id = None
        self.max_card_chars = self.get_config(
            ["hardware", "soundcard", "max_name_lenght"], 35
        )
        self.max_mic_chars = self.get_config(
            ["hardware", "microphone", "max_name_lenght"], 35
        )

    def get_view_id_by_pid(self, pid):
        """
        Retrieves the view ID for a given process ID (PID).
        """
        lviews = self.ipc.list_views()
        for view in lviews:
            if pid == view["pid"]:
                return view["id"]

    def get_active_audio_app_info(self):
        """
        Retrieves information about currently active audio applications.
        """
        audio_apps = {}
        try:
            with pulsectl.Pulse("list-sink-inputs") as pulse:
                for sink_input in pulse.sink_input_list():
                    if not sink_input.mute and sink_input.volume.value_flat > 0.0:
                        app_name = sink_input.proplist.get(
                            "application.name", "Unknown"
                        )
                        pid = int(
                            sink_input.proplist.get("application.process.id", "Unknown")
                        )
                        audio_apps[pid] = {
                            "application_name": app_name,
                            "index": sink_input.index,
                            "view_id": self.get_view_id_by_pid(pid),
                        }
        except pulsectl.PulseOperationFailed as e:
            self.logger.exception(f"Failed to connect to PulseAudio: {e}")
        return audio_apps

    def get_soundcard_list(self):
        """
        Retrieves a list of all available sound card speakers.
        """
        return sc.all_speakers()

    def get_mic_list(self):
        """
        Retrieves a list of all available microphones.
        """
        return sc.all_microphones()

    def get_soundcard_list_names(self):
        """
        Retrieves a list of sound card names, excluding blacklisted ones.
        """
        blacklist = self.get_config(["hardware", "soundcard", "blacklist"], [])
        if isinstance(blacklist, str):
            blacklist = [blacklist]
        soundcard_list = []
        try:
            default_name = self.get_default_soundcard_name()
            if not any(b in default_name for b in blacklist):
                soundcard_list.append(default_name)
        except Exception as e:
            self.logger.exception(f"Could not get default speaker: {e}")
        for soundcard in self.get_soundcard_list():
            name = soundcard.name
            if name not in soundcard_list and not any(b in name for b in blacklist):
                soundcard_list.append(name)
        return soundcard_list

    def get_mic_list_names(self):
        """
        Retrieves a list of microphone names, excluding blacklisted ones.
        """
        mic_list = []
        blacklist = self.get_config(["hardware", "microphone", "blacklist"], [])
        if isinstance(blacklist, str):
            blacklist = [blacklist]
        try:
            default_mic = self.get_default_mic_name()
            mic_list_names = [mic.name for mic in self.get_mic_list()]
            if (
                default_mic
                and default_mic in mic_list_names
                and not any(b in default_mic for b in blacklist)
            ):
                mic_list.append(default_mic)
        except Exception as e:
            self.logger.exception(f"Could not get default microphone: {e}")
        for mic in self.get_mic_list():
            if mic.name not in mic_list and not any(b in mic.name for b in blacklist):
                mic_list.append(mic.name)
        return mic_list

    def find_soundcard_id_by_name(self, name):
        """
        Finds a sound card ID by its name.
        """
        scl = self.get_soundcard_list()
        id_found = [s.id for s in scl if name == s.name]
        if id_found:
            return id_found[0]
        return None

    def find_mic_id_by_name(self, name):
        """
        Finds a microphone ID by its name.
        """
        micl = self.get_mic_list()
        id_found = [m.id for m in micl if name == m.name]
        if id_found:
            return id_found[0]
        return None

    def get_default_soundcard_id(self):
        """
        Retrieves the ID of the default sound card.
        """
        return sc.default_speaker().id

    def get_default_soundcard_name(self):
        """
        Retrieves the name of the default sound card.
        """
        return sc.default_speaker().name

    def get_default_mic_id(self):
        """
        Retrieves the ID of the default microphone.
        """
        return sc.default_microphone().id

    def get_default_mic_name(self):
        """
        Retrieves the name of the default microphone.
        """
        return sc.default_microphone().name

    def set_default_soundcard(self, id):
        """
        Sets the default sound card using pactl.
        """
        if not id:
            self.logger.warning("No soundcard ID provided.")
            return
        try:
            cmd = f"pactl set-default-sink {id}"
            self.logger.info(f"Attempting to set default sink with: {cmd}")
            self.run_cmd(cmd)
        except FileNotFoundError:
            self.logger.error("pactl not found. Cannot set default soundcard.")
        except Exception as e:
            self.logger.exception(f"Failed to set default soundcard with pactl: {e}")

    def set_default_mic(self, id):
        """
        Sets the default microphone using pactl.
        """
        if not id:
            self.logger.warning("No microphone ID provided.")
            return
        try:
            cmd = f"pactl set-default-source {id}"
            self.logger.info(f"Attempting to set default source with: {cmd}")
            self.run_cmd(cmd)
        except FileNotFoundError:
            self.logger.error("pactl not found. Cannot set default microphone.")
        except Exception as e:
            self.logger.exception(f"Failed to set default microphone with pactl: {e}")

    def create_menu_popover_soundcard(self):
        """
        Creates the main button for the soundcard dashboard popover.
        """
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
        """
        Creates and displays the dashboard popover with sound card and microphone controls.
        This method is structured in four phases to prevent unwanted signal emissions:
        1.  **Initialization (`if self.popover_dashboard is None`):**
            The UI widgets (Popover, Boxes, Dropdowns) are created only once.
            Crucially, the 'notify::selected-item' signal handlers are connected here,
            and their IDs (`soundcard_handler_id`, `mic_handler_id`) are stored.
            The `self.popover_dashboard.set_parent()` call is also here, as reparenting
            a GTK widget multiple times causes a critical error.
        2.  **Signal Blocking (Before Update):**
            The stored handler IDs are used with `handler_block()` to temporarily disable
            the `on_soundcard_changed` and `on_mic_changed` methods. This is essential
            because the next step, updating the lists, will call `set_selected()`, which
            emits the 'notify::selected-item' signal. Blocking prevents these automatic
            emissions from triggering the `pactl` commands unnecessarily.
        3.  **UI Update (List Population):**
            `self.update_soundcard_list()` and `self.update_mic_list()` are called.
            These methods populate the dropdowns and set the default active item using
            `set_selected()`. Because the handlers are blocked, no signals are processed.
        4.  **Signal Unblocking (After Update):**
            The stored handler IDs are used with `handler_unblock()` to re-enable the
            change detection. The dropdowns are now ready to respond to actual user clicks.
        Finally, `self.popover_dashboard.popup()` is called to display the dashboard.
        """
        if self.popover_dashboard is None:
            self.popover_dashboard = Gtk.Popover.new()
            self.popover_dashboard.connect("closed", self.popover_is_closed)
            self.popover_dashboard.connect("notify::visible", self.popover_is_open)
            box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_margin_start(12)
            box.set_margin_end(12)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            self.soundcard_model = Gtk.StringList.new([])
            self.soundcard_dropdown = Gtk.DropDown.new(self.soundcard_model, None)
            self.mic_model = Gtk.StringList.new([])
            self.mic_dropdown = Gtk.DropDown.new(self.mic_model, None)
            self.soundcard_handler_id = self.soundcard_dropdown.connect(
                "notify::selected-item", self.on_soundcard_changed
            )
            self.mic_handler_id = self.mic_dropdown.connect(
                "notify::selected-item", self.on_mic_changed
            )
            self.soundcard_dropdown.set_size_request(200, -1)
            self.mic_dropdown.set_size_request(200, -1)
            sc_hbox = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            sound_card_icon = Gtk.Image.new_from_icon_name("audio-card-symbolic")
            sc_hbox.append(sound_card_icon)
            sc_hbox.append(self.soundcard_dropdown)
            mic_hbox = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            mic_icon = Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic")
            mic_hbox.append(mic_icon)
            mic_hbox.append(self.mic_dropdown)
            box.append(sc_hbox)
            box.append(mic_hbox)
            self.popover_dashboard.set_child(box)
            self.popover_dashboard.set_parent(self.menubutton_dashboard)  # pyright: ignore
        if self.soundcard_handler_id:
            self.soundcard_dropdown.handler_block(self.soundcard_handler_id)  # pyright: ignore
        if self.mic_handler_id:
            self.mic_dropdown.handler_block(self.mic_handler_id)  # pyright: ignore
        self.schedule_in_gtk_thread(self.update_soundcard_list)
        self.schedule_in_gtk_thread(self.update_mic_list)
        if self.soundcard_handler_id:
            self.soundcard_dropdown.handler_unblock(self.soundcard_handler_id)  # pyright: ignore
        if self.mic_handler_id:
            self.mic_dropdown.handler_unblock(self.mic_handler_id)  # pyright: ignore
        self.schedule_in_gtk_thread(self.popover_dashboard.popup)
        return self.popover_dashboard

    def update_soundcard_list(self):
        """
        Updates the list of sound cards in the dropdown, truncating names as needed.
        """
        soundcards = self.get_soundcard_list_names()
        self.soundcard_model.splice(0, self.soundcard_model.get_n_items(), [])
        for name in soundcards:
            display_name = (
                (name[: self.max_card_chars] + "...")
                if len(name) > self.max_card_chars
                else name
            )
            self.soundcard_model.append(display_name)
        if soundcards:
            try:
                default_name = self.get_default_soundcard_name()
                if default_name in soundcards:
                    index = soundcards.index(default_name)
                    self.soundcard_dropdown.set_selected(index)  # pyright: ignore
                else:
                    self.soundcard_dropdown.set_selected(0)  # pyright: ignore
            except (ValueError, Exception) as e:
                self.logger.exception(f"Failed to set default soundcard active: {e}")
                self.soundcard_dropdown.set_selected(0)  # pyright: ignore

    def update_mic_list(self):
        """
        Updates the microphone list in the dropdown, truncating names as needed.
        """
        mics = self.get_mic_list_names()
        self.mic_model.splice(0, self.mic_model.get_n_items(), [])
        for name in mics:
            display_name = (
                (name[: self.max_mic_chars] + "...")
                if len(name) > self.max_mic_chars
                else name
            )
            self.mic_model.append(display_name)
        if mics:
            try:
                default_name = self.get_default_mic_name()
                if default_name in mics:
                    index = mics.index(default_name)
                    self.mic_dropdown.set_selected(index)  # pyright: ignore
                else:
                    self.mic_dropdown.set_selected(0)  # pyright: ignore
            except (ValueError, Exception) as e:
                self.logger.exception(f"Failed to set default microphone active: {e}")
                self.mic_dropdown.set_selected(0)  # pyright: ignore

    def on_soundcard_changed(self, dropdown, param):
        """
        Handles the event when the soundcard selection is changed.
        This method should only fire on user interaction.
        """
        selected_item = dropdown.get_selected_item()
        if selected_item is None:
            return
        selected_index = dropdown.get_selected()
        full_name = self.get_soundcard_list_names()[selected_index]
        id = self.find_soundcard_id_by_name(full_name)
        self.set_default_soundcard(id)

    def on_mic_changed(self, dropdown, param):
        """
        Handles the event when the microphone selection is changed.
        This method should only fire on user interaction.
        """
        selected_item = dropdown.get_selected_item()
        if selected_item is None:
            return
        selected_index = dropdown.get_selected()
        full_name = self.get_mic_list_names()[selected_index]
        id = self.find_mic_id_by_name(full_name)
        self.set_default_mic(id)

    def playerctl_list(self):
        """
        Executes the 'playerctl -l' command to list available players.
        """
        cmd = ["playerctl", "-l"]
        Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        return ""

    def open_popover_dashboard(self, *_):
        """
        Opens the dashboard popover for soundcard and mic selection.
        """
        self.create_popover_soundcard()

    def popover_is_open(self, *_):
        """
        Placeholder method for when the popover is open.
        """
        pass

    def popover_is_closed(self, *_):
        """
        Placeholder method for when the popover is closed.
        """
        pass

    def show_audio_info(self):
        """
        Retrieves and processes information about active audio applications.
        """
        audio_apps = self.get_active_audio_app_info()
        for app_info in audio_apps.values():
            pass

    def on_start(self):
        """
        Placeholder method to be called at the start of the application.
        """
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
        **Refactoring Notes:**
        1. **Configuration:** All configuration access was updated to the *exact* format requested:
           `self.get_config(["hardware", "soundcard", "max_name_lenght"], default_value)`, where the key path is a list of nested strings.
        2. **Logging:** Global `logging` setup was removed. All local `logger` calls
           were replaced with `self.logger` (inherited from `BasePlugin`). Generic
           exception handlers (`except Exception as e:`) correctly use
           `self.logger.exception()` to include the full traceback.
        Its core logic is centered on **device discovery, UI management,
        and system-level control**:
        1.  **Device Discovery**: It uses external libraries like
            `soundcard` and `pulsectl` to discover all available audio
            output devices (speakers) and input devices (microphones)
            connected to the system. It also identifies active audio
            applications by their process ID (PID).
        2.  **Dynamic UI**: It creates a `Gtk.Popover` containing
            two `Gtk.DropDown` widgets. These widgets are dynamically
            populated using a `Gtk.StringList` model with the names of the
            discovered sound cards and microphones, providing a user-friendly
            way to select the desired device.
        3.  **System-Level Control**: When a user selects a new device from a
            dropdown, the plugin uses `self.run_cmd` to execute
            `pactl` commands. These commands directly interact with the
            PulseAudio server to set the newly selected sound card or
            microphone as the default system device.
        """
        return self.code_explanation.__doc__
