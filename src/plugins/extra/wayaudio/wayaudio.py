def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.advanced_volume"
    container, id = panel.config_handler.get_plugin_container("top-panel-systray", id)
    return {
        "id": id,
        "name": "Advanced Volume Control",
        "version": "2.0.3",
        "deps": ["top_panel", "css_generator"],
        "index": 11,
        "container": container,
        "enabled": True,
        "description": "Professional audio manager with clean scrollbar gutters.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    from gi.repository import Gtk
    import pulsectl
    import soundcard as sc
    from collections import defaultdict

    class AdvancedVolumePlugin(BasePlugin):
        def on_start(self):
            """Initializes the PulseAudio controller and registers settings hints."""
            self.pulse = pulsectl.Pulse("waypanel-volume-mgr")
            self.sc = sc
            self.popover = None
            self.show_ignored = False

            if "css_generator" in self.plugins:
                self.plugins["css_generator"].install_css("wayaudio.css")

            self.max_name_lenght = self.get_plugin_setting_add_hint(
                ["name_lenght"], 35, "Maximum character length for device names."
            )
            self.soundcard_blacklist = self.get_plugin_setting_add_hint(
                ["soundcard", "blacklist"], ["Navi"], "Keywords to hide output devices."
            )
            self.mic_blacklist = self.get_plugin_setting_add_hint(
                ["microphone", "blacklist"], ["Navi"], "Keywords to hide input devices."
            )
            self.ignored_streams = self.get_plugin_setting_add_hint(
                ["ignored_streams"], [], "List of application names currently hidden."
            )

            self.btn = Gtk.Button()
            self.btn.add_css_class("volume-panel-button")
            self.btn.set_icon_name("audio-volume-high-symbolic")
            self.btn.connect("clicked", self.toggle_popover)
            self.add_cursor_effect(self.btn)
            self.main_widget = (self.btn, "append")

        def toggle_popover(self, *_):
            """Toggles the visibility of the advanced audio dashboard."""
            if not self.popover:
                # use_scrolled=True returns (popover, scrolled_window, listbox)
                self.popover, self.sw, _ = self.create_popover(  # pyright: ignore
                    parent_widget=self.btn,
                    css_class="volume-popover-root",
                    use_scrolled=True,
                    max_height=600,
                    min_width=380,
                )
                # Force the scrollbar to occupy its own space (Non-overlay)
                if self.sw:
                    self.sw.set_overlay_scrolling(False)

            self.update_ui()
            self.popover.popup()

        def _get_filtered_devices(self, is_mic=False):
            """Filters devices based on the user-defined blacklist."""
            devices = self.sc.all_microphones() if is_mic else self.sc.all_speakers()
            blacklist = self.mic_blacklist if is_mic else self.soundcard_blacklist
            return [d for d in devices if not any(b in d.name for b in blacklist)]

        def update_ui(self):
            """Rebuilds the UI structure and synchronizes current system devices."""
            root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            root_box.add_css_class("volume-content-wrapper")

            s_info = self.pulse.server_info()
            curr_sink_name = s_info.default_sink_name  # pyright: ignore
            curr_source_name = s_info.default_source_name  # pyright: ignore

            # --- DEVICE ROUTING ---
            routing_header = Gtk.Button()
            routing_header.add_css_class("volume-section-toggle-header")
            r_head_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            rlbl = Gtk.Label(
                label="Device Routing", xalign=0, css_classes=["volume-header-text"]
            )
            r_head_box.append(rlbl)
            r_icon = Gtk.Image(icon_name="pan-down-symbolic")
            r_head_box.append(r_icon)
            routing_header.set_child(r_head_box)

            routing_header.add_css_class("volume-section-toggle-header")
            routing_header.set_margin_top(
                8
            )  # Adds space at the very top of the popover

            routing_revealer = Gtk.Revealer()
            routing_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
            routing_header.connect(
                "clicked",
                lambda _: routing_revealer.set_reveal_child(
                    not routing_revealer.get_reveal_child()
                ),
            )
            routing_revealer.add_css_class("routing-revealer")

            routing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            routing_box.set_margin_start(12)
            routing_box.set_margin_end(12)
            routing_box.set_margin_top(10)
            routing_box.set_margin_bottom(12)

            speakers = self._get_filtered_devices(is_mic=False)
            s_model = Gtk.StringList.new(
                [s.name[: self.max_name_lenght] for s in speakers]
            )
            s_drop = Gtk.DropDown.new(s_model, None)
            s_drop.add_css_class("volume-device-dropdown")
            active_sink_idx = next(
                (i for i, s in enumerate(speakers) if s.id in curr_sink_name), 0
            )
            s_drop.set_selected(active_sink_idx)
            s_drop.connect(
                "notify::selected-item",
                lambda d, _: self.run_cmd(
                    f"pactl set-default-sink {speakers[d.get_selected()].id}"
                ),
            )

            mics = self._get_filtered_devices(is_mic=True)
            m_model = Gtk.StringList.new([m.name[: self.max_name_lenght] for m in mics])
            m_drop = Gtk.DropDown.new(m_model, None)
            m_drop.add_css_class("volume-device-dropdown")
            active_source_idx = next(
                (i for i, m in enumerate(mics) if m.id in curr_source_name), 0
            )
            m_drop.set_selected(active_source_idx)
            m_drop.connect(
                "notify::selected-item",
                lambda d, _: self.run_cmd(
                    f"pactl set-default-source {mics[d.get_selected()].id}"
                ),
            )

            routing_box.append(
                Gtk.Label(
                    label="Output Device",
                    xalign=0,
                    css_classes=["volume-app-name-label"],
                )
            )
            routing_box.append(s_drop)
            routing_box.append(
                Gtk.Label(
                    label="Input Device",
                    xalign=0,
                    css_classes=["volume-app-name-label"],
                )
            )
            routing_box.append(m_drop)
            routing_revealer.set_child(routing_box)

            root_box.append(routing_header)
            root_box.append(routing_revealer)

            # --- SYSTEM MASTER ---
            master_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            master_box.add_css_class("volume-section-master")
            master_box.set_margin_start(12)
            master_box.set_margin_end(12)
            master_box.set_margin_top(12)
            master_box.set_margin_bottom(12)

            mlbl = Gtk.Label(
                label="System Volume", xalign=0, css_classes=["volume-header-text"]
            )
            master_box.append(mlbl)
            sink = self.pulse.get_sink_by_name(curr_sink_name)
            master_box.append(
                self.create_volume_row(sink, is_sink=True, type_class="master")
            )
            root_box.append(master_box)
            root_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

            # --- APPLICATIONS ---
            apps_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            apps_header.set_margin_start(12)
            apps_header.set_margin_end(12)
            apps_header.set_margin_top(12)
            albl = Gtk.Label(
                label="Applications",
                xalign=0,
                hexpand=True,
                css_classes=["volume-header-text"],
            )

            ignore_toggle = Gtk.Button(css_classes=["volume-ignore-toggle"])
            ignore_toggle.set_icon_name(
                "view-conceal-symbolic"
                if not self.show_ignored
                else "view-visible-symbolic"
            )
            ignore_toggle.connect("clicked", self._on_toggle_ignored)
            apps_header.append(albl)
            apps_header.append(ignore_toggle)
            root_box.append(apps_header)

            grouped_apps = defaultdict(list)
            for app in self.pulse.sink_input_list():
                app_name = app.proplist.get("application.name", "Unknown")
                grouped_apps[app_name].append(app)

            apps_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            apps_container.set_margin_start(12)
            apps_container.set_margin_end(12)
            apps_container.set_margin_top(12)
            apps_container.set_margin_bottom(12)

            for app_name, streams in grouped_apps.items():
                is_ignored = app_name in self.ignored_streams
                if is_ignored and not self.show_ignored:
                    continue

                app_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                app_card.add_css_class("volume-app-entry")
                if is_ignored:
                    app_card.add_css_class("ignored")

                title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                icon_lookup = app_name.lower().replace(" ", "-")
                app_icon = Gtk.Image(pixel_size=24)
                app_icon.set_from_icon_name(self.icon_exist(icon_lookup))

                tlbl = Gtk.Label(
                    label=app_name,
                    xalign=0,
                    hexpand=True,
                    css_classes=["volume-app-name-label"],
                )

                act_btn = Gtk.Button(css_classes=["volume-app-action-btn"])
                act_btn.set_icon_name(
                    "list-remove-symbolic"
                    if app_name not in self.ignored_streams
                    else "list-add-symbolic"
                )
                act_btn.connect("clicked", self._on_ignore_click, app_name)

                title_row.append(app_icon)
                title_row.append(tlbl)
                title_row.append(act_btn)
                app_card.append(title_row)

                for stream in streams:
                    stream_box = Gtk.Box(
                        orientation=Gtk.Orientation.VERTICAL, spacing=4
                    )
                    media_title = (
                        stream.proplist.get("media.title")
                        or stream.proplist.get("media.name")
                        or "Playback Stream"
                    )
                    title_lbl = Gtk.Label(
                        label=media_title, xalign=0, css_classes=["volume-stream-title"]
                    )
                    title_lbl.set_ellipsize(3)  # pyright: ignore

                    stream_box.append(title_lbl)
                    stream_box.append(
                        self.create_volume_row(stream, is_sink=False, type_class="app")
                    )
                    stream_box.append(self.create_sink_selector(stream))

                    app_card.append(stream_box)
                    if stream != streams[-1]:
                        app_card.append(
                            Gtk.Separator(css_classes=["volume-stream-separator"])
                        )

                apps_container.append(app_card)

            root_box.append(apps_container)
            if self.sw:
                self.sw.set_child(root_box)

        def _on_toggle_ignored(self, _):
            self.show_ignored = not self.show_ignored
            self.update_ui()

        def _on_ignore_click(self, _, app_name):
            if app_name in self.ignored_streams:
                self.ignored_streams.remove(app_name)
            else:
                self.ignored_streams.append(app_name)
            self.set_plugin_setting(["ignored_streams"], self.ignored_streams)
            self.update_ui()

        def create_volume_row(self, audio_obj, is_sink=True, type_class="app"):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add_css_class(f"volume-row-{type_class}")

            mute_btn = Gtk.Button(css_classes=[f"volume-mute-button-{type_class}"])
            mute_btn.set_icon_name(
                "audio-volume-muted-symbolic"
                if audio_obj.mute
                else "audio-volume-high-symbolic"
            )

            vol_percent = int(audio_obj.volume.value_flat * 100)
            percent_lbl = Gtk.Label(
                label=f"{vol_percent}%", css_classes=["volume-percentage-label"]
            )
            percent_lbl.set_size_request(40, -1)

            adj = Gtk.Adjustment(
                value=vol_percent, lower=0, upper=150, step_increment=1
            )
            scale = Gtk.Scale(
                orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=adj,
                hexpand=True,
                draw_value=False,
            )
            scale.add_css_class(f"volume-scale-{type_class}")

            def on_val_changed(s):
                val_raw = s.get_adjustment().get_value()
                val_norm = val_raw / 100.0
                percent_lbl.set_label(f"{int(val_raw)}%")
                if is_sink:
                    self.pulse.volume_set_all_chans(audio_obj, val_norm)
                else:
                    self.pulse.sink_input_volume_set(
                        audio_obj.index,
                        pulsectl.PulseVolumeInfo(
                            val_norm, len(audio_obj.volume.values)
                        ),
                    )

            scale.connect("value-changed", on_val_changed)
            row.append(mute_btn)
            row.append(scale)
            row.append(percent_lbl)
            return row

        def create_sink_selector(self, app_input):
            sinks = self.pulse.sink_list()
            model = Gtk.StringList.new([s.description for s in sinks])
            dropdown = Gtk.DropDown.new(model, None)
            dropdown.add_css_class("volume-device-dropdown")
            current_idx = next(
                (i for i, s in enumerate(sinks) if s.index == app_input.sink), 0
            )
            dropdown.set_selected(current_idx)
            dropdown.connect(
                "notify::selected-item",
                lambda d, _: self.pulse.sink_input_move(
                    app_input.index, sinks[d.get_selected()].index
                ),
            )
            return dropdown

        def on_disable(self):
            if self.pulse:
                self.pulse.close()

    return AdvancedVolumePlugin
