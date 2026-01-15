from .menu import AppMenuHandler
import os


class RemoteApps:
    def __init__(self, app_launcher):
        self.menu_handler = AppMenuHandler(app_launcher)
        self.app_launcher = app_launcher
        self.max_hits = 30

    def _trigger_remote_search(self, query: str) -> bool:
        """Spawns a background thread to fetch Flathub results."""
        import threading

        thread = threading.Thread(
            target=self._fetch_remote_results, args=(query,), daemon=True
        )
        thread.start()
        self.app_launcher.search_timeout_id = None
        return False

    def _fetch_remote_results(self, query: str):
        """Fetches hits and downloads icons in background."""
        from gi.repository import GLib
        import requests
        import hashlib
        from pathlib import Path

        hits = self.menu_handler.pkg_helper.search_flathub(query)
        if not hits:
            return

        icon_cache = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "waypanel_icons"
        icon_cache.mkdir(parents=True, exist_ok=True)

        for hit in hits[:6]:
            url = hit.get("icon")
            if url:
                try:
                    path = icon_cache / f"{hashlib.md5(url.encode()).hexdigest()}.png"
                    if not path.exists():
                        r = requests.get(url, timeout=5)
                        path.write_bytes(r.content)
                    hit["_local_icon"] = str(path)
                except Exception:
                    hit["_local_icon"] = None

        GLib.idle_add(self._render_remote_results, hits)

    def _render_remote_results(self, hits: list):
        """Deduplicates results and renders them to the UI."""
        query = self.app_launcher.searchbar.get_text().strip().lower()
        if not query:
            return False

        local_names = {
            a.get_name().lower()
            for a in self.app_launcher.all_apps.values()
            if query in a.get_name().lower()
            or query in " ".join(a.get_keywords()).lower()
        }

        count = 0
        for hit in hits:
            if count >= self.max_hits:
                break
            if hit.get("name", "").lower() in local_names:
                continue
            self._add_remote_app_to_grid(hit)
            count += 1
        return False

    def _add_remote_app_to_grid(self, hit: dict):
        """Adds a Flathub item with emblem and downloaded icon."""
        name = hit.get("name", "Unknown")
        app_id = hit.get("app_id")
        path = hit.get("_local_icon")

        vbox = self.app_launcher.gtk.Box.new(
            self.app_launcher.gtk.Orientation.VERTICAL, 5
        )
        if path and os.path.exists(path):
            img = self.app_launcher.gtk.Image.new_from_file(path)
        else:
            icon_name = "system-software-install"
            for c in [app_id, name.lower(), name.lower().replace(" ", "-")]:
                if self.app_launcher.gtk_helper.icon_exist(c):
                    icon_name = c
                    break
            img = self.app_launcher.gtk.Image.new_from_icon_name(icon_name)

        img.set_pixel_size(64)
        vbox.append(img)

        label = self.app_launcher.gtk.Label.new(name)
        label.set_max_width_chars(12)
        label.set_ellipsize(self.app_launcher.pango.EllipsizeMode.END)
        vbox.append(label)

        hint = self.app_launcher.gtk.Label.new("FLATHUB")
        hint.add_css_class("flatpak-emblem")
        hint.set_halign(self.app_launcher.gtk.Align.CENTER)
        vbox.append(hint)

        button = self.app_launcher.gtk.Button()
        button.set_child(vbox)
        button.set_has_frame(False)
        button.add_css_class("app-item-remote")
        button.MYTEXT = (
            name,
            f"remote:{app_id}",
            " ".join(hit.get("keywords") or []),
        )

        button.connect("clicked", lambda _: self.app_launcher.install_remote_app(hit))

        self.app_launcher.flowbox.append(button)
        self.app_launcher.remote_widgets.append(button)

