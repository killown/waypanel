import gi
import configparser
import rapidfuzz
import subprocess
import os
from rapidfuzz.fuzz import token_set_ratio
from src.shared.data_helpers import DataHelpers
from src.shared.config_handler import ConfigHandler
from src.shared.command_runner import CommandRunner
from src.shared.concurrency_helper import ConcurrencyHelper
from gi.repository import Gtk, Gdk, GLib, Gio, GObject  # pyright: ignore
from typing import Any, Optional, Callable, Union

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")


class GtkHelpers:
    def __init__(self, panel_instance):
        self.style_css_config = panel_instance.style_css_config
        self.logger = panel_instance.logger
        self.config_data = panel_instance.config_data
        self.concurrency_helper = ConcurrencyHelper(panel_instance)
        self.data_helper = DataHelpers()
        self.terminal_emulators = [
            "kitty",
            "alacritty",
            "gnome-terminal",
            "terminator",
            "tilix",
            "xterm",
            "urxvt",
            "wezterm",
            "lxterminal",
            "xfce4-terminal",
            "st",
            "rxvt",
        ]
        self.config_handler = ConfigHandler(panel_instance)
        if hasattr(panel_instance, "ipc"):
            self.command = CommandRunner(panel_instance)
        self.app_css_provider = None
        self.css_load_id = None

    def load_css_from_file(self):
        if self.app_css_provider is None:
            self.app_css_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),  # pyright: ignore
                self.app_css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        try:
            self.app_css_provider.load_from_file(
                Gio.File.new_for_path(self.config_handler.style_css_config)
            )
        except GLib.Error as e:
            self.logger.error(f"Error loading CSS file: {e.message}")

    def on_css_file_changed(
        self, monitor, file, other_file, event_type: Gio.FileMonitorEvent
    ):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            if self.css_load_id is not None:
                GLib.source_remove(self.css_load_id)

            def run_once_after_delay():
                self.load_css_from_file()
                self.css_load_id = None
                return GLib.SOURCE_REMOVE

            self.css_load_id = GLib.timeout_add(100, run_once_after_delay)

    def widget_exists(self, widget: Any) -> bool:
        """
        Check if the given object is a valid Gtk.Widget instance.
        Args:
            widget (Any): The object to check.
        Returns:
            bool: True if the object is a non-None Gtk.Widget; False otherwise.
        """
        return widget is not None and isinstance(widget, Gtk.Widget)

    def is_widget_ready(self, container: Any) -> bool:
        """
        Check if the container is ready for appending widgets.
        This checks whether the container:
        - Is a valid Gtk.Widget instance
        - Is realized (has an associated window)
        - Is visible
        Args:
            container (Any): The widget container to check.
        Returns:
            bool: True if the container is valid, realized, and visible; False otherwise.
        """
        if not self.widget_exists(container):
            return False
        if not Gtk.Widget.get_realized(container) or not Gtk.Widget.get_visible(
            container
        ):
            return False
        return True

    def set_plugin_main_icon(self, widget: Gtk.Widget, plugin_name, icon_name):
        """
        Sets the main icon for a plugin widget, deriving the plugin name from the
        calling file's name (e.g., 'my_plugin.py' becomes 'my_plugin').
        Args:
            widget (Gtk.Widget): The widget instance to set the icon on.
            fallback_icons (list): A list of backup icon names to try.
        """
        fallback_icons = self.config_handler.get_root_setting(
            [plugin_name, "fallback_main_icons"], None
        )
        icon_name = self.icon_exist(icon_name, fallback_icons)
        if icon_name:
            widget.set_icon_name(icon_name)  # pyright: ignore
        else:
            self.logger.warning(f"Could not find icon for plugin: {plugin_name}")

    def icon_exist(self, argument: str, fallback_icons=None) -> str:
        """
        Check if an icon exists based on the given application identifier, using a tiered search strategy.
        Args:
            argument (str): The application name or identifier to search for.
            fallback_icons (list, optional): A list of fallback icon names to check.
        Returns:
            str: The name of the matching icon if found, or "image-missing" otherwise.
        """
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())  # pyright: ignore

        # --- FLATPAK COMPATIBILITY INJECTION ---
        if os.path.exists("/.flatpak-info"):
            if icon_theme:
                current_paths = list(icon_theme.get_search_path())
                # Map common host icon locations mirrored by Flatpak
                host_paths = [
                    "/run/host/usr/share/icons",
                    "/run/host/usr/local/share/icons",
                    os.path.expanduser("~/.local/share/icons"),
                ]
                for hp in host_paths:
                    if os.path.isdir(hp) and hp not in current_paths:
                        current_paths.append(hp)

                icon_theme.set_search_path(current_paths)
        # ---------------------------------------

        norm_arg = self.normalize_name(argument)
        if fallback_icons is None:
            fallback_icons = [""]
        for icon in fallback_icons:
            if icon_theme.has_icon(icon):
                if not hasattr(self, "icon_cache"):
                    self.icon_cache = {}
                self.icon_cache[argument] = icon
                return icon
        try:
            if not isinstance(argument, str) or not argument.strip():
                self.logger.warning(f"Invalid or missing argument: {argument}")
                return "image-missing"
            if hasattr(self, "icon_cache") and argument in self.icon_cache:
                return self.icon_cache[argument]
            gio_icon_list = getattr(self, "gio_icon_list", [])
            for app_info in gio_icon_list:
                app_id = app_info.get_id()
                if app_id:
                    base_app_name = app_id.split(".")[-1].replace(".desktop", "")
                    norm_base_name = self.normalize_name(base_app_name)
                    if norm_arg == norm_base_name:
                        icon = app_info.get_icon()
                        icon_name = self.extract_icon_name(icon)
                        if icon_name:
                            if not hasattr(self, "icon_cache"):
                                self.icon_cache = {}
                            self.icon_cache[argument] = icon_name.lower()
                            return icon_name.lower()
            patterns = [
                norm_arg,
                f"{norm_arg}-symbolic",
                f"org.{norm_arg}.Desktop",
                f"{norm_arg}-desktop",
                f"application-x-{norm_arg}",
                f"system-{norm_arg}",
                f"utility-{norm_arg}",
                f"fedora-{norm_arg}",
                f"debian-{norm_arg}",
            ]
            for pattern in patterns:
                if icon_theme.has_icon(pattern):
                    if not hasattr(self, "icon_cache"):
                        self.icon_cache = {}
                    self.icon_cache[argument] = pattern
                    return pattern
            all_icons = icon_theme.get_icon_names()
            fuzzy_scorers = [
                rapidfuzz.fuzz.token_set_ratio,
                rapidfuzz.fuzz.partial_ratio,
                rapidfuzz.fuzz.ratio,
            ]
            for scorer in fuzzy_scorers:
                best_match = rapidfuzz.process.extractOne(
                    query=norm_arg,
                    choices=all_icons,
                    scorer=scorer,
                    processor=rapidfuzz.utils.default_process,
                    score_cutoff=85,
                )
                if best_match:
                    result = best_match[0]
                    if not hasattr(self, "icon_cache"):
                        self.icon_cache = {}
                    self.icon_cache[argument] = result
                    return result
            for icon_name in all_icons:
                norm_icon = rapidfuzz.utils.default_process(icon_name)
                if norm_arg in norm_icon or norm_icon in norm_arg:
                    if not hasattr(self, "icon_cache"):
                        self.icon_cache = {}
                    self.icon_cache[argument] = icon_name
                    return icon_name
            self.logger.debug(f"No icon found for argument: {argument}")
            if not hasattr(self, "icon_cache"):
                self.icon_cache = {}
            self.icon_cache[argument] = "image-missing"
            return "image-missing"
        except Exception as e:
            self.logger.error(
                f"Unexpected error while checking if icon exists for argument: {e}",
                exc_info=True,
            )
            if not hasattr(self, "icon_cache"):
                self.icon_cache = {}
            self.icon_cache[argument] = "image-missing"
            return "image-missing"

    def set_widget_icon_name(self, section: str, fallback_icons: list) -> str:
        """
        Determine the best icon name for a widget.
        Reads the icon from the config TOML for the given section.
        Args:
            section (str): Section name in the config (e.g., 'appmenu').
            fallback_icons (list): List of icon names to use as fallback.
        Returns:
            str: The selected icon name.
        """
        menu_icon = self.config_data.get(section, {}).get("icon", "")
        return self.icon_exist(menu_icon, fallback_icons)

    def update_widget(self, function_method: Callable[..., None], *args: Any) -> None:
        """
        Schedule a widget update to run in the main GTK thread using GLib.idle_add.
        Args:
            function_method (Callable): The callable method to execute.
            *args (Any): Variable-length argument list for the callable.
        """
        GLib.idle_add(function_method, *args)

    def update_widget_safely(self, method: Callable[..., None], *args: Any) -> bool:
        """
        Safely call a method with provided arguments if all validations pass.
        Ensures the operation is performed on the main thread using GLib.idle_add.
        Args:
            method: The callable method to invoke (e.g., container.append or set_layer_position_exclusive).
            *args: Arguments to pass to the method.
        Returns:
            bool: True if the method was successfully called, False otherwise.
        """
        if args:
            first_arg = args[0]
            if isinstance(first_arg, Gtk.Widget):
                if first_arg is None or not isinstance(first_arg, Gtk.Widget):
                    self.logger.error("Error: Invalid widget provided")
                    return False
                if first_arg.get_parent():
                    self.logger.warning(
                        "Widget already has a parent. Skipping operation."
                    )
                    return False
        try:
            self.update_widget(method, *args)
        except Exception as e:
            self.logger.error(f"Error calling method {method.__name__}: {e}")
            return False
        return True

    def search_desktop(self, app_id: str) -> Optional[str]:
        """
        Search for a desktop file associated with the given application ID.
        Includes host mirrors for Flatpak compatibility.
        """
        if not self.data_helper.validate_string(app_id):
            return None

        is_flatpak = os.path.exists("/.flatpak-info")
        search_paths = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
        ]

        if is_flatpak:
            # Map host paths to sandbox-visible mirrors
            uid = os.getuid()
            search_paths.extend(
                [
                    "/run/host/usr/share/applications",
                    "/run/host/usr/local/share/applications",
                    f"/run/host/run/user/{uid}/flatpak-install/share/applications",
                    os.path.join(
                        "/run/host",
                        os.path.expanduser("~").lstrip("/"),
                        ".local/share/applications",
                    ),
                ]
            )

        app_id_lower = app_id.lower()
        for app_dir in search_paths:
            if not os.path.isdir(app_dir):
                continue

            try:
                for file_name in os.listdir(app_dir):
                    if (
                        file_name.lower().startswith(app_id_lower)
                        or app_id_lower in file_name.lower()
                    ) and file_name.endswith(".desktop"):
                        return os.path.join(app_dir, file_name)
            except PermissionError:
                continue

        # Fallback to Gio
        try:
            all_apps = Gio.AppInfo.get_all()
            for app in all_apps:
                if app.get_id() and app_id_lower in app.get_id().lower():  # pyright: ignore
                    return app.get_id()
        except Exception as e:
            self.logger.error(f"Gio AppInfo fallback failed: {e}")

        return None

    def normalize_name(self, name: str) -> str:
        """Normalize icon/app names for comparison."""
        if isinstance(name, list):
            self.logger.error(f"Icon name is not str, type list found. {name}")
            return name[0].lower().strip()
        return name.lower().strip()

    def extract_icon_name(self, icon) -> str:
        """Extract the icon name from a Gio.Icon object."""
        if hasattr(icon, "get_names") and callable(icon.get_names):
            names = icon.get_names()
            if names:
                return names[0]  # pyright: ignore
        if hasattr(icon, "get_name") and callable(icon.get_name):
            return icon.get_name()  # pyright: ignore
        return ""

    def search_str_inside_file(self, file_path: str, word: str) -> bool:
        """
        Search for a formatted string inside a file.
        This function looks for the pattern 'name=<word>' (case-insensitive)
        within the specified file.
        Args:
            file_path (str): Path to the file to search in.
            word (str): The word to search for, formatted as 'name=<word>'.
        Returns:
            bool: True if the pattern is found, False otherwise.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read().lower()
                return f"name={word.lower()}" in content
        except Exception as e:
            self.logger.warning(f"Error reading file '{file_path}': {e}")
            return False

    def find_steam_icon(self, app_id: str) -> Optional[str]:
        """
        Searches for a Steam-related .desktop file that matches the app_id
        using StartupWMClass and fuzzy matching, returning its icon name.
        Args:
            app_id (str): The window manager class of the application.
        Returns:
            Optional[str]: The icon name if found, otherwise None.
        """
        if "steam_app_" in app_id:
            steam_icon = app_id.replace("steam_app_", "steam_icon_")
            return steam_icon
        desktop_dir = os.path.expanduser("~/.local/share/applications")
        if not os.path.isdir(desktop_dir):
            return None
        best_match = None
        best_score = 0
        app_id_lower = app_id.lower()
        for filename in os.listdir(desktop_dir):
            if not filename.endswith(".desktop"):
                continue
            desktop_file_path = os.path.join(desktop_dir, filename)
            try:
                parser = configparser.ConfigParser(interpolation=None)
                parser.read(desktop_file_path)
                if "Desktop Entry" in parser:
                    desktop_entry = parser["Desktop Entry"]
                    if "Exec" in desktop_entry and desktop_entry[
                        "Exec"
                    ].lower().startswith("steam"):
                        current_score = 0
                        if (
                            "StartupWMClass" in desktop_entry
                            and desktop_entry["StartupWMClass"].lower() == app_id_lower
                        ):
                            current_score = 100
                        else:
                            desktop_name = desktop_entry.get("Name", "")
                            filename_without_ext = os.path.splitext(filename)[0]
                            score_name = token_set_ratio(
                                app_id_lower, desktop_name.lower()
                            )
                            score_filename = token_set_ratio(
                                app_id_lower, filename_without_ext.lower()
                            )
                            current_score = max(score_name, score_filename)
                        if current_score > best_score:
                            best_score = current_score
                            best_match = desktop_file_path
            except (configparser.Error, UnicodeDecodeError) as e:
                self.logger.warning(f"Failed to parse desktop file {filename}: {e}")
                continue
        if best_match and best_score > 80:
            try:
                parser = configparser.ConfigParser(interpolation=None)
                parser.read(best_match)
                if "Desktop Entry" in parser and "Icon" in parser["Desktop Entry"]:
                    icon_name = parser["Desktop Entry"]["Icon"]
                    if self.icon_exist(icon_name):
                        self.logger.info(
                            f"Using Steam icon '{icon_name}' from best match '{os.path.basename(best_match)}' with score {best_score}"
                        )
                        return icon_name
            except (configparser.Error, UnicodeDecodeError) as e:
                self.logger.warning(
                    f"Failed to parse best match file {best_match}: {e}"
                )
        return None

    def get_icon(self, app_id: str, initial_title: str, title: str) -> Optional[str]:
        """
        Retrieve an appropriate icon name based on window metadata.
        Args:
            app_id (str): The window manager class of the application.
            initial_title (str): The original title of the window.
            title (str): The current title of the window.
        Returns:
            Optional[str]: The icon name if found, otherwise None.
        """
        app_id = app_id.lower()
        initial_title = initial_title.lower()
        title = title.lower()
        steam_icon = self.find_steam_icon(app_id)
        if steam_icon:
            return steam_icon
        filtered_title = self.filter_utf_for_gtk(title)
        first_word = filtered_title.split()[0] if filtered_title else ""
        if filtered_title != app_id:
            for terminal in self.terminal_emulators:
                if terminal in app_id and terminal not in filtered_title:
                    title_icon = self.icon_exist(first_word or initial_title)
                    if title_icon != "image-missing":
                        return title_icon
        web_apps = {
            "msedge",
            "microsoft-edge",
            "microsoft-edge-dev",
            "microsoft-edge-beta",
        }
        if any(app in app_id.lower() for app in web_apps):
            desk_local = self.search_local_desktop(initial_title)
            if desk_local and desk_local.lower().endswith("-default.desktop"):
                base_name, _ = os.path.splitext(os.path.basename(desk_local))
                if base_name.lower().startswith("msedge-"):
                    return base_name
            else:
                return self.icon_exist("microsoft-edge")
        found_icon = self.icon_exist(app_id)
        if found_icon:
            return found_icon

    def handle_icon_for_button(self, view: dict, button) -> None:
        """
        Set an appropriate icon for the button based on the view's details.
        Args:
            view (dict): The view object containing details like title and app-id.
            button (Gtk.Button): The button to which the icon will be applied.
        """
        app_id = None
        try:
            title = view.get("title", "")
            initial_title = title.split()[0] if title else ""
            app_id = view.get("app-id", "")
            icon_path = self.get_icon(app_id, title, initial_title)
            if not icon_path:
                self.logger.debug(f"No icon found for view: {app_id}")
                button.set_icon_name("default-icon-name")
                return
            self.logger.debug(f"Icon retrieved for view: {app_id} -> {icon_path}")
            if icon_path.startswith("/"):
                try:
                    image = Gtk.Image.new_from_file(icon_path)
                    if isinstance(image, Gtk.Image):
                        button.set_child(image)
                    else:
                        self.logger.error("Error: Invalid image provided")
                        button.set_icon_name("default-icon-name")
                except Exception as e:
                    self.logger.error(f"Error loading icon from file: {e}")
                    button.set_icon_name("default-icon-name")
            else:
                button.set_icon_name(icon_path)
        except Exception as e:
            self.logger.error(
                f"Unexpected error while handling icon for button: {app_id}, {e}",
                exc_info=True,
            )
            button.set_icon_name("default-icon-name")

    def find_icon_for_app_id(self, app_id: str) -> Optional[str]:
        """
        Find an icon for a given application ID.
        Args:
            app_id (str): The application ID to search for.
        Returns:
            Optional[str]: The icon name or path if found, otherwise None.
        """
        try:
            if not app_id or not isinstance(app_id, str):
                self.logger.warning(f"Invalid or missing app_id: {app_id}")
                return None

            def normalize_icon_name(app_id: str) -> str:
                if "." in app_id:
                    return app_id.split(".")[-1]
                return app_id

            app_id = app_id.lower()
            normalized_app_id = normalize_icon_name(app_id)
            try:
                app_list = Gio.AppInfo.get_all()
            except Exception as e:
                self.logger.error(
                    f"Failed to retrieve installed applications: {e}", exc_info=True
                )
                return None
            for app in app_list:
                try:
                    app_info_id = app.get_id().lower()  # pyright: ignore
                    if not app_info_id:
                        continue
                    if (
                        app_info_id.startswith(normalized_app_id)
                        or normalized_app_id in app_info_id
                    ):
                        icon = app.get_icon()
                        if not icon:
                            continue
                        if isinstance(icon, Gio.ThemedIcon):
                            icon_names = icon.get_names()
                            if icon_names:
                                return icon_names[0]
                        elif isinstance(icon, Gio.FileIcon):
                            file_path = icon.get_file().get_path()
                            if file_path:
                                return file_path
                except Exception as e:
                    self.logger.error(
                        f"Error processing application: {e}", exc_info=True
                    )
            self.logger.debug(f"No icon found for app_id: {app_id}")
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error while finding icon for app_id {app_id}: {e}",
                exc_info=True,
            )
            return None

    def filter_utf_for_gtk(self, byte_string: Union[bytes, str]) -> str:
        """
        Safely decode a byte string to UTF-8, handling all encoding issues, with priority to UTF-8.
        Args:
            byte_string (Union[bytes, str]): The input byte string or already decoded string.
        Returns:
            str: The decoded string with invalid characters replaced or ignored.
        """
        try:
            if isinstance(byte_string, str):
                return byte_string.lower()
            if isinstance(byte_string, bytes):
                encodings = [
                    "utf-8",
                    "utf-16",
                    "utf-32",
                    "utf-16-le",
                    "utf-16-be",
                    "utf-32-le",
                    "utf-32-be",
                ]
                for encoding in encodings:
                    try:
                        self.logger.debug(f"Attempting to decode using {encoding}...")
                        return byte_string.decode(encoding, errors="replace")
                    except UnicodeDecodeError as e:
                        self.logger.warning(
                            f"Failed to decode using {encoding}. Details: {e}"
                        )
                self.logger.info(
                    "All UTF decoding attempts failed, falling back to 'latin-1'."
                )
                return byte_string.decode("latin-1", errors="replace").lower()
        except Exception as e:
            self.logger.error(
                f"Unexpected error while filtering UTF for GTK: {byte_string} and {e}",
                exc_info=True,
                extra={"input_type": type(byte_string).__name__},
            )
            return ""

    def add_cursor_effect(self, widget):
        motion = Gtk.EventControllerMotion()
        motion.connect(
            "enter",
            lambda c, x, y: widget.set_cursor(
                Gdk.Cursor.new_from_name("pointer", None)
            ),
        )
        motion.connect(
            "leave",
            lambda c: widget.set_cursor(None),
        )
        widget.add_controller(motion)

    def create_button(
        self,
        icon_name: str,
        cmd: str,
        class_style: str,
        use_label: bool = False,
        use_function: Optional[Callable] = None,
        use_args: Optional[Any] = None,
    ) -> Optional[Gtk.Button]:
        """Creates a Gtk.Button with strictly constrained sizing and click handling.

        Args:
            icon_name: The name of the icon or label text.
            cmd: The command to execute. Use "NULL" to disable the button.
            class_style: The CSS class to apply.
            use_label: Whether to use a label instead of an icon.
            use_function: A function to execute on button click.
            use_args: Arguments to pass to the custom function.

        Returns:
            The configured Gtk.Button or None if validation fails.
        """
        try:
            if not icon_name:
                self.logger.error("Invalid input: icon_name must be provided.")
                return None

            valid_icon = self.icon_exist(icon_name)
            button = Gtk.Button()

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)
            box.set_hexpand(False)
            box.set_vexpand(False)

            if use_label:
                child = Gtk.Label(label=valid_icon)
            else:
                child = Gtk.Image.new_from_icon_name(valid_icon)

            child.set_hexpand(False)
            child.set_vexpand(False)
            box.append(child)
            button.set_child(box)

            if class_style:
                button.add_css_class(class_style)
                box_class_name = f"box-{class_style}"
                box.add_css_class(box_class_name)

            if cmd == "NULL":
                button.set_sensitive(False)
                return button

            handler = (
                (lambda *_: use_function(use_args))
                if use_function
                else (lambda *_: self.command.run(cmd))
            )
            button.connect("clicked", handler)

            return button

        except Exception as e:
            self.logger.error(f"Error creating button: {e}", exc_info=True)
            return None

    def search_local_desktop(self, initial_title: str) -> Optional[str]:
        """
        Search for a desktop file matching the given title in the webapps directory.
        This function scans `.desktop` files in the `self.webapps_applications` directory,
        checking if their filename starts with specific prefixes (chrome, msedge, FFPWA-).
        It then searches for the given title inside each file and returns the first match.
        Args:
            initial_title (str): The title to search for inside the desktop files.
        Returns:
            Optional[str]: The matched desktop file name if found, otherwise None.
        """
        for deskfile in os.listdir(self.config_handler.webapps_applications):
            if not deskfile.startswith(("chrome", "msedge", "FFPWA-")):
                continue
            webapp_path = os.path.join(
                self.config_handler.webapps_applications, deskfile
            )
            if self.search_str_inside_file(webapp_path, initial_title.lower()):
                return deskfile
        return None

    def layer_shell_check(self) -> None:
        """
        Check if gtk4-layer-shell is installed; clone and build it from source if not.
        This function performs the following steps:
        1. Checks for an existing installation by looking for a key shared library file.
        2. If not found, clones the repository from GitHub into a temporary directory.
        3. Sets up the build environment using Meson.
        4. Builds and installs gtk4-layer-shell locally under ~/.local/lib/gtk4-layer-shell.
        Logs are generated at each step for transparency and debugging.
        """
        try:
            install_path = os.path.expanduser("~/.local/lib/gtk4-layer-shell")
            installed_marker = os.path.join(install_path, "libgtk_layer_shell.so")
            temp_dir = "/tmp/gtk4-layer-shell"
            repo_url = "https://github.com/wmww/gtk4-layer-shell.git"
            build_dir = "build"
            if os.path.exists(installed_marker):
                self.logger.info("gtk4-layer-shell is already installed.")
                return
            self.logger.info("gtk4-layer-shell is not installed. Installing...")
            try:
                if not os.path.exists(temp_dir):
                    self.logger.info(f"Creating temporary directory: {temp_dir}")
                    os.makedirs(temp_dir)
            except Exception as e:
                self.logger.error(
                    error=e, message=f"Failed to create temporary directory: {temp_dir}"
                )
                return
            try:
                self.logger.info(f"Cloning repository from: {repo_url}")
                subprocess.run(["git", "clone", repo_url, temp_dir], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e, message="Failed to clone the gtk4-layer-shell repository."
                )
                return
            try:
                os.chdir(temp_dir)
            except Exception as e:
                self.logger.error(
                    error=e, message=f"Failed to change directory to: {temp_dir}"
                )
                return
            try:
                self.logger.info("Configuring the build environment...")
                subprocess.run(
                    [
                        "meson",
                        "setup",
                        f"--prefix={install_path}",
                        "-Dexamples=true",
                        "-Ddocs=true",
                        "-Dtests=true",
                        build_dir,
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e,
                    message="Failed to configure the build environment with Meson.",
                )
                return
            try:
                self.logger.info("Building the project...")
                subprocess.run(["ninja", "-C", build_dir], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e, message="Failed to build the gtk4-layer-shell project."
                )
                return
            try:
                self.logger.info("Installing the project...")
                subprocess.run(["ninja", "-C", build_dir, "install"], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    error=e, message="Failed to install the gtk4-layer-shell project."
                )
                return
            self.logger.info("gtk4-layer-shell installation complete.")
        except Exception as e:
            self.logger.error(
                error=e,
                message="Unexpected error during gtk4-layer-shell installation.",
            )

    def extract_icon_info(self, application_name: str) -> Optional[str]:
        """
        Extract the icon name for a given application by searching desktop files.
        Includes host mirrors for Flatpak compatibility.
        """
        search_paths = [
            "/usr/share/applications/",
            os.path.expanduser("~/.local/share/applications/"),
            "/run/host/usr/share/applications/",
        ]

        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue

            for file_name in os.listdir(search_path):
                if not file_name.endswith(".desktop"):
                    continue

                file_path = os.path.join(search_path, file_name)
                try:
                    with open(
                        file_path, "r", encoding="utf-8", errors="ignore"
                    ) as desktop_file:
                        found_name = False
                        for line in desktop_file:
                            clean_line = line.strip()
                            if clean_line.startswith("Name="):
                                app_name = clean_line.split("=", 1)[1]
                                if app_name == application_name:
                                    found_name = True
                            elif found_name and clean_line.startswith("Icon="):
                                icon_name = clean_line.split("=", 1)[1]
                                self.logger.debug(
                                    f"Found icon '{icon_name}' for '{application_name}' in: {file_path}"
                                )
                                return icon_name
                except Exception as e:
                    self.logger.error(f"Error reading desktop file {file_path}: {e}")

        self.logger.info(f"No icon found for application: {application_name}")
        return None

    def remove_widget(self, widget: Any) -> bool:
        """
        Safely remove a widget from its parent using .unparent().
        Args:
            widget (Any): The widget to remove. Must be a Gtk.Widget instance.
        Returns:
            bool: True if the widget was successfully unparented, False otherwise.
        """
        if not isinstance(widget, Gtk.Widget):
            self.logger.error("Invalid widget provided for removal.")
            return False
        parent = widget.get_parent()
        if not parent:
            self.logger.warning("Widget has no parent. Skipping removal.")
            return False
        try:
            widget.unparent()
            self.logger.debug(f"Successfully unparented widget: {widget}")
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to unparent widget: {widget} - Error: {e}", exc_info=True
            )
            return False

    def create_popover(
        self,
        parent_widget,
        css_class: str = "plugin-default-popover",
        has_arrow: bool = True,
        closed_handler=None,
        visible_handler=None,
        offset=(0, 5),
    ):
        """
        Creates and configures a standard Gtk.Popover for use in plugins.
        This function extracts the generic popover setup logic from AppLauncher.
        Args:
            gtk (module): The Gtk module (e.g., gi.repository.Gtk).
            parent_widget (Gtk.Widget): The widget the popover will be parented to.
            css_class (str, optional): A custom CSS class to add to the popover.
                                       Defaults to "plugin-default-popover".
            has_arrow (bool, optional): Whether the popover should display an arrow
                                        pointing to its parent. Defaults to True.
            closed_handler (function, optional): Handler for the 'closed' signal.
            visible_handler (function, optional): Handler for the 'notify::visible' signal.
        Returns:
            Gtk.Popover: The configured popover object.
        """
        popover = Gtk.Popover()
        popover.add_css_class(css_class)
        popover.set_has_arrow(has_arrow)
        x, y = offset
        popover.set_offset(x, y)
        if closed_handler:
            popover.connect("closed", closed_handler)
        if visible_handler:
            popover.connect("notify::visible", visible_handler)
        popover.set_parent(parent_widget)
        return popover

    def create_menu_with_actions(self, action_map: dict, action_prefix: str = "app"):
        """
        Creates a Gtk.MenuButton with a Gtk.Menu and a Gio.SimpleActionGroup based on a
        recursive dictionary structure of actions and optional submenus.
        This version uses the documented and simpler Gio.MenuItem.set_icon() method,
        which correctly handles GIcon serialization internally, matching the requirement
        for the "icon" attribute.
        Args:
            action_map (dict): A recursive dictionary defining menu items and submenus.
            action_prefix (str, optional): The namespace for the menu actions (e.g., 'app').
        Returns:
            Gtk.MenuButton: A fully configured Gtk.MenuButton.
        """
        action_group = Gio.SimpleActionGroup()

        def _create_menu_recursive(menu_config: dict) -> Gio.Menu:
            """Recursively builds the Gio.Menu and populates the action_group."""
            menu = Gio.Menu()
            for key, config in menu_config.items():
                if config.get("is_submenu", False):
                    submenu_label = key
                    submenu_config = config.get("items", {})
                    submenu = _create_menu_recursive(submenu_config)
                    menu.append_submenu(submenu_label, submenu)
                else:
                    action_name = key
                    menu_item_label = config["label"]
                    action_id = f"{action_prefix}.{action_name}"
                    menu_item = Gio.MenuItem.new(menu_item_label, action_id)
                    icon_name = config.get("icon")
                    if icon_name:
                        gicon = Gio.ThemedIcon.new(icon_name)
                        menu_item.set_icon(gicon)
                    menu.append_item(menu_item)
                    action = Gio.SimpleAction.new(action_name, None)
                    callback = config["callback"]
                    if config.get("is_async", False):
                        action.connect(
                            "activate",
                            lambda *args,
                            cb=callback: self.concurrency_helper.run_in_async_task(
                                cb()
                            ),
                        )
                    else:
                        action.connect("activate", callback)
                    action_group.add_action(action)
            return menu

        menu = _create_menu_recursive(action_map)
        menubutton = Gtk.MenuButton()
        menubutton.set_menu_model(menu)
        menubutton.insert_action_group(action_prefix, action_group)
        return menubutton

    def create_async_button(self, label: str, callback, css_class: str) -> Gtk.Button:
        """
        Creates a Gtk.Button, connects its 'clicked' signal to an asynchronous
        task wrapper, and applies an optional CSS class.
        """
        button = Gtk.Button(label=label)
        button.connect(
            "clicked",
            lambda *args: self.concurrency_helper.run_in_async_task(callback()),
        )
        if css_class:
            button.add_css_class(css_class)
        return button

    def create_dashboard_popover(
        self,
        parent_widget,
        popover_closed_handler,
        popover_visible_handler,
        action_handler,
        button_config: dict,
        module_name: str = "",
        max_children_per_line: int = 3,
    ):
        """
        Creates and configures a reusable dashboard popover containing a Gtk.Stack
        of categorized Gtk.FlowBox widgets, based on the provided configuration.
        Args:
            parent_widget: The widget the popover is attached to.
            popover_closed_handler: The callback function for popover closure.
            popover_visible_handler: The callback function for popover visibility.
            action_handler: The callback function for button clicks.
            button_config (dict): A dict defining buttons:
                                  { "Label": {"icons": ["name1"], "summary": "...", "category": "..."} }
            module_name (str): A prefix for CSS classes to avoid conflicts.
            max_children_per_line (int): Max number of buttons per row.
        Returns:
            Gtk.Popover: The fully configured dashboard popover.
        """
        prefixed_css_class = f"{module_name}-popover"
        prefixed_label_class = f"{module_name}-label"
        prefixed_summary_class = f"{module_name}-summary"
        prefixed_stack_class = f"{module_name}-stack"
        prefixed_icon_vbox_class = f"{module_name}-icon-vbox"
        prefixed_button_class = f"{module_name}-button"
        popover_dashboard = self.create_popover(
            parent_widget=parent_widget,
            css_class=prefixed_css_class,
            has_arrow=True,
            closed_handler=popover_closed_handler,
            visible_handler=popover_visible_handler,
        )
        categorized_buttons = {}
        for label, config in button_config.items():
            category = config.get("category", "General")
            if category not in categorized_buttons:
                categorized_buttons[category] = []
            categorized_buttons[category].append((label, config))
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        stack = Gtk.Stack()
        stack.add_css_class(prefixed_stack_class)
        for category, items in categorized_buttons.items():
            flowbox = Gtk.FlowBox(
                homogeneous=True,
                valign=Gtk.Align.START,
                margin_start=15,
                margin_end=15,
                margin_top=10,
                margin_bottom=15,
                max_children_per_line=max_children_per_line,
                selection_mode=Gtk.SelectionMode.NONE,
            )
            for label, config in items:
                icon_name = self.icon_exist(
                    config.get("icons", [None])[0],
                    config.get("icons", [None, None])[1:],
                )
                icon_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                icon_vbox.add_css_class(prefixed_icon_vbox_class)
                if icon_name:
                    icon = Gtk.Image.new_from_icon_name(icon_name)
                    icon.set_icon_size(Gtk.IconSize.LARGE)
                    icon_vbox.append(icon)
                name_label = Gtk.Label(label=label)
                name_label.add_css_class(prefixed_label_class)
                icon_vbox.append(name_label)
                summary_label = Gtk.Label(label=config.get("summary", ""))
                summary_label.add_css_class(prefixed_summary_class)
                icon_vbox.append(summary_label)
                button = Gtk.Button(child=icon_vbox, has_frame=False)
                button.add_css_class(prefixed_button_class)
                button.connect("clicked", action_handler, label)
                self.add_cursor_effect(button)
                flowbox.append(button)
            stack.add_titled(flowbox, category.replace("_", " "), category)
        if len(categorized_buttons) > 1:
            stack_switcher = Gtk.StackSwitcher()
            stack_switcher.set_stack(stack)
            stack_switcher.set_margin_top(10)
            stack_switcher.set_margin_start(10)
            stack_switcher.set_margin_end(10)
            main_box.append(stack_switcher)
            main_box.append(Gtk.Separator(margin_top=5, margin_bottom=5))
        main_box.append(stack)
        popover_dashboard.set_child(main_box)
        popover_dashboard.popup()
        return popover_dashboard

    def safe_remove_css_class(self, widget: Gtk.Widget, class_name: str):
        """
        Removes a CSS class only if it is currently present on the widget.
        Prevents the Gtk:ERROR assertion failure.
        """
        if class_name in widget.get_css_classes():
            widget.remove_css_class(class_name)

    def clear_listbox(self, listbox: Gtk.ListBox):
        """
        Clears all children from a Gtk.ListBox and explicitly unparents them.
        Args:
            listbox (Gtk.ListBox | None): The listbox widget to clear.
        """
        try:
            while True:
                row = listbox.get_row_at_index(0)
                if row is None:
                    break
                if not isinstance(row, Gtk.ListBoxRow):
                    break
                listbox.remove(row)
                row.unparent()
        except Exception as e:
            self.logger.exception(f"Gtk Helper failed to clear Gtk.ListBox: {e}")

    def count_box_items(self, box: Gtk.Box) -> int:
        """
        Count the number of child widgets currently appended to a Gtk.Box.
        This function uses the GTK4 `observe_children()` API to safely
        iterate over the box's current children. It works with any
        Gtk.Box instance regardless of layout orientation.
        Args:
            box (Gtk.Box): The Gtk.Box widget whose children you want to count.
        Returns:
            int: The number of widgets currently appended to the box.
        """
        return len(list(box.observe_children()))

    def set_clipboard_text(self, text: str) -> None:
        """
        Sets the string content onto the system clipboard using the 'wl-copy' utility.
        This method utilizes inter-process communication (IPC) via 'subprocess'
        to interface directly with the Wayland compositor's clipboard manager,
        bypassing the GDK/GTK clipboard abstraction layer for optimal stability.
        Args:
            text: The string content to place on the clipboard.
        Raises:
            RuntimeError: If the 'wl-copy' utility fails, is not found, or times out.
        """
        import subprocess

        try:
            subprocess.run(
                ["wl-copy"],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                timeout=2,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Clipboard utility 'wl-copy' not found. Ensure 'wl-clipboard' is installed."
            )
        except subprocess.CalledProcessError as e:
            error_output = (
                e.stderr.decode("utf-8").strip() if e.stderr else "No detailed output."
            )
            raise RuntimeError(
                f"Clipboard copy failed (wl-copy exited with code {e.returncode}). Output: {error_output}"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Clipboard copy timed out waiting for 'wl-copy' process."
            )
