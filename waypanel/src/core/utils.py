import os
import math
import gi
from waypanel.src.core.background import *
import numpy as np
from time import sleep
import subprocess
from gi.repository import Gtk, Adw, Gio, Gdk
from subprocess import Popen
from subprocess import check_output
import toml
from wayfire.ipc import WayfireSocket

from wayfire.ipc import *

from wayfire.extra.ipc_utils import WayfireUtils
import shlex
from subprocess import call
from wayfire.extra.stipc import Stipc



gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


class Utils(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._setup_config_paths()
        self.psutil_store = {}
        self.panel_cfg = self.load_topbar_config()
        self.icon_names = [icon for icon in Gtk.IconTheme().get_icon_names()]
        self.gio_icon_list = Gio.AppInfo.get_all()
        self.gestures = {}
        self.sock = WayfireSocket()
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
            "rxvt"
        ]
        self.start_thread_compositor()

    def run_app(self, cmd, wclass=None, initial_title=None, cmd_mode=True):
        if [c for c in self.terminal_emulators if cmd in c] and cmd_mode:
            try:
                Popen(cmd.split(), start_new_session=True)
            except Exception as e:
                print(e)
            return
        if ";" in cmd:
            for c in cmd.split(";"):
                try:
                    Popen(c.split(), start_new_session=True)
                except Exception as e:
                    print(e)
        else:
            try:
                Popen(cmd.split(), start_new_session=True)
            except Exception as e:
                print(e)

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
        command = shlex.split(command)
        Popen(command)

    def widget_exists(self, widget):
        return widget is not None and isinstance(widget, Gtk.Widget)

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

                button = self.CreateButton(
                    config_data[app]["icon"],
                    config_data[app]["cmd"],
                    class_style,
                    wclass,
                    initial_title,
                    use_label,
                )

                if callback is not None:
                    self.create_gesture(button, 3, callback)

                box.append(button)

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

    def get_workspaces_with_views(self):
        focused_output = self.sock.get_focused_output()
        monitor = focused_output["geometry"]
        ws_with_views = []
        views = self.wf_utils.focused_output_views()

        if views:
            views = [
                view for view in views
                if view["role"] == "toplevel" and not view["minimized"] and view["app-id"] != "nil" and view["pid"] > 0
            ]

            if views:
                grid_width = focused_output["workspace"]["grid_width"]
                grid_height = focused_output["workspace"]["grid_height"]
                current_ws_x = focused_output["workspace"]["x"]
                current_ws_y = focused_output["workspace"]["y"]

                for ws_x in range(grid_width):
                    for ws_y in range(grid_height):
                        for view in views:
                            if self.wf_utils.view_visible_on_workspace(
                                view["geometry"],
                                ws_x - current_ws_x,
                                ws_y - current_ws_y,
                                monitor
                            ):
                                ws_with_views.append({"x": ws_x, "y": ws_y, "view-id": view["id"]})
                return ws_with_views
        return []


    def go_next_workspace_with_views(self):
        workspaces = self.get_workspaces_with_views()
        if not workspaces:
            return

        active_workspace = self.sock.get_focused_output()["workspace"]
        active_workspace = {"x": active_workspace["x"], "y": active_workspace["y"]}

        next_ws = self.wf_utils.get_next_workspace(workspaces, active_workspace)
        if next_ws:
            self.sock.set_workspace(next_ws)

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
        self.utils.run_app(config["take_note_app"]["cmd"])



    def CreateFromAppList(
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

                button = self.CreateButton(
                    config_data[app]["icon"],
                    config_data[app]["cmd"],
                    class_style,
                    wclass,
                    initial_title,
                    use_label,
                )

                if callback is not None:
                    self.create_gesture(button, 3, callback)

                box.append(button)

        return box

    def on_compositor_finished(self):
        try:
            self.watch_task.finish()
        except Exception as err:
            print(err)

    def start_thread_compositor(self):
        self.watch_task = Background(self.watch_events, self.on_compositor_finished)
        self.watch_task.start()

    def compositor_window_changed(self):
        pass

    def watch_events(self):
        sock = WayfireSocket()
        sock.watch()
        while True:
            try:
                msg = sock.read_message()
                if "event" in msg:
                    if msg["event"] == "plugin-activation-state-changed":
                        if msg["state"] is True:
                            if msg["plugin"] == "scale":
                                self.is_scale_active[msg["output"]] = True
                        if msg["state"] is False:
                            if msg["plugin"] == "scale":
                                self.is_scale_active[msg["output"]] = False
            except Exception as e:
                print(e)

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
        install_path = os.path.expanduser('~/.local/lib/gtk4-layer-shell')
        installed_marker = os.path.join(install_path, 'libgtk_layer_shell.so')  # Adjust if necessary
        temp_dir = '/tmp/gtk4-layer-shell'
        repo_url = 'https://github.com/wmww/gtk4-layer-shell.git'
        build_dir = 'build'
        
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
        subprocess.run(['git', 'clone', repo_url, temp_dir], check=True)
        
        # Change to the repository directory
        os.chdir(temp_dir)
        
        # Set up the build directory with Meson
        print("Configuring the build environment...")
        subprocess.run(['meson', 'setup', f'--prefix={install_path}', '-Dexamples=true', '-Ddocs=true', '-Dtests=true', build_dir], check=True)
        
        # Build the project
        print("Building the project...")
        subprocess.run(['ninja', '-C', build_dir], check=True)
        
        # Install the project
        print("Installing the project...")
        subprocess.run(['ninja', '-C', build_dir, 'install'], check=True)
        
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
            outputs = [output["name"] for output in self.list_outputs()]
            for output in outputs:
                call("wlopm --off {}".format(output).split())
        if state == "on" and output_name is None:
            outputs = [output["name"] for output in self.list_outputs()]
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
        title = self.filter_utf8_for_gtk(title)
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        icon = self.get_icon(wmclass, initial_title, title)

        button = self.create_clickable_image(
            icon, class_style, wmclass, title, initial_title, view_id
        )
        return button

    def search_str_inside_file(self, file_path, word):
        with open(file_path, "r") as file:
            content = file.read()
            if "name={}".format(word.lower()) in content.lower():
                return True
            else:
                return False

    def get_icon(self, wm_class, initial_title, title):
        title = self.filter_utf8_for_gtk(title)
        for terminal in self.terminal_emulators:
            if terminal in wm_class and terminal not in title.lower():
                title_icon = self.icon_exist(initial_title)
                if title_icon:
                    return title_icon

        web_apps = {
            "chromium",
            "microsoft-edge",
            "microsoft-edge-dev",
            "microsoft-edge-beta",
        }
        if any(app in wm_class.lower() for app in web_apps):
            desk_local = self.search_local_desktop(initial_title)

            if desk_local and desk_local.endswith("-Default.desktop"):
                if desk_local.startswith("msedge-") or desk_local.startswith("chrome-"):
                    icon_name = desk_local.split(".desktop")[0]
                    return icon_name

        found_icon = self.icon_exist(wm_class)
        if found_icon:
            return found_icon

        return ""

    # FIXME: panel will crash if started app has some random errors in output
    # that means, the panels bellow will be always on top and no clickable anymore
    # example of apps with errors, nautilus, element, chromium etc.
    def create_clickable_image(
        self, icon_name, class_style, wclass, title, initial_title, view_id
    ):
        # this is creating empty box in case you can't find any app-id
        if wclass == "nil":
            return Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=6)

        # no pid no new taskbar button, that will crash the panel
        pid = self.wf_utils.get_view_pid(view_id)
        if pid == -1:
            return

        title = self.filter_utf8_for_gtk(title)
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=6)
        if class_style is not None:
            box.add_css_class(class_style)

        output_name = self.wf_utils.get_view_output_name(view_id)
        default_output = self.get_default_monitor_name(self.topbar_config)

        use_this_title = title[:30]

        first_word_length = len(title.split()[0])
        if first_word_length > 13:
            use_this_title = title.split()[0]

        if output_name != default_output:
            use_this_title = "({0}) {1}".format(output_name, use_this_title)
        label = Gtk.Label.new(use_this_title)
        label.add_css_class("label_from_clickable_image")

        if isinstance(icon_name, Gio.FileIcon):
            # If icon_name is a FileIcon object, directly use it
            image = Gtk.Image.new_from_gicon(icon_name)
        else:
            # Otherwise, treat icon_name as a string representing the icon name
            dock_icon = self.find_dock_icon(wclass)
            if dock_icon:
                image = Gtk.Image.new_from_icon_name(dock_icon)
            else:
                image = Gtk.Image.new_from_icon_name(icon_name)

        image.props.margin_end = 5
        image.set_halign(Gtk.Align.END)
        image.add_css_class("icon_from_clickable_image")

        box.append(image)
        box.append(label)
        box.add_css_class("box_from_clickable_image")

        self.create_gesture(box, 1, lambda *_: self.set_view_focus(view_id))
        self.create_gesture(box, 2, lambda *_: self.wf_utils.close_view(view_id))
        self.create_gesture(box, 3, lambda *_: self.set_view_active_workspace(view_id))

        return box

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

    def set_view_active_workspace(self, view_id):
        self.wf_utils.scale_toggle()
        active_workspace = self.wf_utils.get_active_workspace()
        output_id = self.wf_utils.get_focused_output_id()
        self.wf_utils.set_workspace(active_workspace, view_id=view_id, output_id=output_id)

    def close_view(self, view_id):
        self.wf_utils.close_view(view_id)

    def view_focus_indicator_effect(self, view_id):
        precision = 1
        values = np.arange(0.1, 1, 0.1)
        float_sequence = [round(value, precision) for value in values]
        original_alpha = self.sock.get_view_alpha(view_id)["alpha"]
        for f in float_sequence:
            try:
                self.wf_utils.set_view_alpha(view_id, f)
                sleep(0.04)
            except Exception as e:
                print(e)
        self.wf_utils.set_view_alpha(view_id, original_alpha)

    def set_view_focus(self, view_id):
        try:
            view = self.sock.get_view(view_id)
            if view is None:
                return

            # why foucs an app with no app-id
            if view["app-id"] == "nil":
                return

            view_id = view["id"]
            output_id = view["output-id"]

            if output_id in self.is_scale_active:
                # there is an issue depending on the scale animation duration
                # the panel will freeze while the layzer shell will keep on top of the views because it enter in a infinite recursion
                # the conflict happens with go_workspace_set_focus while the animation of scale is still happening
                # another issue with scale is, if you enable close on new views option it will close faster than you set layer on bottom
                # thus will produce the same kind of issue
                if self.is_scale_active[output_id] is True:
                    self.sock.scale_toggle()
                    # FIXME: better get animation speed from the conf so define a proper sleep
                    sleep(0.2)
                    self.wf_utils.go_workspace_set_focus(view_id)
                    self.move_cursor_middle(view_id)
                else:
                    self.wf_utils.go_workspace_set_focus(view_id)
                    self.move_cursor_middle(view_id)
            else:
                self.wf_utils.go_workspace_set_focus(view_id)
                self.move_cursor_middle(view_id)
                #self.wf_utils.view_focus_indicator_effect(view_id)

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
        self.dockbar_config = config_paths["dockbar_config"]
        self.style_css_config = config_paths["style_css_config"]
        self.workspace_list_config = config_paths["workspace_list_config"]
        self.topbar_config = config_paths["topbar_config"]
        self.menu_config = config_paths["menu_config"]
        self.window_notes_config = config_paths["window_notes_config"]
        self.cmd_config = config_paths["cmd_config"]
        self.topbar_launcher_config = config_paths["topbar_launcher_config"]
        self.cache_folder = config_paths["cache_folder"]

    def setup_config_paths(self):
        home = os.path.expanduser("~")
        full_path = os.path.abspath(__file__)
        directory_path = os.path.dirname(full_path)
        # Get the parent directory, waypane/src will go for waypanel
        directory_path = os.path.dirname(directory_path)

        # Initial path setup
        scripts = os.path.join(home, ".config/waypanel/scripts")
        if not self.file_exists(scripts):
            scripts = "../config/scripts"

        config_path = os.path.join(home, ".config/waypanel")

        dockbar_config = os.path.join(config_path, "dockbar.toml")
        if not self.file_exists(dockbar_config):
            dockbar_config = os.path.join(directory_path, "config/dockbar.toml")

        style_css_config = os.path.join(config_path, "style.css")
        if not self.file_exists(style_css_config):
            style_css_config = os.path.join(directory_path, "config/style.css")

        workspace_list_config = os.path.join(config_path, "workspacebar.toml")
        if not self.file_exists(workspace_list_config):
            workspace_list_config = os.path.join(directory_path, "config/workspacebar.toml")

        topbar_config = os.path.join(config_path, "panel.toml")
        if not self.file_exists(topbar_config):
            topbar_config = os.path.join(directory_path, "config/panel.toml")

        menu_config = os.path.join(config_path, "menu.toml")
        if not self.file_exists(menu_config):
            menu_config = os.path.join(directory_path, "config/menu.toml")

        window_notes_config = os.path.join(config_path, "window-config.toml")
        if not self.file_exists(window_notes_config):
            window_notes_config = os.path.join(directory_path, "config/window-config.toml")

        cmd_config = os.path.join(config_path, "cmd.toml")
        if not self.file_exists(cmd_config):
            cmd_config = os.path.join(directory_path, "config/cmd.toml")

        topbar_launcher_config = os.path.join(config_path, "topbar-launcher.toml")
        if not self.file_exists(topbar_launcher_config):
            topbar_launcher_config = os.path.join(directory_path, "config/topbar-launcher.toml")

        cache_folder = os.path.join(home, ".cache/waypanel")
        
        if not os.path.exists(config_path):
            os.makedirs(config_path)
            os.makedirs(scripts)

        return {
            "home": home,
            "scripts": scripts,
            "config_path": config_path,
            "dockbar_config": dockbar_config,
            "style_css_config": style_css_config,
            "workspace_list_config": workspace_list_config,
            "topbar_config": topbar_config,
            "menu_config": menu_config,
            "window_notes_config": window_notes_config,
            "cmd_config": cmd_config,
            "topbar_launcher_config": topbar_launcher_config,
            "cache_folder": cache_folder
        }

    def filter_utf8_for_gtk(self, byte_string, encoding="utf-8"):
        if isinstance(byte_string, str):
            return byte_string  # For Python 3, assume the string is already decoded
        try:
            decoded_text = byte_string.decode(encoding)
        except AttributeError:
            decoded_text = byte_string.decode(encoding, errors="ignore")
        return decoded_text

    def CreateButton(
        self,
        icon_name,
        cmd,
        Class_Style,
        wclass,
        initial_title=None,
        use_label=False,
        use_function=False,
    ):
        box = Gtk.Box(spacing=2)
        box.add_css_class(Class_Style)
        box.set_can_focus(False)
        box.set_focusable(False)
        box.set_focus_on_click(False)
        button = Adw.ButtonContent()
        button.set_can_focus(False)
        button.set_focusable(False)
        button.set_focus_on_click(False)
        if use_label:
            button.set_label(icon_name)
        else:
            button.add_css_class("hvr-grow")
            button.set_icon_name(icon_name)

        button.add_css_class("{}-button".format(Class_Style))
        if cmd == "NULL":
            button.set_sensitive(False)
            return button
        if use_function is False:
            self.create_gesture(button, 1, lambda *_: self.run_cmd(cmd))
            self.create_gesture(button, 3, lambda *_: self.dockbar_remove(icon_name))
        else:
            self.create_gesture(button, 1, use_function)

        return button

    def load_topbar_config(self):
        with open(self.topbar_config, "r") as f:
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
