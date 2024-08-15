import os
import toml
import gi
import json
from subprocess import Popen, call, check_output as out
from collections import ChainMap
from waypanel.src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell
from gi.repository import Gtk, Adw, GLib, Gio, GObject, Gio
from ..core.create_panel import (
    CreatePanel,
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)
from ..core.utils import Utils
import numpy as np
import sys
from waypanel.src.core.background import *
from wayfire.ipc import WayfireSocket
from  wayfire.extra.ipc_utils import WayfireUtils


sys.path.append("/usr/lib/waypanel/")


class Dockbar(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.utils = Utils()
        self.psutil_store = {}
        self.panel_cfg = self.utils.load_topbar_config()
        self.taskbar_list = [None]
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.all_pids = [i["id"] for i in self.sock.list_views()]
        self.timeout_taskbar = None
        self.buttons_id = {}
        self.has_taskbar_started = False
        self.stored_windows = []
        self.window_created_now = None
        self.is_scale_active = {}
        self._setup_config_paths()


    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        config_paths = self.utils.setup_config_paths()
        
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

    # Start the Dockbar application
    def do_start(self):
        self.start_thread_compositor()
        self.stored_windows = [i["id"] for i in self.sock.list_views()]

        # Read configuration from topbar toml
        with open(self.topbar_config, "r") as f:
            panel_toml = toml.load(f)

            for p in panel_toml:
                if "left" == p:
                    exclusive = panel_toml[p]["Exclusive"] == "True"
                    position = panel_toml[p]["position"]

                    # Create a left panel and associated components
                    self.left_panel = CreatePanel(
                        self, "LEFT", position, exclusive, 32, 0, "LeftBar"
                    )
                    self.dockbar = self.utils.CreateFromAppList(
                        self.dockbar_config, "v", "LeftBar", self.join_windows
                    )
                    self.add_launcher = Gtk.Button()
                    self.add_launcher.set_icon_name("tab-new-symbolic")
                    self.add_launcher.connect("clicked", self.dockbar_append)
                    self.dockbar.append(self.add_launcher)
                    self.left_panel.set_content(self.dockbar)
                    self.left_panel.present()

                # if "right" == p:
                #     exclusive = panel_toml[p]["Exclusive"] == "True"
                #     position = panel_toml[p]["position"]
                #     # Create a right panel and associated components
                #     self.right_panel = CreatePanel(
                #         self, "RIGHT", position, exclusive, 32, 0, "RightBar"
                #     )
                #     workspace_buttons = self.utils.CreateFromAppList(
                #         self.workspace_list_config, "v", "RightBar", None, True
                #     )
                #     self.right_panel.set_content(workspace_buttons)
                #     # self.right_panel.present()

                if "bottom" == p:
                    print()
                    exclusive = panel_toml[p]["Exclusive"] == "True"
                    position = panel_toml[p]["position"]

                    # Create a bottom panel and associated components
                    self.bottom_panel = CreatePanel(
                        self, "BOTTOM", position, exclusive, 32, 0, "BottomBar"
                    )
                    self.add_launcher = Gtk.Button()
                    self.add_launcher.set_icon_name("tab-new-symbolic")
                    self.add_launcher.connect("clicked", self.dockbar_append)
                    self.taskbar = Gtk.Box()
                    self.taskbar.append(self.add_launcher)
                    self.taskbar.add_css_class("taskbar")
                    self.bottom_panel.set_content(self.taskbar)
                    self.bottom_panel.present()

                    # Start the taskbar list for the bottom panel
                    # Remaining check pids will be handled later
                    self.Taskbar("h", "taskbar")

            # LayerShell.set_layer(self.left_panel, LayerShell.Layer.TOP)
            # LayerShell.set_layer(self.bottom_panel, LayerShell.Layer.TOP)

    def on_compositor_finished(self):
        # non working code
        try:
            self.taskbarwatch_task.finish()
        except Exception as err:
            print(err)

    def start_thread_compositor(self):
        self.taskbarwatch_task = Background(
            self.TaskbarWatch, lambda: self.on_compositor_finished
        )
        self.taskbarwatch_task.start()

    def compositor_window_changed(self):
        # if no windows, window_created signal will conflict with window_changed
        # the issue will be no new button will be appended to the taskbar
        # necessary to check if the window list is empity
        # if not len(self.hyprinstance.get_windows()) == 0:
        # self.update_active_window_shell()
        print()

    def file_exists(self, full_path):
        return os.path.exists(full_path)

    def handle_view_event(self, msg, view):
        if "event" not in msg:
            return

        if msg["event"] == "view-unmapped":
            self.on_view_destroyed(view)

        if view is None:
            return

        if view["pid"] == -1:
            return

        if "role" not in view:
            return

        if view["role"] != "toplevel":
            return

        if view["app-id"] == "":
            return

        if view["app-id"] == "nil":
            return

        if msg["event"] == "view-title-changed":
            self.on_title_changed(view)

        if msg["event"] == "view-tiled" and view:
            if self.wf_utils.is_view_maximized(view["id"]):
                self.was_last_focused_view_maximized = True

        if msg["event"] == "app-id-changed":
            self.on_app_id_changed(msg["view"])

        if msg["event"] == "view-focused":
            self.on_view_role_toplevel_focused(view)
            self.on_view_focused()
            self.last_focused_output = view["output-id"]

        if msg["event"] == "view-mapped":
            self.on_view_created(view)

        if msg["event"] == "view-unmapped":
            self.on_view_destroyed(msg["view"])

        if msg["event"] == "view-wset-changed":
            self.update_taskbar(view)

    def handle_plugin_event(self, msg):
        if "event" not in msg:
            return
        if msg["event"] == "plugin-activation-state-changed":
            if msg["state"]:
                if msg["plugin"] == "expo":
                    self.on_expo_activated()
                if msg["plugin"] == "scale":
                    self.on_scale_activated()
                if msg["plugin"] == "move":
                    self.on_moving_view()
            else:
                if msg["plugin"] == "expo":
                    self.on_expo_desactivated()
                if msg["plugin"] == "scale":
                    self.on_scale_desactivated()

    def TaskbarWatch(self):
        # evets should ever stop, if it breaks the loop
        # lets start a new one
        while True:
            try:
                # FIXME: create a file dedicated for watching events
                sock = WayfireSocket()
                sock.watch()
                view = None
                while True:
                    try:
                        msg = sock.read_message()
                        if "view" in msg:
                            view = msg["view"]

                        if "event" in msg:
                            self.handle_view_event(msg, view)
                            self.handle_plugin_event(msg)
                            if msg["event"] == "view-geometry-changed":
                                if "view" in msg:
                                    view = msg["view"]
                                    if view["layer"] != "workspace":
                                        self.taskbar_remove(view["id"])


                    except Exception as e:
                        print(e)
            except Exception as e:
                print(e)

    def on_view_role_toplevel_focused(self, view):
        return

    def on_expo_activated(self):
        return

    def on_expo_desactivated(self):
        return

    def on_view_focused(self):
        return

    def on_app_id_changed(self, view):
        self.update_taskbar_list()
        self.new_taskbar_view("h", "taskbar", view["id"])

    # events that will make the panel clickable or not
    def on_scale_activated(self):
        set_layer_position_exclusive(self.left_panel)
        # set_layer_position_exclusive(self.right_panel)
        set_layer_position_exclusive(self.bottom_panel)
        return

    def on_scale_desactivated(self):
        unset_layer_position_exclusive(self.left_panel)
        # unset_layer_position_exclusive(self.right_panel)
        unset_layer_position_exclusive(self.bottom_panel)
        return

    def on_view_created(self, view):
        self.update_taskbar_list()
        self.new_taskbar_view("h", "taskbar", view["id"])

    def on_view_destroyed(self, view):
        self.update_taskbar_list()

    def on_view_wset_changed(self, view):
        self.update_taskbar(view)

    def on_title_changed(self, view):
        self.update_taskbar(view)


    def get_default_monitor_name(self):
        try:
            with open(self.topbar_config, "r") as file:
                config = toml.load(file)
                if "monitor" in config:
                    return config["monitor"].get("name")
                else:
                    return None
        except FileNotFoundError:
            return None

    def update_taskbar(self, view):
        title = self.utils.filter_utf8_for_gtk(view["title"])
        title = title[:20]

        first_word_length = len(title.split()[0])
        if first_word_length > 10:
            title = title.split()[0]

        initial_title = title.split()[0]
        icon = self.utils.get_icon(view["app-id"], initial_title, title)
        button = self.buttons_id[view["id"]][0]
        image = button.get_first_child()
        label = button.get_last_child()
        if icon:
            if isinstance(icon, Gio.FileIcon):
                image.set_from_gicon(icon)
            else:
                image.set_from_icon_name(icon)
        if title:
            output_name = self.wf_utils.get_view_output_name(view["id"])
            default_output = self.get_default_monitor_name()

            if output_name != default_output:
                title = "({0}) {1}".format(output_name, title)
            label.set_label(title)

    def Taskbar(self, orientation, class_style, update_button=False, callback=None):
        # Load configuration from dockbar_config file
        with open(self.dockbar_config, "r") as f:
            config = toml.load(f)

        # Extract desktop_file paths from the configuration
        launchers_desktop_file = [config[i]["desktop_file"] for i in config]

        list_views = self.sock.list_views()
        if not list_views:
            return

        for i in list_views:
            self.new_taskbar_view(orientation,class_style, i["id"])

        # Return True to indicate successful execution of the Taskbar function
        return True

    def new_taskbar_view(
        self,
        orientation,
        class_style,
        view_id,
        callback=None,
    ):
        if not class_style:
            class_style = "taskbar"
        if not self.id_exist(view_id):
            return
        if view_id in self.taskbar_list:
            return
        view = self.sock.get_view(view_id)
        if view["type"] != "toplevel":
            return
        if view["layer"] == "background":
            return
        id = view["id"]
        title = view["title"]
        title = self.utils.filter_utf8_for_gtk(title)
        wm_class = view["app-id"]
        initial_title = title.split(" ")[0].lower()
        button = self.utils.create_taskbar_launcher(
            wm_class, title, initial_title, orientation, class_style, id
        )
        if not self.utils.widget_exists(button):
            return
        # Append the button to the taskbar
        self.taskbar.append(button)

        # Store button information in dictionaries for easy access
        self.buttons_id[id] = [button, initial_title, id]

        self.taskbar_list.append(id)

        return True

    def pid_exist(self, id):
        pid = self.wf_utils.get_view_pid(id)
        if pid != -1:
            return True
        else:
            return False

    def id_exist(self, id):
        ids = self.wf_utils.list_ids()        
        if id in ids:
            layer = self.sock.get_view(id)["layer"]
            if layer != "workspace":
                return False
            return True
        
        return False

    def update_taskbar_list(self):
        self.Taskbar("h", "taskbar")
        ids = self.wf_utils.list_ids()
        button_ids = self.buttons_id.copy()
        for button_id in button_ids:
            if button_id not in ids:
                self.taskbar_remove(button_id)

    def remove_button(self, id):
        button = self.buttons_id[id][0]
        if not self.utils.widget_exists(button):
            return
        self.taskbar.remove(button)
        self.taskbar_list.remove(id)
        self.utils.remove_gesture(button)
        del self.buttons_id[id]

    def taskbar_remove(self, id=None):
        if self.id_exist(id):
            return
        button = self.buttons_id[id][0]
        if not self.utils.widget_exists(button):
            return
        self.remove_button(id)

    # Append a window to the Dockbar
    # this whole function is a mess, this was based in another compositor
    # so need a rework
    def dockbar_append(self, *_):
        wclass = self.wf_utils.get_focused_view_app_id().lower()
        wclass = "".join(wclass)
        initial_title = wclass
        icon = wclass
        cmd = initial_title
        desktop_file = ""

        # Adjusting for special cases like zsh or bash
        if initial_title in ["zsh", "bash", "fish"]:
            title = self.get_focused_view_title().split()[0]
            title = self.utils.filter_utf8_for_gtk(title)
            cmd = f"kitty --hold {title}"
            icon = wclass

        # Handling icon mapping
        try:
            icon = self.panel_cfg["change_icon_title"][icon]
        except KeyError:
            print(f"Icon mapping not found for {icon}")

        try:
            for deskfile in os.listdir(self.webapps_applications):
                if (
                    deskfile.startswith("chrome")
                    or deskfile.startswith("msedge")
                    or deskfile.startswith("FFPWA-")
                ):
                    pass
                else:
                    continue
                webapp_path = os.path.join(self.webapps_applications, deskfile)
                # necessary initial title without lower()
                desktop_file_found = self.utils.search_str_inside_file(
                    webapp_path, initial_title
                )

                if desktop_file_found:
                    cmd = "gtk-launch {0}".format(deskfile)
                    icon = deskfile.split(".desktop")[0]
                    desktop_file = deskfile
                    break
        except Exception as e:
            print(e)

        # Update the dockbar configuration
        with open(self.dockbar_config, "r") as f:
            config = toml.load(f)
        new_data = {
            initial_title: {
                "cmd": cmd,
                "icon": icon,
                "wclass": wclass,
                "initial_title": initial_title,
                "desktop_file": desktop_file,
                "name": wclass,
            }
        }
        updated_data = ChainMap(new_data, config)
        with open(self.dockbar_config, "w") as f:
            toml.dump(updated_data, f)

        # Create and append button to the dockbar
        button = self.utils.CreateButton(
            icon, cmd, initial_title, wclass, initial_title
        )
        self.dockbar.append(button)

    # Remove a command from the dockbar configuration
    def dockbar_remove(self, cmd):
        with open(self.dockbar_config, "r") as f:
            config = toml.load(f)
        del config[cmd]
        with open(self.dockbar_config, "w") as f:
            toml.dump(config, f)

    # Join multiple windows of the same class into one workspace
    def join_windows(self, *_):
        activewindow = out("hyprctl activewindow".split()).decode()
        wclass = activewindow.split("class: ")[-1].split("\n")[0]
        activeworkspace = activewindow.split("workspace: ")[-1].split(" ")[0]
        j = out("hyprctl -j clients".split()).decode()
        clients = json.loads(j)
        for client in clients:
            if wclass in client["class"]:
                move_clients = f"hyprctl dispatch movetoworkspace {activeworkspace},address:{client['address']}".split()
                gotoworkspace = (
                    f"hyprctl dispatch workspace name:{activeworkspace}".split()
                )
                call(move_clients)
                call(gotoworkspace)
