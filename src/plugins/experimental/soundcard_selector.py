def get_plugin_metadata(_):
    return {
        "enabled": True,
        "index": 2,
        "container": "top-panel-systray",
        "deps": ["top_panel"],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class SoundCardDashboard(BasePlugin):
        """
        A plugin for managing sound cards and microphones via a dashboard popover.
        """

        def __init__(self, panel_instance):
            """
            Initializes the SoundCardDashboard plugin.
            """
            super().__init__(panel_instance)
            import soundcard as sc

            self.sc = sc
            self.popover_dashboard = None
            self.soundcard_dropdown = None
            self.mic_dropdown = None
            self.menubutton_dashboard = None
            self.soundcard_handler_id = None
            self.mic_handler_id = None
            self.soundcard_model = None
            self.mic_model = None
            self.max_card_chars = self.get_config(
                ["hardware", "soundcard", "max_name_lenght"], 35
            )
            self.max_mic_chars = self.get_config(
                ["hardware", "microphone", "max_name_lenght"], 35
            )

        def on_start(self):
            self.create_menu_popover_soundcard()

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
            import pulsectl

            audio_apps = {}
            try:
                with pulsectl.Pulse("list-sink-inputs") as pulse:
                    for sink_input in pulse.sink_input_list():
                        if not sink_input.mute and sink_input.volume.value_flat > 0.0:
                            app_name = sink_input.proplist.get(
                                "application.name", "Unknown"
                            )
                            pid = int(
                                sink_input.proplist.get(
                                    "application.process.id", "Unknown"
                                )
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
            return self.sc.all_speakers()

        def get_mic_list(self):
            """
            Retrieves a list of all available microphones.
            """
            return self.sc.all_microphones()

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
                if mic.name not in mic_list and not any(
                    b in mic.name for b in blacklist
                ):
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
            return self.sc.default_speaker().id

        def get_default_soundcard_name(self):
            """
            Retrieves the name of the default sound card.
            """
            return self.sc.default_speaker().name

        def get_default_mic_id(self):
            """
            Retrieves the ID of the default microphone.
            """
            return self.sc.default_microphone().id

        def get_default_mic_name(self):
            """
            Retrieves the name of the default microphone.
            """
            return self.sc.default_microphone().name

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
                self.logger.exception(
                    f"Failed to set default soundcard with pactl: {e}"
                )

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
                self.logger.exception(
                    f"Failed to set default microphone with pactl: {e}"
                )

        def create_menu_popover_soundcard(self):
            """
            Creates the main button for the soundcard dashboard popover.
            """
            self.menubutton_dashboard = self.gtk.Button()
            self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
            icon_name = self.gtk_helper.icon_exist(
                "soundcard-symbolic",
                [
                    "audio-volume-high-symbolic",
                    "gnome-sound-properties-symbolic",
                    "sound-symbolic",
                ],
            )
            self.menubutton_dashboard.set_icon_name(icon_name)
            self.menubutton_dashboard.add_css_class("soundcard-selector")
            self.main_widget = (self.menubutton_dashboard, "append")
            self.gtk_helper.add_cursor_effect(self.menubutton_dashboard)
            return self.menubutton_dashboard

        def create_popover_soundcard(self, *_):
            """
            Refactored to use self.create_popover, while preserving the complex UI and
            signal handler blocking logic from the original implementation.
            """
            if self.popover_dashboard is None:
                self.popover_dashboard = self.create_popover(
                    parent_widget=self.menubutton_dashboard,
                    css_class="soundcard-dashboard-popover",
                    has_arrow=False,
                    closed_handler=self.popover_is_closed,
                    visible_handler=self.popover_is_open,
                )
                box = self.gtk.Box.new(
                    orientation=self.gtk.Orientation.VERTICAL, spacing=6
                )
                box.set_margin_start(12)
                box.set_margin_end(12)
                box.set_margin_top(12)
                box.set_margin_bottom(12)
                self.soundcard_model = self.gtk.StringList.new([])
                self.soundcard_dropdown = self.gtk.DropDown.new(
                    self.soundcard_model, None
                )
                self.mic_model = self.gtk.StringList.new([])
                self.mic_dropdown = self.gtk.DropDown.new(self.mic_model, None)
                self.soundcard_handler_id = self.soundcard_dropdown.connect(
                    "notify::selected-item", self.on_soundcard_changed
                )
                self.mic_handler_id = self.mic_dropdown.connect(
                    "notify::selected-item", self.on_mic_changed
                )
                self.soundcard_dropdown.set_size_request(200, -1)
                self.mic_dropdown.set_size_request(200, -1)
                sc_hbox = self.gtk.Box.new(
                    orientation=self.gtk.Orientation.HORIZONTAL, spacing=6
                )
                sound_card_icon = self.gtk.Image.new_from_icon_name(
                    "audio-card-symbolic"
                )
                sc_hbox.append(sound_card_icon)
                sc_hbox.append(self.soundcard_dropdown)
                mic_hbox = self.gtk.Box.new(
                    orientation=self.gtk.Orientation.HORIZONTAL, spacing=6
                )
                mic_icon = self.gtk.Image.new_from_icon_name(
                    "audio-input-microphone-symbolic"
                )
                mic_hbox.append(mic_icon)
                mic_hbox.append(self.mic_dropdown)
                box.append(sc_hbox)
                box.append(mic_hbox)
                self.popover_dashboard.set_child(box)
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
            (Preserved: No refactoring applied to this method.)
            """
            soundcards = self.get_soundcard_list_names()
            self.soundcard_model.splice(0, self.soundcard_model.get_n_items(), [])  # pyright: ignore
            for name in soundcards:
                display_name = (
                    (name[: self.max_card_chars] + "...")
                    if len(name) > self.max_card_chars
                    else name
                )
                self.soundcard_model.append(display_name)  # pyright: ignore
            if soundcards:
                try:
                    default_name = self.get_default_soundcard_name()
                    if default_name in soundcards:
                        index = soundcards.index(default_name)
                        self.soundcard_dropdown.set_selected(index)  # pyright: ignore
                    else:
                        self.soundcard_dropdown.set_selected(0)  # pyright: ignore
                except (ValueError, Exception) as e:
                    self.logger.exception(
                        f"Failed to set default soundcard active: {e}"
                    )
                    self.soundcard_dropdown.set_selected(0)  # pyright: ignore

        def update_mic_list(self):
            """
            Updates the microphone list in the dropdown, truncating names as needed.
            (Preserved: No refactoring applied to this method.)
            """
            mics = self.get_mic_list_names()
            self.mic_model.splice(0, self.mic_model.get_n_items(), [])  # pyright: ignore
            for name in mics:
                display_name = (
                    (name[: self.max_mic_chars] + "...")
                    if len(name) > self.max_mic_chars
                    else name
                )
                self.mic_model.append(display_name)  # pyright: ignore
            if mics:
                try:
                    default_name = self.get_default_mic_name()
                    if default_name in mics:
                        index = mics.index(default_name)
                        self.mic_dropdown.set_selected(index)  # pyright: ignore
                    else:
                        self.mic_dropdown.set_selected(0)  # pyright: ignore
                except (ValueError, Exception) as e:
                    self.logger.exception(
                        f"Failed to set default microphone active: {e}"
                    )
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
            self.subprocess.Popen(
                cmd, stdout=self.subprocess.DEVNULL, stderr=self.subprocess.DEVNULL
            )
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
            1. **Popover Helper Used**: `create_popover_soundcard` now uses
               `self.create_popover` from the base plugin to handle popover
               instantiation, connection, and parenting, while keeping the critical
               internal UI construction and signal logic untouched.
            Its core logic is centered on **device discovery, UI management,
            and system-level control**:
            1.  **Device Discovery**: It uses external libraries like
                `soundcard` and `pulsectl` to discover all available audio
                devices.
            2.  **Dynamic UI**: It creates a `self.gtk.Popover` containing
                two `self.gtk.DropDown` widgets dynamically populated using a
                `self.gtk.StringList` model. The UI uses signal blocking/unblocking
                (`handler_block`/`handler_unblock`) to prevent automatic system
                changes when the dropdown lists are programmatically updated.
            3.  **System-Level Control**: User selection changes trigger
                `pactl` commands via `self.run_cmd` to set the new default device.
            """
            return self.code_explanation.__doc__

    return SoundCardDashboard
