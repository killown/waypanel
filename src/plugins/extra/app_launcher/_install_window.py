import os
import threading
import re


class FlatpakInstallWindow:
    """A professional GTK installer with a dynamic label toggle for install scope."""

    def __init__(self, app_launcher, hit_data: dict, app_id: str):
        self.app_launcher = app_launcher
        self.app_id = app_id
        self.hit = hit_data
        self.gtk = app_launcher.gtk
        self.glib = app_launcher.glib
        self.gio = app_launcher.gio

        self.window = self.gtk.Window()
        self.window.set_title("Flatpak Installer")
        self.window.set_default_size(720, 620)
        self.window.set_modal(True)
        self.window.set_name("waypanel-installer")

        # --- HEADER BAR ---
        self.header_bar = self.gtk.HeaderBar()
        self.window.set_titlebar(self.header_bar)

        self.title_label = self.gtk.Label.new("Ready to Install")
        self.title_label.add_css_class("title-4")
        self.header_bar.set_title_widget(self.title_label)

        self.close_btn = self.gtk.Button(label="Cancel")
        self.close_btn.connect("clicked", lambda _: self.window.destroy())
        self.header_bar.pack_start(self.close_btn)

        # Right actions container
        self.actions_end = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 12)
        self.header_bar.pack_end(self.actions_end)

        # Dynamic Scope Toggle
        self.toggle_box = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 8)
        self.toggle_box.set_valign(self.gtk.Align.CENTER)

        # The dynamic label
        self.scope_label = self.gtk.Label.new("Local")
        self.scope_label.add_css_class("dim-label")

        self.scope_switch = self.gtk.Switch()
        self.scope_switch.set_active(False)
        self.scope_switch.set_valign(self.gtk.Align.CENTER)
        # Update label when toggled
        self.scope_switch.connect("state-set", self._on_scope_toggled)

        self.toggle_box.append(self.scope_label)
        self.toggle_box.append(self.scope_switch)
        self.actions_end.append(self.toggle_box)

        # Main Action Button
        self.install_btn = self.gtk.Button(label="Install")
        self.install_btn.add_css_class("suggested-action")
        self.install_btn.connect("clicked", self._on_install_clicked)
        self.actions_end.append(self.install_btn)

        # --- CONTENT ---
        scrolled = self.gtk.ScrolledWindow()
        scrolled.set_policy(self.gtk.PolicyType.NEVER, self.gtk.PolicyType.AUTOMATIC)
        self.window.set_child(scrolled)

        main_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 24)
        for m in ["start", "end", "top", "bottom"]:
            getattr(main_vbox, f"set_margin_{m}")(32)
        scrolled.set_child(main_vbox)

        # Identity
        identity_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 24)
        identity_hbox.set_halign(self.gtk.Align.CENTER)
        main_vbox.append(identity_hbox)

        icon_path = hit_data.get("_local_icon")
        app_icon = (
            self.gtk.Image.new_from_file(icon_path)
            if icon_path and os.path.exists(icon_path)
            else self.gtk.Image.new_from_icon_name("system-software-install")
        )
        app_icon.set_pixel_size(96)
        identity_hbox.append(app_icon)

        title_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 4)
        title_vbox.set_valign(self.gtk.Align.CENTER)
        identity_hbox.append(title_vbox)

        name_label = self.gtk.Label.new(hit_data.get("name", "Application"))
        name_label.add_css_class("title-1")
        name_label.set_halign(self.gtk.Align.START)
        title_vbox.append(name_label)

        id_label = self.gtk.Label.new(app_id)
        id_label.add_css_class("dim-label")
        id_label.set_halign(self.gtk.Align.START)
        title_vbox.append(id_label)

        # Metadata Grid
        self.grid = self.gtk.Grid()
        self.grid.set_column_spacing(40)
        self.grid.set_row_spacing(12)
        self.grid.set_halign(self.gtk.Align.CENTER)
        main_vbox.append(self.grid)

        # Description Card
        desc_frame = self.gtk.Frame()
        desc_frame.add_css_class("card")
        main_vbox.append(desc_frame)

        desc_container = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 12)
        for m in ["start", "end", "top", "bottom"]:
            getattr(desc_container, f"set_margin_{m}")(30)
        desc_container.set_halign(self.gtk.Align.CENTER)
        desc_container.set_valign(self.gtk.Align.CENTER)
        desc_frame.set_child(desc_container)

        self.desc_label = self.gtk.Label.new("Fetching details from Flathub...")
        self.desc_label.set_wrap(True)
        self.desc_label.set_justify(self.gtk.Justification.CENTER)
        self.desc_label.set_max_width_chars(70)
        self.desc_label.add_css_class("body")
        desc_container.append(self.desc_label)

        # Progress Area
        self.install_view = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 15)
        self.install_view.set_visible(False)
        main_vbox.append(self.install_view)

        self.progress_bar = self.gtk.ProgressBar()
        self.install_view.append(self.progress_bar)

        log_scroll = self.gtk.ScrolledWindow()
        log_scroll.set_min_content_height(180)
        log_scroll.add_css_class("card")
        self.console = self.gtk.TextView()
        self.console.set_editable(False)
        self.console.set_monospace(True)
        for m in ["left", "right", "top", "bottom"]:
            getattr(self.console, f"set_{m}_margin")(15)
        self.console.add_css_class("code")
        log_scroll.set_child(self.console)
        self.install_view.append(log_scroll)

        self.window.present()
        threading.Thread(target=self._load_async_data, daemon=True).start()

    def _on_scope_toggled(self, switch, state):
        """Updates the label text based on switch state."""
        self.scope_label.set_text("System" if state else "Local")
        return False

    def _add_row(self, label, value, row):
        l = self.gtk.Label.new(f"<b>{label}</b>")
        l.set_use_markup(True)
        l.add_css_class("dim-label")
        l.set_halign(self.gtk.Align.END)
        v = self.gtk.Label.new(str(value or "N/A"))
        v.set_halign(self.gtk.Align.START)
        self.grid.attach(l, 0, row, 1, 1)
        self.grid.attach(v, 1, row, 1, 1)

    def _load_async_data(self):
        import requests

        url = f"https://flathub.org/api/v2/appstream/{self.app_id.replace('_', '.')}"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                self.glib.idle_add(self._update_ui, r.json())
        except:
            self.glib.idle_add(self.desc_label.set_text, "Failed to load info.")

    def _update_ui(self, data):
        self._add_row("Summary", data.get("summary"), 0)
        self._add_row(
            "Developer", data.get("developer_name") or data.get("publisher"), 1
        )
        self._add_row("License", data.get("project_license"), 2)
        desc = re.sub("<[^<]+?>", "", data.get("description", "")).strip()
        self.desc_label.set_text(desc)
        return False

    def _on_install_clicked(self, _):
        scope = "--system" if self.scope_switch.get_active() else "--user"
        self.start_installation(scope)

    def start_installation(self, scope):
        self.install_btn.set_visible(False)
        self.toggle_box.set_visible(False)
        self.install_view.set_visible(True)
        self.title_label.set_text("Installing...")

        cmd = [
            "flatpak",
            "install",
            scope,
            "--noninteractive",
            "-y",
            "flathub",
            self.app_id,
        ]
        if os.path.exists("/.flatpak-info"):
            cmd = ["flatpak-spawn", "--host"] + cmd

        try:
            self.process = self.gio.Subprocess.new(
                cmd,
                self.gio.SubprocessFlags.STDOUT_PIPE
                | self.gio.SubprocessFlags.STDERR_PIPE,
            )
            self.glib.idle_add(self._pulse)
            self._stream_reader(self.process.get_stdout_pipe())
            self._stream_reader(self.process.get_stderr_pipe())
        except Exception as e:
            self.append_log(f"Error: {e}")

    def _pulse(self):
        if self.process.get_if_exited():
            success = self.process.get_exit_status() == 0
            self.progress_bar.set_fraction(1.0 if success else 0.0)
            self.title_label.set_text(
                "Installation Finished" if success else "Installation Failed"
            )

            if success:
                self.close_btn.set_label("Done")
                launch = self.gtk.Button(label="Launch Application")
                launch.add_css_class("suggested-action")
                launch.connect("clicked", self._launch)
                self.actions_end.append(launch)
            return False
        self.progress_bar.pulse()
        return True

    def _launch(self, _):
        import subprocess

        cmd = ["flatpak", "run", self.app_id]
        if os.path.exists("/.flatpak-info"):
            cmd = ["flatpak-spawn", "--host"] + cmd
        subprocess.Popen(cmd)
        self.window.destroy()

    def _stream_reader(self, stream):
        if not stream:
            return

        def on_read_ready(s, res):
            try:
                data = s.read_bytes_finish(res)
                if data and data.get_size() > 0:
                    text = data.get_data().decode("utf-8")
                    self.glib.idle_add(self.append_log, text)
                    s.read_bytes_async(4096, 0, None, on_read_ready)
            except:
                pass

        stream.read_bytes_async(4096, 0, None, on_read_ready)

    def append_log(self, text):
        buf = self.console.get_buffer()
        buf.insert_at_cursor(text)
        self.console.scroll_to_mark(buf.get_insert(), 0.0, True, 0.5, 1.0)
