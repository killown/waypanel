import asyncio
import math
import os
import socket
import subprocess
from subprocess import call, check_output
from time import sleep
import logging
import sys
import aiohttp
import gi
import numpy as np
import orjson as json
import toml
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.extra.stipc import Stipc

from waypanel.src.ipc_server.ipc_client import WayfireClientIPC

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


class Utils(Adw.Application):
    def __init__(self, application_id=None, **kwargs):
        super().__init__(application_id=application_id, **kwargs)
        self._setup_config_paths()
        self.psutil_store = {}
        self.panel_cfg = self.load_topbar_config()
        self.icon_names = [icon for icon in Gtk.IconTheme().get_icon_names()]
        self.gio_icon_list = Gio.AppInfo.get_all()
        self.gestures = {}
        self.fd = None
        self.watch_id = None
        self.sock = WayfireSocket()

        self.ipc_client = WayfireClientIPC(self.handle_event)
        # here is where the ipc events happen
        self.ipc_client.wayfire_events_setup("/tmp/waypanel-utils.sock")

        self.wf_utils = WayfireUtils(self.sock)
        self.stipc = Stipc(self.sock)

        self.focused_view_id = None
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_path)

        self.is_scale_active = {}
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

    @staticmethod
    def handle_exceptions(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"An error occurred in {func.__name__}: {e}")
                return None

        return wrapper

    def connect_socket(self):
        """Establish a connection to the Unix socket."""
        socket_path = "/tmp/waypanel-utils.sock"
        self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.client_socket.connect(socket_path)

        # Create a GLib IO Watcher
        self.source = GLib.io_add_watch(
            self.client_socket,
            GLib.PRIORITY_DEFAULT,
            GLib.IO_IN,
            self.handle_socket_event,
        )

    def handle_socket_event(self, fd, condition):
        """Read from the socket and process events."""
        chunk = fd.recv(1024).decode()
        if not chunk:
            return GLib.SOURCE_REMOVE  # Remove source if no data is received

        self.buffer += chunk

        # Process the complete events in the buffer
        while "\n" in self.buffer:
            event_str, self.buffer = self.buffer.split("\n", 1)
            if event_str:
                try:
                    event = json.loads(event_str)
                    self.process_event(event)
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")

        return GLib.SOURCE_CONTINUE  # Continue receiving data

    def process_event(self, event):
        """Process the event dictionary."""
        print(f"Received event: {event}")
        self.handle_event(event)

    def disconnect_socket(self):
        """Clean up resources."""
        if self.source:
            self.source.remove()  # Remove the source when done
        if self.client_socket:
            self.client_socket.close()

    def wayfire_events_setup(self):
        """Initialize the Wayfire event listener within a GTK application."""
        # Create a GTK application
        app = Gtk.Application(application_id="com.example.GtkApplication")

        # Define the path for the Unix socket
        self.connect_socket()

    def logger(self):
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),  # Log to console
                logging.FileHandler("/tmp/waypanel.log"),
            ],
        )
        return logging.getLogger(__name__)

    def run_app(self, cmd, wclass=None, initial_title=None, cmd_mode=True):
        if [c for c in self.terminal_emulators if cmd in c] and cmd_mode:
            # **note-taking**
            # replace this function with stipc
            self.stipc.run_cmd(cmd)

    def find_view_middle_cursor_position(self, view_geometry, monitor_geometry):
        # Calculate the middle position of the view
        view_middle_x = view_geometry["x"] + view_geometry["width"] // 2
        view_middle_y = view_geometry["y"] + view_geometry["height"] // 2

        # Calculate the offset from the monitor's top-left corner
        cursor_x = monitor_geometry["x"] + view_middle_x
        cursor_y = monitor_geometry["y"] + view_middle_y

        return cursor_x, cursor_y

    def move_cursor_middle(self, view_id):
        view = self.sock.get_view(view_id)
        output_id = view["output-id"]
        view_geometry = view["geometry"]
        output_geometry = self.sock.get_output(output_id)["geometry"]
        cursor_x, cursor_y = self.find_view_middle_cursor_position(
            view_geometry, output_geometry
        )
        self.stipc.move_cursor(cursor_x, cursor_y)

    def run_cmd(self, command):
        try:
            self.stipc.run_cmd(command)
        except Exception as e:
            print(f"utils: self.run_cmd: {e}")

    def widget_exists(self, widget):
        return widget is not None and isinstance(widget, Gtk.Widget)

    def is_widget_ready(self, container):
        """
        Check if the container and widget are both ready for appending.

        Args:
            container (Gtk.Widget): The container to which the widget will be appended.
            widget (Gtk.Widget): The widget to be appended.

        Returns:
            bool: True if the container and widget are both valid, realized, and visible.
        """
        # Check if both the container and widget are not None and are instances of Gtk.Widget
        if not self.widget_exists(container):
            return False

        # Check if the container is realized and visible
        if not Gtk.Widget.get_realized(container) or not Gtk.Widget.get_visible(
            container
        ):
            return False

        return True

    def get_nearest_icon_name(self, app_name: str, size=Gtk.IconSize.LARGE) -> str:
        """
        Get the best matching icon name for an application (GTK4 synchronous version).
        Returns immediately with the icon name or fallback.

        Args:
            app_name: Application name (e.g. 'firefox')
            size: Preferred icon size (Gtk.IconSize)

        Returns:
            Best matching icon name with fallbacks
        """
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        app_name = app_name.lower().strip()

        # Ordered list of possible icon name patterns
        patterns = [
            # Application-specific
            app_name,
            f"{app_name}-symbolic",
            f"org.{app_name}.Desktop",
            f"{app_name}-desktop",
            # Generic formats
            f"application-x-{app_name}",
            f"system-{app_name}",
            f"utility-{app_name}",
            # Vendor prefixes
            f"fedora-{app_name}",
            f"debian-{app_name}",
        ]

        # Check exact matches first
        for pattern in patterns:
            if icon_theme.has_icon(pattern):
                return pattern

        # Search for partial matches
        try:
            all_icons = icon_theme.get_icon_names()
            matches = [icon for icon in all_icons if app_name in icon.lower()]
            if matches:
                return matches[0]  # Return first match
        except Exception as e:
            print(f"Icon search error: {e}")

        # Final fallbacks
        for fallback in [
            "application-x-executable",
            "image-missing",
            "gtk-missing-image",
        ]:
            if icon_theme.has_icon(fallback):
                return fallback

        return "image-missing"

    def append_widget_if_ready(self, container, widget):
        if widget is None or not isinstance(widget, Gtk.Widget):
            print("Error: Invalid widget provided")
            return False

        if not widget.get_parent():
            container.append(widget)

        return True

    def CreateWorkspacePanel(
        self, config, orientation, class_style, callback=None, use_label=False
    ):
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        if orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        box = Gtk.Box(spacing=10, orientation=orientation)

        with open(config, "r") as f:
            config_data = toml.load(f)

            for app in config_data:
                wclass = None
                initial_title = None

                try:
                    wclass = config_data[app]["wclass"]
                except KeyError:
                    pass

                button = self.create_button(
                    config_data[app]["icon"],
                    config_data[app]["cmd"],
                    class_style,
                    wclass,
                    initial_title,
                    use_label,
                )
                if self.widget_exists(button):
                    if callback is not None:
                        self.create_gesture(button, 3, callback)
                    self.append_widget_if_ready(box, button)
                else:
                    print(f"Error: Failed to create button for app {app}")

        return box

    def find_dock_icon(self, app_id):
        with open(self.dockbar_config, "r") as f:
            config_data = toml.load(f)

            for app in config_data:
                try:
                    wclass = config_data[app]["wclass"]
                    if app_id in wclass:
                        icon = config_data[app]["icon"]
                        return icon
                    else:
                        return None
                except KeyError:
                    return None

    def get_monitor_info(self):
        """
        Retrieve information about the connected monitors.

        This function retrieves information about the connected monitors,
        such as their dimensions and names,
        and returns the information as a dictionary.

        Returns:
            dict: A dictionary containing information
            about the connected monitors.
        """
        # get default display and retrieve
        # information about the connected monitors
        screen = Gdk.Display.get_default()
        monitors = screen.get_monitors()
        monitor_info = {}
        for monitor in monitors:
            monitor_width = monitor.get_geometry().width
            monitor_height = monitor.get_geometry().height
            name = monitor.props.connector
            monitor_info[name] = [monitor_width, monitor_height]

        return monitor_info

    def take_note_app(self, *_):
        """
        Open the note-taking application specified in the configuration file.

        This function reads the configuration file to retrieve the command for
        the note-taking application,
        and then executes the command to open the application.

        Args:
            *_: Additional arguments (unused).

        Returns:
            None
        """
        # Read the configuration file and load the configuration
        with open(self.topbar_config, "r") as f:
            config = toml.load(f)

        # Run the note-taking application using the specified command
        self.run_app(config["take_note_app"]["cmd"])

    def reconnect_client(self, socket):
        socket.close()
        sock = WayfireSocket()
        utils = WayfireUtils(sock)
        stipc = Stipc(sock)
        return sock, utils, stipc

    def on_event_ready(self, fd, condition):
        msg = self.sock.read_next_event()
        if msg is None:
            return True
        if isinstance(msg, dict):  # Check if msg is already a dictionary
            if "event" in msg:
                self.handle_event(msg)
        return True

    def handle_event(self, msg):
        try:
            if msg["event"] == "plugin-activation-state-changed":
                if msg["state"] is True:
                    if msg["plugin"] == "scale":
                        self.is_scale_active[msg["output"]] = True
                if msg["state"] is False:
                    if msg["plugin"] == "scale":
                        self.is_scale_active[msg["output"]] = False
        except Exception as e:
            print(e)
        return True

    def CreateFromAppList(
        self, config, orientation, class_style, callback=None, use_label=False
    ):
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        if orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        box = Gtk.Box(spacing=10, orientation=orientation)

        with open(config, "r") as f:
            config_data = toml.load(f)["dockbar"]

            for app in config_data:
                wclass = None
                initial_title = None

                try:
                    wclass = config_data[app]["wclass"]
                except KeyError:
                    pass

                button = self.create_button(
                    self.get_nearest_icon_name(config_data[app]["icon"]),
                    config_data[app]["cmd"],
                    class_style,
                    wclass,
                    initial_title,
                    use_label,
                )

                if callback is not None:
                    self.create_gesture(button, 3, callback)
                self.append_widget_if_ready(box, button)
                button.add_css_class(class_style)
        return box

    def search_local_desktop(self, initial_title):
        for deskfile in os.listdir(self.webapps_applications):
            if deskfile.startswith(("chrome", "msedge", "FFPWA-")):
                pass
            else:
                continue
            webapp_path = os.path.join(self.webapps_applications, deskfile)
            desktop_file_found = self.search_str_inside_file(
                webapp_path, initial_title.lower()
            )
            if desktop_file_found:
                return deskfile
        return None

    def layer_shell_check(self):
        """Check if gtk4-layer-shell is installed, and install it if not."""
        # Define paths
        install_path = os.path.expanduser("~/.local/lib/gtk4-layer-shell")
        installed_marker = os.path.join(
            install_path, "libgtk_layer_shell.so"
        )  # Adjust if necessary
        temp_dir = "/tmp/gtk4-layer-shell"
        repo_url = "https://github.com/wmww/gtk4-layer-shell.git"
        build_dir = "build"

        # Check if the library is installed
        if os.path.exists(installed_marker):
            print("gtk4-layer-shell is already installed.")
            return

        # Proceed with installation if not installed
        print("gtk4-layer-shell is not installed. Installing...")

        # Create a temporary directory
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Clone the repository
        print("Cloning the repository...")
        subprocess.run(["git", "clone", repo_url, temp_dir], check=True)

        # Change to the repository directory
        os.chdir(temp_dir)

        # Set up the build directory with Meson
        print("Configuring the build environment...")
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

        # Build the project
        print("Building the project...")
        subprocess.run(["ninja", "-C", build_dir], check=True)

        # Install the project
        print("Installing the project...")
        subprocess.run(["ninja", "-C", build_dir, "install"], check=True)

        print("Installation complete.")

    def extract_icon_info(self, application_name):
        icon_name = None

        # Paths to search for desktop files
        search_paths = [
            "/usr/share/applications/",
            os.path.expanduser("~/.local/share/applications/"),
        ]

        # Loop through each search path
        for search_path in search_paths:
            # Check if the search path exists
            if os.path.exists(search_path):
                # Loop through each file in the directory
                for file_name in os.listdir(search_path):
                    if file_name.endswith(".desktop"):
                        file_path = os.path.join(search_path, file_name)
                        with open(file_path, "r") as desktop_file:
                            found_name = False
                            for line in desktop_file:
                                if line.startswith("Name="):
                                    if line.strip().split("=")[1] == application_name:
                                        found_name = True
                                elif found_name and line.startswith("Icon="):
                                    icon_name = line.strip().split("=")[1]
                                    return icon_name

        return icon_name

    def search_desktop(self, wm_class):
        all_apps = Gio.AppInfo.get_all()
        desktop_files = [
            i.get_id().lower() for i in all_apps if wm_class in i.get_id().lower()
        ]
        if desktop_files:
            return desktop_files[0]
        else:
            return None

    def icon_exist(self, argument):
        if argument:
            exist = [
                i.get_icon()
                for i in self.gio_icon_list
                if argument.lower() in i.get_id().lower()
            ]
            if exist:
                if hasattr(exist[0], "get_names"):
                    return exist[0].get_names()[0]
                if hasattr(exist[0], "get_name"):
                    return exist[0].get_name()
            else:
                exist = [name for name in self.icon_names if argument.lower() in name]
                if exist:
                    exist = exist[0]
                    return exist
        return ""

    def dpms_status(self):
        status = check_output(["wlopm"]).decode().strip().split("\n")
        dpms_status = {}
        for line in status:
            line = line.split()
            dpms_status[line[0]] = line[1]
        return dpms_status

    def dpms(self, state, output_name=None):
        if state == "off" and output_name is None:
            outputs = [output["name"] for output in self.sock.list_outputs()]
            for output in outputs:
                call("wlopm --off {}".format(output).split())
        if state == "on" and output_name is None:
            outputs = [output["name"] for output in self.sock.list_outputs()]
            for output in outputs:
                call("wlopm --on {}".format(output).split())
        if state == "on":
            call("wlopm --on {}".format(output_name).split())
        if state == "off":
            call("wlopm --off {}".format(output_name).split())
        if state == "toggle":
            call("wlopm --toggle {}".format(output_name).split())

    def create_taskbar_launcher(
        self,
        wmclass,
        title,
        initial_title,
        orientation,
        class_style,
        view_id,
        callback=None,
    ):
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        title = self.filter_utf_for_gtk(title)
        icon = self.get_icon(wmclass, initial_title, title)

        button = self.create_taskbar_button(title, icon, view_id)
        return button

    def search_str_inside_file(self, file_path, word):
        with open(file_path, "r") as file:
            content = file.read()
            if "name={}".format(word.lower()) in content.lower():
                return True
            else:
                return False

    def get_icon(self, wm_class, initial_title, title):
        title = self.filter_utf_for_gtk(title)
        initial_title = title.split()[0]
        for terminal in self.terminal_emulators:
            if terminal in wm_class and terminal not in title.lower():
                title_icon = self.icon_exist(initial_title)
                if title_icon:
                    return title_icon

        # only works for microsoft edges web apps
        web_apps = {
            "msedge",
            "microsoft-edge",
            "microsoft-edge-dev",
            "microsoft-edge-beta",
        }
        if any(app in wm_class.lower() for app in web_apps):
            desk_local = self.search_local_desktop(initial_title)
            print(desk_local)

            if desk_local and desk_local.endswith("-Default.desktop"):
                if desk_local.startswith("msedge-"):
                    icon_name = desk_local.split(".desktop")[0]
                    return icon_name
            else:
                return self.get_nearest_icon_name("microsoft-edge")

        found_icon = self.icon_exist(wm_class)
        if found_icon:
            return found_icon

        return None

    def list_app_ids(self):
        views = self.sock.list_views()
        return [i["app-id"].lower() for i in views if i["app-id"] != "nil"]

    def create_taskbar_button(self, title, icon_name, view_id):
        if icon_name is None:
            return None

        button = Gtk.Button()

        # Filter title for UTF-8 compatibility
        title = self.filter_utf_for_gtk(title)
        if not title:
            return None

        # Determine title to use based on its length
        use_this_title = title[:30]
        first_word_length = len(title.split()[0])
        if first_word_length > 13:
            use_this_title = title.split()[0]

        # Create a box to hold icon and label
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Add icon if available
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.new_from_icon_name()
            box.append(icon)

        # Add label
        label = Gtk.Label(label=use_this_title)
        box.append(label)

        # Set the box as the button's child
        button.set_child(box)

        # Create gesture handlers for the button
        button.connect("clicked", lambda *_: self.set_view_focus(view_id))
        self.create_gesture(box, 1, lambda *_: self.set_view_focus(view_id))
        self.create_gesture(box, 2, lambda *_: self.sock.close_view(view_id))
        self.create_gesture(
            box, 3, lambda *_: self.wf_utils.move_view_to_empty_workspace(view_id)
        )

        return button

    def focus_view_when_ready(self, view):
        """this function is meant to be used with GLib timeout or idle_add"""
        if view["role"] == "toplevel" and view["focusable"] is True:
            self.sock.set_focus(view["id"])
            return False  # Stop idle processing
        return True  # Continue idle processing

    def move_view_to_empty_workspace(self, view_id):
        ws = self.wf_utils.get_active_workspace()
        if ws:
            x, y = ws.values()
            self.sock.set_workspace(x, y, view_id)

    def normalize_icon_name(self, app_id):
        if "." in app_id:
            return app_id.split(".")[-1]  # Extract the last part
        return app_id

    # this function is useful because it will handle icon_name and icon_path
    def handle_icon_for_button(self, view, button):
        title = view["title"]
        initial_title = title.split()[0]
        wmclass = view["app-id"]
        icon_path = self.get_icon(wmclass, title, initial_title)
        if icon_path:
            print(icon_path)
            if icon_path.startswith("/"):
                try:
                    image = Gtk.Image.new_from_file(icon_path)
                    button.set_image(image)
                    if image is not None and isinstance(image, Gtk.Image):
                        button.set_image(image)
                        button.set_always_show_image(True)
                    else:
                        print("Error: Invalid image provided")
                except Exception as e:
                    print(f"Error loading icon from file: {e}")
                    button.set_icon_name("default-icon-name")
            else:
                button.set_icon_name(icon_path)
        else:
            button.set_icon_name("default-icon-name")

    def find_icon_for_app_id(self, app_id):
        app_id = app_id.lower()
        app_list = Gio.AppInfo.get_all()
        normalized_app_id = self.normalize_icon_name(app_id)
        for app in app_list:
            app_info_id = app.get_id().lower()
            if app_info_id and (
                app_info_id.startswith(normalized_app_id)
                or normalized_app_id in app_info_id
            ):
                icon = app.get_icon()
                if icon:
                    if isinstance(icon, Gio.ThemedIcon):
                        icon_names = icon.get_names()
                        return icon_names[0] if icon_names else None
                    elif isinstance(icon, Gio.FileIcon):
                        return icon.get_file().get_path()
        return None

    def find_icon(self, app_id):
        return self.find_icon_for_app_id(app_id)

    async def get_steam_game_pic(self, game_title):
        REQUEST_TIMEOUT = 10  # seconds
        search_url = "https://store.steampowered.com/search/"
        params = {"term": game_title}

        # Set timeout for the session
        timeout = ClientTimeout(total=REQUEST_TIMEOUT)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(search_url, params=params) as response:
                    if response.status != 200:
                        print("Failed to retrieve search results.")
                        return None

                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    results = soup.find_all("a", href=True, class_="search_result_row")

                    if not results:
                        print("Game not found.")
                        return None

                    # Assume the first result is the desired game
                    game_url = results[0]["href"]

                    try:
                        async with session.get(game_url) as game_response:
                            if game_response.status != 200:
                                print("Failed to retrieve game page.")
                                return None

                            game_text = await game_response.text()
                            game_soup = BeautifulSoup(game_text, "html.parser")

                            # Find the image URL
                            img_tag = game_soup.find(
                                "img", {"class": "game_header_image_full"}
                            )
                            if img_tag and img_tag["src"]:
                                return img_tag["src"]
                            else:
                                print("Image not found.")
                                return None
                    except asyncio.TimeoutError:
                        print("Timed out while retrieving game page.")
                        return None
            except asyncio.TimeoutError:
                print("Timed out while retrieving search results.")
                return None
            except aiohttp.ClientError as e:
                print(f"HTTP error occurred: {e}")
                return None

    async def main_get_steam_game_image(self, game_title):
        image_url = await self.get_steam_game_pic(game_title)
        if image_url:
            return image_url

    def get_game_image(self, game_title):
        asyncio.run(self.main_get_steam_game_image(game_title))

    async def download_image(self, url, filename):
        cache_dir = os.path.expanduser("~/.cache")
        os.makedirs(cache_dir, exist_ok=True)
        file_path = os.path.join(cache_dir, filename)
        timeout = ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        print("Failed to download image.")
                        return None

                    with open(file_path, "wb") as file:
                        file.write(await response.read())

                    return file_path
            except asyncio.TimeoutError:
                print("Timed out while downloading image.")
                return None
            except aiohttp.ClientError as e:
                print(f"HTTP error occurred: {e}")
                return None

    def get_wayfire_pid(self):
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                try:
                    with open(f"/proc/{entry}/comm", "r") as comm_file:
                        command_name = comm_file.read().strip()
                        if "wayfire" in command_name:
                            return entry
                except IOError:
                    continue
        return None

    def list_libs_in_process(self, pid):
        libs = []
        maps_file = f"/proc/{pid}/maps"

        try:
            with open(maps_file, "r") as f:
                for line in f:
                    if "so" in line:
                        lib_path = line.split()[-1]
                        if os.path.isfile(lib_path) and lib_path not in libs:
                            libs.append(lib_path)
        except FileNotFoundError:
            pass

        return libs

    def check_lib_in_wayfire(self, lib_name):
        pid = self.get_wayfire_pid()
        if not pid:
            print("Wayfire process not found.")
            return False

        libs = self.list_libs_in_process(pid)
        for lib in libs:
            if lib_name in lib:
                return True

        return False

    def find_wayfire_lib(self, lib_name):
        if self.check_lib_in_wayfire(lib_name):
            return True
        else:
            return False

    def get_audio_apps_with_titles(self):
        """Retrieve audio applications along with their titles."""
        try:
            # Get sink inputs from PulseAudio
            pactl_output = subprocess.run(
                ["pactl", "list", "sink-inputs"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            ).stdout
            # Parse sink inputs
            apps = []
            current_app = {}
            for line in pactl_output.splitlines():
                if line.startswith("Sink Input #"):
                    if current_app:
                        apps.append(current_app)
                        current_app = {}
                elif "=" in line:
                    key, value = map(str.strip, line.split("=", 1))
                    current_app[key] = value.strip('"')
            if current_app:
                apps.append(current_app)
            # Get window titles using wmctrl
            try:
                wmctrl_output = subprocess.run(
                    ["wmctrl", "-lp"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                ).stdout
                # Create PID to window title mapping
                pid_to_windows = defaultdict(list)
                for wm_line in wmctrl_output.splitlines():
                    parts = wm_line.split(maxsplit=4)
                    if len(parts) >= 5:
                        pid = parts[2]
                        title = parts[4]
                        pid_to_windows[pid].append(title)
            except:
                pid_to_windows = {}
            # Prepare the result list
            result = []
            for app in apps:
                pid = app.get("application.process.id")
                if not pid:
                    continue
                # Try to get the best available title in this order:
                # 1. Media title (song/video name)
                # 2. Window title
                # 3. Application name
                title = (
                    app.get("media.name")
                    or app.get("xesam:title")
                    or (
                        pid_to_windows.get(pid, [""])[0]
                        if pid in pid_to_windows
                        else ""
                    )
                    or app.get("application.name", "")
                )
                if title:  # Only include if we found a title
                    result.append({pid: title})
            return result
        except subprocess.CalledProcessError as e:
            print(f"Error running command: {e.stderr}")
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
            return []

    def get_default_monitor_name(self, config_file_path):
        try:
            with open(config_file_path, "r") as file:
                config = toml.load(file)
                if "monitor" in config:
                    return config["monitor"].get("name")
                else:
                    return None
        except FileNotFoundError:
            print(f"Config file '{config_file_path}' not found.")
            return None

    def view_focus_indicator_effect(self, view_id):
        precision = 1
        values = np.arange(0.1, 1, 0.1)
        float_sequence = [round(value, precision) for value in values]
        original_alpha = self.sock.get_view_alpha(view_id)["alpha"]
        for f in float_sequence:
            try:
                self.sock.set_view_alpha(view_id, f)
                sleep(0.02)
            except Exception as e:
                print(e)
        self.sock.set_view_alpha(view_id, original_alpha)

    def is_view_valid(self, view_id):
        views = [i["id"] for i in self.sock.list_views()]
        if view_id not in views:
            return
        view = self.sock.get_view(view_id)
        if view["role"] != "toplevel":
            return False
        if view["pid"] == -1:
            return False
        if view["app-id"] == "" or view["app-id"] == "nil":
            return False
        return self.sock.get_view(view_id)

    def set_view_focus(self, view_id):
        try:
            view = self.is_view_valid(view_id)

            if not view:
                return

            view_id = view["id"]
            output_id = view["output-id"]

            # sometimes the view is so small that we should resize it
            viewgeo = self.wf_utils.get_view_geometry(view_id)
            if viewgeo:
                if viewgeo["width"] < 100 or viewgeo["height"] < 100:
                    self.sock.configure_view(
                        view_id, viewgeo["x"], viewgeo["y"], 400, 400
                    )

            if output_id in self.is_scale_active:
                if self.is_scale_active[output_id] is True:
                    self.sock.scale_toggle()
                    # FIXME: better get animation speed from the conf so define a proper sleep
                    # sleep(0.4)
                    self.wf_utils.go_workspace_set_focus(view_id)
                    self.wf_utils.center_cursor_on_view(view_id)
                else:
                    self.wf_utils.go_workspace_set_focus(view_id)
                    self.wf_utils.center_cursor_on_view(view_id)
            else:
                self.wf_utils.go_workspace_set_focus(view_id)
                self.wf_utils.center_cursor_on_view(view_id)
                self.view_focus_indicator_effect(view_id)

        except Exception as e:
            print(e)
            return True

    def file_exists(self, path):
        return os.path.isfile(path)

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        config_paths = self.setup_config_paths()
        # Set instance variables from the dictionary
        self.home = config_paths["home"]
        self.webapps_applications = os.path.join(self.home, ".local/share/applications")
        self.scripts = config_paths["scripts"]
        self.config_path = config_paths["config_path"]
        self.style_css_config = config_paths["style_css_config"]
        self.window_notes_config = config_paths["window_notes_config"]
        self.cache_folder = config_paths["cache_folder"]

    def setup_config_paths(self):
        home = os.path.expanduser("~")
        full_path = os.path.abspath(__file__)
        directory_path = os.path.dirname(full_path)
        # Get the parent directory, waypane/src will go for waypanel
        directory_path = os.path.dirname(directory_path)
        self.waypanel_cfg = os.path.join(home, ".config/waypanel/waypanel.toml")
        # Initial path setup
        scripts = os.path.join(home, ".config/waypanel/scripts")
        if not self.file_exists(scripts):
            scripts = "../config/scripts"

        config_path = os.path.join(home, ".config/waypanel")

        style_css_config = os.path.join(config_path, "style.css")
        if not self.file_exists(style_css_config):
            style_css_config = os.path.join(directory_path, "config/style.css")

        window_notes_config = os.path.join(config_path, "window-config.toml")
        if not self.file_exists(window_notes_config):
            window_notes_config = os.path.join(
                directory_path, "config/window-config.toml"
            )

        cache_folder = os.path.join(home, ".cache/waypanel")

        if not os.path.exists(config_path):
            os.makedirs(config_path)
            os.makedirs(scripts)

        return {
            "home": home,
            "scripts": scripts,
            "config_path": config_path,
            "style_css_config": style_css_config,
            "window_notes_config": window_notes_config,
            "cache_folder": cache_folder,
        }

    def filter_utf_for_gtk(self, byte_string):
        """
        Safely decode a byte string to UTF-8, handling all encoding issues, with priority to UTF-8.

        Args:
            byte_string (bytes or str): The input byte string to be filtered.

        Returns:
            str: The decoded string with invalid characters replaced or ignored.
        """
        if isinstance(byte_string, str):
            return byte_string

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

            # Try UTF-8 first
            try:
                return byte_string.decode("utf-8", errors="replace")
            except UnicodeDecodeError as e:
                print(f"UTF-8 decoding error: {e}")

            # Try other UTF encodings if UTF-8 fails
            for encoding in encodings[1:]:  # Skip 'utf-8' as it's already tried
                try:
                    return byte_string.decode(encoding, errors="replace")
                except UnicodeDecodeError as e:
                    print(f"{encoding} decoding error: {e}")

            # If all UTF decoding attempts fail, fallback to a last-resort encoding like 'latin-1'
            print("All UTF decoding attempts failed, falling back to 'latin-1'.")
            return byte_string.decode("latin-1", errors="replace")

        raise TypeError("Input must be a bytes object or a string.")

    def create_button(
        self,
        icon_name,
        cmd,
        Class_Style,
        wclass,
        initial_title=None,
        use_label=False,
        use_function=False,
    ):
        # Create the button
        button = Gtk.Button()
        assert button is not None, "Button creation failed"

        # Create content box
        box = Gtk.Box()

        # Add icon or label
        if use_label:
            label = Gtk.Label(label=icon_name)
            box.append(label)
        else:
            if icon_name:  # Only add icon if name is provided
                icon = Gtk.Image.new_from_icon_name(icon_name)
                box.append(icon)

        # Set content
        button.set_child(box)

        # If cmd is NULL, disable the button
        if cmd == "NULL":
            button.set_sensitive(False)
            return button

        # Set up click handling - LEFT CLICK
        if use_function:
            button.connect("clicked", lambda *_: use_function())
        else:
            button.connect("clicked", lambda *_: self.run_cmd(cmd))

        # Set up gesture for RIGHT CLICK (button 3)
        self.create_gesture(box, 3, lambda *_: self.dockbar_remove(icon_name))

        button.add_css_class(Class_Style)
        return button

    # Remove a command from the dockbar configuration
    def dockbar_remove(self, cmd):
        with open(self.waypanel_cfg, "r") as f:
            config = toml.load(f)
        del config[cmd]
        with open(self.waypanel_cfg, "w") as f:
            toml.dump(config, f)

    def load_topbar_config(self):
        with open(self.waypanel_cfg, "r") as f:
            return toml.load(f)

    def create_gesture(self, widget, mouse_button, callback, arg=None):
        gesture = Gtk.GestureClick.new()
        if arg is None:
            gesture.connect("released", callback)
        else:
            gesture.connect("released", lambda gesture, arg=arg: callback(arg))
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        self.gestures[widget] = gesture
        return widget

    def remove_gesture(self, widget):
        if widget in self.gestures:
            gesture = self.gestures[widget]
            widget.remove_controller(gesture)
            del self.gestures[widget]

    def convert_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return "%s %s" % (s, size_name[i])

    def btn_background(self, class_style, icon_name):
        tbtn_title_b = Adw.ButtonContent()
        tbtn_title_b.set_icon_name(icon_name)
        return tbtn_title_b
