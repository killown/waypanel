import gi
import configparser
import rapidfuzz
import subprocess
import os
import inspect
from rapidfuzz.fuzz import token_set_ratio
from src.shared.data_helpers import DataHelpers
from src.shared.config_handler import ConfigHandler
from src.shared.command_runner import CommandRunner
from gi.repository import Gtk, Gdk, GLib, Gio  # pyright: ignore
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
        self.data_helper = DataHelpers()
        self.terminal_emulators = [
            "kitty",
            "gnome-terminal",
            "terminator",
            "xterm",
            "konsole",
            "urxvt",
            "alacritty",
            "wezterm",
            "lxterminal",
            "xfce4-terminal",
            "tilix",
            "st",
            "rxvt",
        ]
        self.config_handler = ConfigHandler(panel_instance)
        if hasattr(panel_instance, "ipc"):
            self.command = CommandRunner(panel_instance)

    def on_css_file_changed(
        self, monitor, file, other_file, event_type: Gio.FileMonitorEvent
    ):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:

            def run_once():
                self.load_css_from_file()
                return False

            GLib.idle_add(run_once)

    def load_css_from_file(self):
        css_provider = Gtk.CssProvider()
        try:
            css_provider.load_from_file(
                Gio.File.new_for_path(self.config_handler.style_css_config)
            )
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),  # pyright: ignore
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        except GLib.Error as e:
            self.logger.error(f"Error loading CSS file: {e.message}")

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
        fallback_icons = self.config_handler.check_and_get_config(
            ["plugins", plugin_name, "fallback_main_icons"]
        )
        icon_name = self.icon_exist(icon_name)
        if not icon_name:
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
        This function searches through installed applications to find a matching desktop file
        whose ID contains the provided `app_id`.
        Args:
            app_id (str): The application ID or app_id to search for.
        Returns:
            Optional[str]: The ID of the first matching desktop file if found, or None if no match is found.
        """
        try:
            if not self.data_helper.validate_string(app_id):
                self.logger.warning(f"Invalid or missing app_id: {app_id}")
                return None
            try:
                all_apps = Gio.AppInfo.get_all()
            except Exception as e:  # pyright: ignore
                self.logger.error(f"Failed to retrieve installed applications. {e}")
                return None
            desktop_files = [
                app.get_id().lower()  # pyright: ignore
                for app in all_apps
                if app.get_id() and app_id.lower() in app.get_id().lower()  # pyright: ignore
            ]
            if desktop_files:
                self.logger.debug(
                    f"Found desktop file for app_id '{app_id}': {desktop_files[0]}"
                )
                return desktop_files[0]
            else:
                self.logger.info(f"No desktop file found for app_id: {app_id}")
                return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error while searching for desktop file with app_id: {app_id} {e}",
            )
            return None

    def normalize_name(self, name: str) -> str:
        """Normalize icon/app names for comparison."""
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
        """
        Create a Gtk.Button with an icon or label, click behavior, and CSS styling.
        Args:
            icon_name (str): The name of the icon or label text.
            cmd (str): The command to execute on button click. Use "NULL" to disable the button.
            class_style (str): The CSS class to apply to the button.
            use_label (bool): Whether to use a label instead of an icon.
            use_function (Optional[Callable]): A function to execute on button click.
            use_args (Optional[Any]): Arguments to pass to the custom function.
        Returns:
            Optional[Gtk.Button]: The created button, or None if creation failed.
        """
        try:
            if not icon_name and not use_label:
                self.logger.error(
                    "Invalid input: Either icon_name or use_label must be provided.",
                    exc_info=True,
                )
                return None
            icon_name = self.icon_exist(icon_name)
            button = Gtk.Button()
            assert button is not None, "Button creation failed"
            box = Gtk.Box()
            if use_label:
                label = Gtk.Label(label=icon_name)
                box.append(label)
            else:
                if icon_name:
                    try:
                        icon = Gtk.Image.new_from_icon_name(icon_name)
                        box.append(icon)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to create icon with name: {icon_name}",
                            exc_info=True,
                        )
                        return None
            button.set_child(box)
            if cmd == "NULL":
                button.set_sensitive(False)
                return button
            if use_function:
                try:
                    button.connect("clicked", lambda *_: use_function(use_args))
                except Exception as e:
                    self.logger.error(
                        f"Failed to connect custom function to button: {e}",
                        exc_info=True,
                    )
                    return None
            else:
                try:
                    button.connect("clicked", lambda *_: self.command.run(cmd))
                except Exception as e:
                    self.logger.error(
                        f"Failed to connect command '{cmd}' to button: {e}",
                        exc_info=True,
                    )
                    return None
            try:
                button.add_css_class(class_style)
            except Exception as e:
                self.logger.error(
                    f"Failed to apply CSS class '{class_style}' to button: {e}",
                    exc_info=True,
                )
                return None
            return button
        except Exception as e:
            self.logger.error(
                f"Unexpected error while creating button: {e}", exc_info=True
            )
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
        This function searches through standard desktop file directories to find an entry
        matching the provided application name, then returns the associated icon name.
        Args:
            application_name (str): The name of the application to search for.
        Returns:
            Optional[str]: The icon name if found, or None if no matching application is found.
        """
        search_paths = [
            "/usr/share/applications/",
            os.path.expanduser("~/.local/share/applications/"),
        ]
        try:
            for search_path in search_paths:
                if not os.path.exists(search_path):
                    self.logger.debug(f"Search path does not exist: {search_path}")
                    continue
                try:
                    for file_name in os.listdir(search_path):
                        if not file_name.endswith(".desktop"):
                            continue
                        file_path = os.path.join(search_path, file_name)
                        try:
                            with open(file_path, "r") as desktop_file:
                                found_name = False
                                for line in desktop_file:
                                    if line.startswith("Name="):
                                        app_name = line.strip().split("=")[1]
                                        if app_name == application_name:
                                            found_name = True
                                    elif found_name and line.startswith("Icon="):
                                        icon_name = line.strip().split("=")[1]
                                        self.logger.debug(
                                            f"Found icon '{icon_name}' for application '{application_name}' in file: {file_path}"
                                        )
                                        return icon_name
                        except Exception as e:
                            self.logger.error(
                                error=e,
                                message=f"Error reading desktop file: {file_path}",
                                context={"file": file_path},
                            )
                except Exception as e:
                    self.logger.error(
                        error=e,
                        message=f"Error listing files in directory: {search_path}",
                        context={"directory": search_path},
                    )
        except Exception as e:
            self.logger.error(
                error=e, message="Unexpected error while extracting icon info."
            )
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
