import os
import threading
import re
import requests
from gi.repository import GdkPixbuf, Gdk


class FlatpakInstallWindow:
    """Professional GTK installer with async loading, spinner, and post-install actions."""

    def __init__(self, app_launcher, hit_data: dict, app_id: str):
        self.app_launcher = app_launcher
        self.app_id = app_id
        self.hit = hit_data
        self.gtk = app_launcher.gtk
        self.glib = app_launcher.glib
        self.gio = app_launcher.gio

        self.window = self.gtk.Window()
        self.window.set_title("Flatpak Installer")
        self.window.set_default_size(800, 750)
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

        self.actions_end = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 12)
        self.header_bar.pack_end(self.actions_end)

        # Installation Spinner (Hidden by default)
        self.spinner = self.gtk.Spinner()
        self.spinner.set_visible(False)
        self.actions_end.append(self.spinner)

        self.scope_label = self.gtk.Label.new("Local")
        self.scope_label.add_css_class("dim-label")

        self.scope_switch = self.gtk.Switch()
        self.scope_switch.set_active(False)
        self.scope_switch.connect("state-set", self._on_scope_toggled)

        self.toggle_box = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 8)
        self.toggle_box.append(self.scope_label)
        self.toggle_box.append(self.scope_switch)
        self.actions_end.append(self.toggle_box)

        self.install_btn = self.gtk.Button(label="Install")
        self.install_btn.add_css_class("suggested-action")
        self.install_btn.connect("clicked", self._on_install_clicked)
        self.actions_end.append(self.install_btn)

        # --- CONTENT ---
        scrolled = self.gtk.ScrolledWindow()
        self.window.set_child(scrolled)

        self.main_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 24)
        for m in ["start", "end", "top", "bottom"]:
            getattr(self.main_vbox, f"set_margin_{m}")(32)
        scrolled.set_child(self.main_vbox)

        # Identity Header
        identity_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 24)
        identity_hbox.set_halign(self.gtk.Align.CENTER)
        self.main_vbox.append(identity_hbox)

        icon_path = hit_data.get("_local_icon")
        self.app_icon = (
            self.gtk.Image.new_from_file(icon_path)
            if icon_path and os.path.exists(icon_path)
            else self.gtk.Image.new_from_icon_name("system-software-install")
        )
        self.app_icon.set_pixel_size(96)
        identity_hbox.append(self.app_icon)

        title_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 4)
        title_vbox.set_valign(self.gtk.Align.CENTER)
        identity_hbox.append(title_vbox)

        self.name_label = self.gtk.Label.new(hit_data.get("name", "Application"))
        self.name_label.add_css_class("title-1")
        self.name_label.set_halign(self.gtk.Align.START)
        title_vbox.append(self.name_label)

        self.version_label = self.gtk.Label.new("Version: ...")
        self.version_label.add_css_class("dim-label")
        self.version_label.set_halign(self.gtk.Align.START)
        title_vbox.append(self.version_label)

        # SCREENSHOTS CAROUSEL
        self.screenshot_scrolled = self.gtk.ScrolledWindow()
        self.screenshot_scrolled.set_policy(
            self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.NEVER
        )
        self.screenshot_scrolled.set_min_content_height(420)
        self.screenshot_scrolled.add_css_class("card")
        self.screenshot_scrolled.set_visible(False)
        self.main_vbox.append(self.screenshot_scrolled)

        self.screenshot_box = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 12)
        for m in ["start", "end", "top", "bottom"]:
            getattr(self.screenshot_box, f"set_margin_{m}")(12)
        self.screenshot_scrolled.set_child(self.screenshot_box)

        # Metadata Grid
        self.grid = self.gtk.Grid()
        self.grid.set_column_spacing(40)
        self.grid.set_row_spacing(12)
        self.grid.set_halign(self.gtk.Align.CENTER)
        self.main_vbox.append(self.grid)

        # Description
        desc_frame = self.gtk.Frame()
        desc_frame.add_css_class("card")
        self.main_vbox.append(desc_frame)

        self.desc_label = self.gtk.Label.new("Fetching details from Flathub...")
        self.desc_label.set_wrap(True)
        self.desc_label.set_justify(self.gtk.Justification.CENTER)
        self.desc_label.set_max_width_chars(70)
        for m in ["start", "end", "top", "bottom"]:
            getattr(self.desc_label, f"set_margin_{m}")(30)
        desc_frame.set_child(self.desc_label)

        # Progress View
        self.install_view = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 15)
        self.install_view.set_visible(False)
        self.main_vbox.append(self.install_view)

        self.progress_bar = self.gtk.ProgressBar()
        self.install_view.append(self.progress_bar)

        self.window.present()
        threading.Thread(target=self._load_async_data, daemon=True).start()

    def _on_scope_toggled(self, switch, state):
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
        formatted_id = self.app_id.replace("_", ".")
        url = f"https://flathub.org/api/v2/appstream/{formatted_id}"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                self.glib.idle_add(self._update_ui_text, data)
                self._load_screenshots(data.get("screenshots", []))
        except:
            self.glib.idle_add(self.desc_label.set_text, "Failed to load info.")

    def _update_ui_text(self, data):
        releases = data.get("releases", [])
        version = releases[0].get("version", "Unknown") if releases else "Unknown"
        self.version_label.set_text(f"Version: {version}")
        self._add_row("Developer", data.get("developer_name") or "Mozilla", 0)
        self._add_row("License", data.get("project_license"), 1)
        desc = re.sub("<[^<]+?>", "", data.get("description", "")).strip()
        self.desc_label.set_text(desc)
        return False

    def _load_screenshots(self, screenshots):
        if not screenshots:
            return
        for s in screenshots[:4]:
            img_url = s["sizes"][0]["src"]
            threading.Thread(
                target=self._download_and_render_screenshot,
                args=(img_url,),
                daemon=True,
            ).start()

    def _download_and_render_screenshot(self, url):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(r.content)
                loader.close()
                pixbuf = loader.get_pixbuf()
                target_h = 400
                aspect = pixbuf.get_width() / pixbuf.get_height()
                target_w = int(target_h * aspect)
                scaled = pixbuf.scale_simple(
                    target_w, target_h, GdkPixbuf.InterpType.BILINEAR
                )
                self.glib.idle_add(self._append_screenshot, scaled)
        except:
            pass

    def _append_screenshot(self, pixbuf):
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        img = self.gtk.Picture.new_for_paintable(texture)
        img.set_content_fit(self.gtk.ContentFit.CONTAIN)
        img.set_can_shrink(True)
        img.set_hexpand(True)
        img.set_vexpand(True)
        img.set_size_request(pixbuf.get_width(), 400)
        img.add_css_class("card")
        self.screenshot_box.append(img)
        self.screenshot_scrolled.set_visible(True)
        return False

    def _on_install_clicked(self, _):
        scope = "--system" if self.scope_switch.get_active() else "--user"
        self.start_installation(scope)

    def start_installation(self, scope):
        self.install_btn.set_visible(False)
        self.toggle_box.set_visible(False)
        self.install_view.set_visible(True)
        self.title_label.set_text("Installing...")

        # Start spinner
        self.spinner.set_visible(True)
        self.spinner.start()

        # Build the command for the host system
        cmd = [
            "flatpak",
            "install",
            scope,
            "--noninteractive",
            "-y",
            "flathub",
            self.app_id,
        ]

        # Use flatpak-spawn --host to escape the panel's sandbox
        if os.path.exists("/.flatpak-info"):
            cmd = ["flatpak-spawn", "--host"] + cmd

        try:
            self.process = self.gio.Subprocess.new(
                cmd,
                self.gio.SubprocessFlags.STDOUT_PIPE
                | self.gio.SubprocessFlags.STDERR_PIPE,
            )
            self.glib.idle_add(self._pulse)
        except Exception as e:
            self.spinner.stop()
            self.spinner.set_visible(False)
            self.title_label.set_text(f"Error: {e}")

    def _pulse(self):
        if self.process.get_if_exited():
            success = self.process.get_exit_status() == 0

            # Stop and hide spinner
            self.spinner.stop()
            self.spinner.set_visible(False)

            self.progress_bar.set_fraction(1.0 if success else 0.0)
            self.title_label.set_text(
                "Installation Finished" if success else "Installation Failed"
            )

            if success:
                self.close_btn.set_label("Done")
                launch_btn = self.gtk.Button(label="Launch Application")
                launch_btn.add_css_class("suggested-action")
                launch_btn.connect("clicked", self._launch_app)
                self.actions_end.append(launch_btn)
            return False

        self.progress_bar.pulse()
        return True

    def _launch_app(self, _):
        """Triggers application launch via the plugin's CommandRunner to escape sandbox."""
        cmd = f"flatpak run {self.app_id}"
        if hasattr(self.app_launcher, "cmd"):
            self.app_launcher.cmd.run(cmd)
            self.window.destroy()
