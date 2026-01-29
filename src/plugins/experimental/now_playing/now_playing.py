def get_plugin_metadata(_):
    id = "org.waypanel.plugin.now_playing"
    return {
        "id": id,
        "name": "Media Player",
        "version": "3.3.1",
        "index": 20,
        "description": "Dedicated media control button with marquee scrolling and pulse effects.",
        "container": "background",
        "deps": ["css_generator", "top_panel"],
        "enabled": True,
    }


def get_plugin_class():
    import gi
    import gc
    import math

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, GLib, GdkPixbuf, Gio, Pango, Gdk
    from src.plugins.core._base import BasePlugin
    from src.shared.dbus_helpers import DbusHelpers
    from dbus_fast.aio import MessageBus
    from dbus_fast import BusType

    class PlayerRow(Gtk.Box):
        def __init__(self, service_name, plugin):
            super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.service_name = service_name
            self.plugin = plugin
            self.last_art_url = None

            self._scroll_pos = 0
            self._full_title = ""
            self._full_artist = ""
            self._scroll_timer = None

            self._setup_ui()

        def add_cursor_effect(self, widget):
            """Adds the hover pulse effect and pointer cursor to control buttons."""
            motion = Gtk.EventControllerMotion()
            widget._cursor_anim_id = None
            widget._watchdog_id = None

            def on_tick(widget, frame_clock):
                duration = 300000.0  # 300ms
                if not hasattr(widget, "_anim_start_time"):
                    return False
                elapsed = frame_clock.get_frame_time() - widget._anim_start_time
                if elapsed > duration:
                    widget.set_opacity(1.0)
                    widget._cursor_anim_id = None
                    return False

                intensity = math.sin((elapsed / duration) * math.pi)
                widget.set_opacity(1.0 - (0.3 * intensity))
                return True

            def handle_event(controller, *args):
                is_enter = len(args) > 1
                if widget._cursor_anim_id is not None:
                    widget.remove_tick_callback(widget._cursor_anim_id)
                    widget._cursor_anim_id = None
                if widget._watchdog_id:
                    GLib.source_remove(widget._watchdog_id)
                    widget._watchdog_id = None

                if is_enter:
                    widget.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
                    clock = widget.get_frame_clock()
                    if clock:
                        widget._anim_start_time = clock.get_frame_time()
                        widget._cursor_anim_id = widget.add_tick_callback(on_tick)
                    widget._watchdog_id = GLib.timeout_add(
                        500,
                        lambda: [
                            widget.set_opacity(1.0),
                            setattr(widget, "_watchdog_id", None),
                            False,
                        ][2],
                    )
                else:
                    widget.set_cursor(None)
                    widget.set_opacity(1.0)

            motion.connect("enter", handle_event)
            motion.connect("leave", handle_event)
            widget.add_controller(motion)

        def _setup_ui(self):
            self.add_css_class("player-row")
            self.set_halign(Gtk.Align.CENTER)

            self.art_image = Gtk.Image()
            self.art_image.set_pixel_size(120)
            self.art_image.set_size_request(120, 120)
            self.art_image.set_halign(Gtk.Align.CENTER)
            self.art_image.add_css_class("player-art")
            self.append(self.art_image)

            info_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info_vbox.set_halign(Gtk.Align.CENTER)

            self.title_label = Gtk.Label(label="Unknown Title")
            self.title_label.add_css_class("player-title")
            self.title_label.set_xalign(0.5)
            self.title_label.set_max_width_chars(25)
            self.title_label.set_ellipsize(Pango.EllipsizeMode.NONE)

            self.artist_label = Gtk.Label(label="Unknown Artist")
            self.artist_label.add_css_class("player-artist")
            self.artist_label.set_xalign(0.5)
            self.artist_label.set_max_width_chars(25)
            self.artist_label.set_ellipsize(Pango.EllipsizeMode.NONE)

            controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
            controls_box.set_halign(Gtk.Align.CENTER)
            controls_box.add_css_class("player-controls")

            self.btn_prev = self._create_btn("media-skip-backward-symbolic", "previous")
            self.btn_play = self._create_btn(
                "media-playback-start-symbolic", "play_pause"
            )
            self.btn_next = self._create_btn("media-skip-forward-symbolic", "next")

            for btn in [self.btn_prev, self.btn_play, self.btn_next]:
                controls_box.append(btn)

            info_vbox.append(self.title_label)
            info_vbox.append(self.artist_label)
            info_vbox.append(controls_box)
            self.append(info_vbox)

        def _create_btn(self, icon, action):
            btn = Gtk.Button.new_from_icon_name(icon)
            btn.add_css_class("flat")
            self.add_cursor_effect(btn)
            btn.connect(
                "clicked",
                lambda _: self.plugin.run_in_async_task(
                    self.plugin.local_dbus.player_action(self.service_name, action)
                ),
            )
            return btn

        def update_ui(self, data):
            title = data.get("title", "Unknown")
            artist = data.get("artist", "Unknown")

            if title != self._full_title or artist != self._full_artist:
                self._full_title, self._full_artist = title, artist
                self._scroll_pos = 0
                self._start_marquee()

            icon = (
                "media-playback-pause-symbolic"
                if data.get("status") == "Playing"
                else "media-playback-start-symbolic"
            )
            self.btn_play.set_icon_name(icon)

            art_url = data.get("art_url")
            if art_url and art_url != self.last_art_url:
                self.last_art_url = art_url
                self._load_art_async(art_url)

        def _start_marquee(self):
            if self._scroll_timer:
                GLib.source_remove(self._scroll_timer)
            if len(self._full_title) > 25 or len(self._full_artist) > 25:
                self._scroll_timer = GLib.timeout_add(250, self._on_marquee_tick)
            else:
                self.title_label.set_text(self._full_title)
                self.artist_label.set_text(self._full_artist)

        def _on_marquee_tick(self):
            self._scroll_pos += 1

            def shift(text, limit=25):
                if len(text) <= limit:
                    return text
                p = text + "     "
                i = self._scroll_pos % len(p)
                return (p[i:] + p[:i])[:limit]

            self.title_label.set_text(shift(self._full_title))
            self.artist_label.set_text(shift(self._full_artist))
            return True

        def _load_art_async(self, url):
            def _done(s, r):
                try:
                    pix = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                        s.read_finish(r), 120, 120, True, None
                    )
                    self.plugin.schedule_in_gtk_thread(
                        lambda: self.art_image.set_from_pixbuf(pix)
                    )
                except Exception:
                    pass

            try:
                Gio.File.new_for_uri(url).read_async(GLib.PRIORITY_DEFAULT, None, _done)
            except Exception:
                pass

    class MediaPlugin(BasePlugin):
        def on_enable(self):
            self.active_rows, self.local_dbus, self.main_button, self._added = (
                {},
                None,
                None,
                False,
            )
            self.popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.popover_box.add_css_class("player-popover-content")
            self.run_in_async_task(self._init_dbus())
            self.plugins["css_generator"].install_css("main.css")

        async def _init_dbus(self):
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
            self.local_dbus = DbusHelpers(bus)
            while True:
                players = await self.local_dbus.get_active_mpris_players()
                valid = set()
                for p in players:
                    m = await self.local_dbus.get_media_metadata(p)
                    if m and (m.get("title") or m.get("status")):
                        valid.add(p)
                        self.schedule_in_gtk_thread(self._sync_row, p, m)
                for p in list(self.active_rows.keys()):
                    if p not in valid:
                        self.schedule_in_gtk_thread(self._remove_row, p)
                self.schedule_in_gtk_thread(self._sync_panel)
                await self.asyncio.sleep(2)

        def _sync_row(self, p, m):
            if p not in self.active_rows:
                row = PlayerRow(p, self)
                self.active_rows[p] = row
                self.popover_box.append(row)
            self.active_rows[p].update_ui(m)

        def _remove_row(self, p):
            row = self.active_rows.pop(p, None)
            if row:
                if row._scroll_timer:
                    GLib.source_remove(row._scroll_timer)
                self.popover_box.remove(row)
                gc.collect()

        def _sync_panel(self):
            container = self._panel_instance.top_panel_box_center

            if self.active_rows and not self._added:
                self.main_button = Gtk.Button()
                self.add_cursor_effect(self.main_button)
                self.main_button.add_css_class("player-trigger")
                self.main_button.set_icon_name("multimedia-audio-player-symbolic")

                pop, scr, _ = self.create_popover(
                    parent_widget=self.main_button,
                    css_class="player-popover",
                    use_scrolled=True,
                    max_height=500,
                )

                scr.set_child(self.popover_box)
                self.main_button.connect("clicked", lambda _: pop.popup())
                container.append(self.main_button)
                self._added = True
            elif not self.active_rows and self._added:
                container.remove(self.main_button)
                self.main_button, self._added = None, False
                gc.collect()

        def on_disable(self):
            if self.main_button and self._added:
                self._sync_panel()
            for r in self.active_rows.values():
                if r._scroll_timer:
                    GLib.source_remove(r._scroll_timer)
            self.active_rows.clear()
            gc.collect()

    return MediaPlugin
