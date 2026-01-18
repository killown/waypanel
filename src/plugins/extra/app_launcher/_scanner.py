import os
from gi.repository import GLib, Gio
from typing import Dict, Any, List


class AppScanner:
    """
    Handles the discovery and parsing of Linux desktop application entries.

    Attributes:
        search_paths (List[str]): Directories to scan for .desktop files.
    """

    def __init__(self):
        """Initializes the scanner with standard application search paths."""
        self.search_paths: List[str] = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications/"),
            "/run/host/usr/share/applications",
        ]

        if os.path.exists("/.flatpak-info"):
            host_flatpak_user = (
                "/run/host/user-share/flatpak/exports/share/applications"
            )
            host_flatpak_sys = "/run/host/share/flatpak/exports/share/applications"

            if os.path.isdir(host_flatpak_user):
                self.search_paths.append(host_flatpak_user)
            if os.path.isdir(host_flatpak_sys):
                self.search_paths.append(host_flatpak_sys)

    def scan(self) -> Dict[str, Any]:
        """
        Scans search paths for valid, non-hidden desktop applications.

        Returns:
            Dict[str, Any]: A mapping of desktop IDs to application metadata objects.
        """
        all_apps = {}

        for app_dir in self.search_paths:
            if not os.path.isdir(app_dir):
                continue

            try:
                for file_name in os.listdir(app_dir):
                    if not file_name.endswith(".desktop") or file_name in all_apps:
                        continue

                    file_path = os.path.join(app_dir, file_name)

                    if os.path.islink(file_path):
                        target = os.readlink(file_path)
                        if not os.path.isabs(target):
                            target = os.path.join(app_dir, target)

                        if target.startswith("/home/") and not target.startswith(
                            "/run/host/"
                        ):
                            target = os.path.join("/run/host", target.lstrip("/"))

                        file_path = target

                    if not os.path.exists(file_path):
                        continue

                    keyfile = GLib.KeyFile.new()
                    try:
                        if not keyfile.load_from_file(
                            file_path, GLib.KeyFileFlags.NONE
                        ):
                            continue
                    except GLib.Error:
                        continue

                    if not keyfile.has_group("Desktop Entry") or self._should_skip(
                        keyfile
                    ):
                        continue

                    name = keyfile.get_locale_string("Desktop Entry", "Name")
                    if not name:
                        continue

                    all_apps[file_name] = self._create_app_object(
                        file_name,
                        name,
                        self._get_string(keyfile, "Icon"),
                        self._get_string(keyfile, "Exec"),
                        self._get_list(keyfile, "Keywords"),
                    )
            except PermissionError:
                continue

        return all_apps

    def _should_skip(self, keyfile: GLib.KeyFile) -> bool:
        """Checks if the application entry has NoDisplay or Hidden flags set."""
        for key in ["NoDisplay", "Hidden"]:
            try:
                if keyfile.get_boolean("Desktop Entry", key):
                    return True
            except GLib.Error:
                pass
        return False

    def _get_string(self, keyfile: GLib.KeyFile, key: str) -> str | None:
        """Safely retrieves a string value from the keyfile."""
        try:
            return keyfile.get_string("Desktop Entry", key)
        except GLib.Error:
            return None

    def _get_list(self, keyfile: GLib.KeyFile, key: str) -> List[str]:
        """Safely retrieves a list of strings from the keyfile."""
        try:
            return keyfile.get_string_list("Desktop Entry", key)
        except GLib.Error:
            return []

    def _create_app_object(
        self,
        app_id: str,
        name: str,
        icon: str | None,
        exec_cmd: str | None,
        keywords: List[str],
    ) -> Any:
        """
        Creates a metadata object compatible with the plugin's interaction logic.
        """

        class AppEntry:
            def get_name(self):
                return name

            def get_id(self):
                return app_id

            def get_keywords(self):
                return keywords

            def get_exec(self):
                return exec_cmd

            def get_icon(self):
                return Gio.ThemedIcon.new(icon) if icon else None

        return AppEntry()
