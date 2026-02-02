from gi.repository import Gtk, Adw, WebKit, Gdk
import subprocess


class FlathubBrowser(Gtk.ApplicationWindow):
    """Dedicated WebKit window for Flathub with SPA-aware installation detection."""

    def __init__(self, plugin, **kwargs):
        super().__init__(title="Flathub Store", **kwargs)
        self.plugin = plugin
        self.set_default_size(1100, 800)

        self.main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_vbox)

        self.header_bar = Adw.HeaderBar()
        self.main_vbox.append(self.header_bar)

        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        nav_box.add_css_class("linked")

        self.btn_back = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.btn_back.connect("clicked", lambda *_: self.webview.go_back())
        self.btn_forward = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self.btn_forward.connect("clicked", lambda *_: self.webview.go_forward())
        self.btn_home = Gtk.Button.new_from_icon_name("go-home-symbolic")
        self.btn_home.connect(
            "clicked", lambda *_: self.webview.load_uri("https://flathub.org")
        )

        nav_box.append(self.btn_back)
        nav_box.append(self.btn_forward)
        nav_box.append(self.btn_home)
        self.header_bar.pack_start(nav_box)

        self.btn_reload = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.btn_reload.connect("clicked", lambda *_: self.webview.reload())
        self.header_bar.pack_end(self.btn_reload)

        for btn in [self.btn_back, self.btn_forward, self.btn_home, self.btn_reload]:
            self._add_cursor_hover(btn, "pointer")

        self.webview = WebKit.WebView()

        # 1. Intercept actual downloads (.flatpakref)
        self.webview.connect("decide-policy", self._on_decide_policy)

        # 2. Trigger detection on every URL change (SPA Navigation)
        self.webview.connect("notify::uri", self._on_uri_changed)

        # 3. Initial load check
        self.webview.connect("load-changed", self._on_load_changed)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(self.webview)
        self.main_vbox.append(scrolled)

        self.webview.load_uri("https://flathub.org")

    def _add_cursor_hover(self, widget, cursor_name):
        controller = Gtk.EventControllerMotion.new()

        def on_enter(controller, x, y):
            widget.set_cursor(Gdk.Cursor.new_from_name(cursor_name, None))

        def on_leave(controller):
            widget.set_cursor(None)

        controller.connect("enter", on_enter)
        controller.connect("leave", on_leave)
        widget.add_controller(controller)

    def _is_flatpak_installed(self, app_id):
        """Checks installation state using flatpak info command."""
        try:
            subprocess.check_call(
                ["flatpak", "info", app_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, Exception):
            return False

    def _on_uri_changed(self, webview, pspec):
        """Fires whenever the URL changes, including SPA pushState."""
        uri = webview.get_uri()
        if uri and "/apps/" in uri:
            app_id = uri.split("/apps/")[-1].split("/")[0]
            if self._is_flatpak_installed(app_id):
                # FIXME: sometimes disabling all buttons
                # self._mark_as_installed_in_dom()
                pass

    def _on_load_changed(self, webview, load_event):
        if load_event == WebKit.LoadEvent.FINISHED:
            self._on_uri_changed(webview, None)

    def _mark_as_installed_in_dom(self):
        """Aggressive JS to kill the button even as Flathub rerenders."""
        js_code = """
        (function() {
            function killButton() {
                const buttons = document.querySelectorAll('a[role="button"]');
                buttons.forEach(btn => {
                    if (btn.innerText.includes('Instalar') || btn.href.includes('/install')) {
                        btn.innerText = 'Installed';
                        btn.style.opacity = '0.5';
                        btn.style.pointerEvents = 'none';
                        btn.style.backgroundColor = 'var(--color-bg-deep, #2e3436)';
                        btn.removeAttribute('href');
                        btn.classList.remove('hover:opacity-75', 'active:opacity-50');
                    }
                });
            }

            // Run frequently for the first few seconds of navigation to catch SPA render
            let attempts = 0;
            const interval = setInterval(() => {
                killButton();
                if (++attempts > 20) clearInterval(interval);
            }, 100);

            // MutationObserver for background changes
            const observer = new MutationObserver(killButton);
            observer.observe(document.body, { childList: true, subtree: true });
        })();
        """
        self.webview.evaluate_javascript(js_code, -1, None, None, None, None, None)

    def _on_decide_policy(self, webview, decision, decision_type):
        if decision_type == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            nav_action = decision.get_navigation_action()
            uri = nav_action.get_request().get_uri()

            if uri.endswith(".flatpakref") or "dl.flathub.org" in uri:
                app_id = (
                    uri.split("/")[-1]
                    .replace(".flatpakref", "")
                    .replace("flatpak+", "")
                )
                hit_data = {
                    "id": app_id,
                    "name": app_id.split(".")[-1].capitalize(),
                    "remote": True,
                }

                try:
                    self.plugin.menu_handler.pkg_helper.install_flatpak(hit_data)

                    def center_later():
                        found = self.plugin.view_id_found(title="Flatpak Installer")
                        if found:
                            self.plugin.wf_helper.center_view_on_output(
                                found[0], 800, 710
                            )

                    self.plugin.glib.timeout_add(150, center_later)
                except Exception as e:
                    self.plugin.logger.error(f"Install trigger failed: {e}")

                decision.ignore()
                return True
        return False
