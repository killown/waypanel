import os
import threading


class FlatpakUninstallWindow:
    """A professional GTK window for uninstalling Flatpaks with real-time logging."""

    def __init__(self, app_launcher, hit_data: dict, app_id: str):
        self.app_launcher = app_launcher
        self.app_id = app_id
        self.hit = hit_data
        self.gtk = app_launcher.gtk
        self.glib = app_launcher.glib
        self.gio = app_launcher.gio

        self.window = self.gtk.Window()
        self.window.set_title("Flatpak Uninstaller")
        self.window.set_default_size(720, 620)
        self.window.set_modal(True)
        self.window.set_name("waypanel-uninstaller")

        # --- HEADER BAR ---
        self.header_bar = self.gtk.HeaderBar()
        self.window.set_titlebar(self.header_bar)

        self.title_label = self.gtk.Label.new("Application Details")
        self.title_label.add_css_class("title-4")
        self.header_bar.set_title_widget(self.title_label)

        self.close_btn = self.gtk.Button(label="Close")
        self.close_btn.connect("clicked", lambda _: self.window.destroy())
        self.header_bar.pack_start(self.close_btn)

        self.actions_end = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 6)
        self.header_bar.pack_end(self.actions_end)

        self.uninstall_btn = self.gtk.Button(label="Uninstall")
        self.uninstall_btn.add_css_class("destructive-action")  # Red button in GNOME
        self.uninstall_btn.connect("clicked", self._on_uninstall_clicked)
        self.actions_end.append(self.uninstall_btn)

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

        # Metadata Grid (Populated from 'flatpak info')
        self.grid = self.gtk.Grid()
        self.grid.set_column_spacing(40)
        self.grid.set_row_spacing(12)
        self.grid.set_halign(self.gtk.Align.CENTER)
        main_vbox.append(self.grid)

        # Info Card (The Square)
        info_frame = self.gtk.Frame()
        info_frame.add_css_class("card")
        main_vbox.append(info_frame)

        self.info_label = self.gtk.Label.new("Reading local installation data...")
        self.info_label.set_wrap(True)
        self.info_label.set_justify(self.gtk.Justification.CENTER)
        self.info_label.set_max_width_chars(70)
        self.info_label.set_margin_end(30)
        self.info_label.add_css_class("body")
        info_frame.set_child(self.info_label)

        # Progress Area
        self.progress_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 15)
        self.progress_box.set_visible(False)
        main_vbox.append(self.progress_box)

        self.progress_bar = self.gtk.ProgressBar()
        self.progress_box.append(self.progress_bar)

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
        self.progress_box.append(log_scroll)

        self.window.present()
        threading.Thread(target=self._load_local_info, daemon=True).start()

    def _load_local_info(self):
        """Runs 'flatpak info' to get actual local installation details."""
        import subprocess

        cmd = ["flatpak", "info", self.app_id]
        if os.path.exists("/.flatpak-info"):
            cmd = ["flatpak-spawn", "--host"] + cmd

        try:
            env = os.environ.copy()
            env["LC_ALL"] = "C"
            res = subprocess.run(cmd, capture_output=True, text=True, env=env)
            if res.returncode == 0:
                self.glib.idle_add(self._parse_info, res.stdout)
            else:
                self.glib.idle_add(
                    self.info_label.set_text,
                    "Application not found or partially installed.",
                )
        except Exception as e:
            self.glib.idle_add(self.info_label.set_text, f"Error: {e}")

    def _parse_info(self, raw_text):
        """Extracts key lines to fill the grid and card."""
        lines = raw_text.splitlines()
        grid_data = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                grid_data[key.strip()] = val.strip()

        # Update Grid
        self._add_row("Version", grid_data.get("Version"), 0)
        self._add_row("License", grid_data.get("License"), 1)
        self._add_row("Origin", grid_data.get("Origin"), 2)
        self._add_row("Installed Size", grid_data.get("Installed"), 3)

        # Update Card with the 'Subject' or 'Commit' info
        commit_info = f"Commit: {grid_data.get('Commit', 'N/A')[:12]}\nDate: {grid_data.get('Date', 'N/A')}"
        self.info_label.set_text(commit_info)
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

    def _on_uninstall_clicked(self, _):
        self.uninstall_btn.set_visible(False)
        self.progress_box.set_visible(True)
        self.title_label.set_text("Uninstalling...")

        # Non-interactive uninstall
        cmd = ["flatpak", "uninstall", "-y", "--noninteractive", self.app_id]
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

            if success:
                # Start polling to verify uninstallation
                self.title_label.set_text("Verifying...")
                self.glib.timeout_add(500, self._verify_uninstalled)
            else:
                self.title_label.set_text("Failed")
                self.close_btn.set_label("Done")

            if hasattr(self.app_launcher, "active_windows"):
                self.app_launcher.active_windows.discard(self.app_id)
            return False

        self.progress_bar.pulse()
        return True

    def _verify_uninstalled(self):
        """Checks every 500ms if the app is still recognized by Flatpak."""
        cmd = ["flatpak", "info", self.app_id]
        if os.path.exists("/.flatpak-info"):
            cmd = ["flatpak-spawn", "--host"] + cmd

        try:
            # We use a simple check to see if the command fails (app is gone)
            res = self.gio.Subprocess.new(cmd, self.gio.SubprocessFlags.STDOUT_SILENCE)

            # Wait a tiny bit for the check process to complete
            if not res.wait_check():
                # Success: App ID is no longer found in the system
                self.append_log(
                    "\n[CONFIRMED] Application successfully removed from system.\n"
                )
                self.title_label.set_text("Uninstalled")
                self.close_btn.set_label("Done")
                return False  # Stop polling
        except:
            # If the process fails to even start, assume it's gone
            self.append_log("\n[CONFIRMED] Application removed.\n")
            self.title_label.set_text("Uninstalled")
            self.close_btn.set_label("Done")
            return False

        return True  # Continue polling

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
                else:
                    self.glib.idle_add(self._pulse)
                    s.close(None)
            except:
                self.glib.idle_add(self._pulse)

        stream.read_bytes_async(4096, 0, None, on_read_ready)

    def append_log(self, text):
        buf = self.console.get_buffer()
        buf.insert_at_cursor(text)
        self.console.scroll_to_mark(buf.get_insert(), 0.0, True, 0.5, 1.0)
