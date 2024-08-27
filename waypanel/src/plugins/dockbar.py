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

        # Read configuration from the topbar TOML file
        panel_toml = self._load_panel_config(self.topbar_config)

        # Set up panels based on the configuration
        self._setup_panels(panel_toml)

    def _load_panel_config(self, config_file):
        """Load and return panel configuration from the given TOML file."""
        with open(config_file, "r") as f:
            return toml.load(f)

    def _setup_panels(self, panel_toml):
        """Set up panels based on the provided configuration."""
        for p in panel_toml:
            if p == "left":
                self._setup_left_panel(panel_toml[p])
            elif p == "bottom":
                self._setup_bottom_panel(panel_toml[p])
            # Uncomment and implement if needed
            # elif p == "right":
            #     self._setup_right_panel(panel_toml[p])

    def _setup_left_panel(self, config):
        """Create and configure the left panel."""
        exclusive = config["Exclusive"] == "True"
        position = config["position"]

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

    def _setup_bottom_panel(self, config):
        """Create and configure the bottom panel."""
        exclusive = config["Exclusive"] == "True"
        position = config["position"]

        self.bottom_panel = CreatePanel(
            self, "BOTTOM", position, exclusive, 32, 0, "BottomBar"
        )
        self.add_launcher = Gtk.Button()
        self.add_launcher.set_icon_name("tab-new-symbolic")
        self.add_launcher.connect("clicked", self.dockbar_append)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.add_css_class("scrolled_window_bottom_bar")
        output = os.getenv("waypanel")
        output_name = None
        geometry = None

        if output:
            output_name = json.loads(output)
            output_name = output_name["output_name"]

        if output_name:
            output_id = self.wf_utils.get_output_id_by_name(output_name)
            if output_id:
                geometry = self.wf_utils.get_output_geometry(output_id)

        if geometry:
            monitor_width = geometry["width"]
            self.scrolled_window.set_size_request(monitor_width / 1.2, 64)

        self.bottom_panel.set_content(self.scrolled_window)
        self.taskbar = Gtk.Box()
        self.taskbar.set_halign(Gtk.Align.CENTER)  # Center horizontally
        self.taskbar.set_valign(Gtk.Align.CENTER)  # Center vertically
        self.scrolled_window.set_child(self.taskbar)
        self.taskbar.append(self.add_launcher)
        self.taskbar.add_css_class("taskbar")
        self.bottom_panel.present()

        # Start the taskbar list for the bottom panel
        self.Taskbar("h", "taskbar")

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
                            if msg["event"] == "view-geometry-changed":
                                if "view" in msg:
                                    view = msg["view"]
                                    if view["layer"] != "workspace":
                                        self.taskbar_remove(view["id"])

                            if msg["event"] == "output-gain-focus":
                                pass
                            self.handle_view_event(msg, view)
                            self.handle_plugin_event(msg)


                    except Exception as e:
                        print(e)
            except Exception as e:
                print(e)

    def on_view_role_toplevel_focused(self, view):
        return

    def on_expo_activated(self):
        return

    def on_moving_view(self):
        return 

    def on_expo_desactivated(self):
        return

    def on_view_focused(self):
        return

    def on_app_id_changed(self, view):
        self.update_taskbar_list(view)
        self.new_taskbar_view("h", "taskbar", view["id"])

    # events that will make the panel clickable or not
    def on_scale_activated(self):
        set_layer_position_exclusive(self.left_panel)
        # set_layer_position_exclusive(self.right_panel)
        set_layer_position_exclusive(self.bottom_panel)
        self.update_taskbar_for_hidden_views()
        return

    def on_scale_desactivated(self):
        unset_layer_position_exclusive(self.left_panel)
        # unset_layer_position_exclusive(self.right_panel)
        unset_layer_position_exclusive(self.bottom_panel)
        return

    def on_view_created(self, view):
        self.update_taskbar_list(view)
        self.new_taskbar_view("h", "taskbar", view["id"])

    def on_view_destroyed(self, view):
        self.update_taskbar_list(view)

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

            #this part enables output name in taskbar list buttons
            #if title:
            #  output_name = self.wf_utils.get_view_output_name(view["id"])
            #default_output = self.get_default_monitor_name()

            # if output_name != default_output:
            #   title = "({0}) {1}".format(output_name, title)
            # label.set_label(title)

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
        if not self.view_exist(view_id):
            return
        if view_id in self.taskbar_list:
            return
        view = self.sock.get_view(view_id)
        if view["type"] != "toplevel":
            return
        if view["layer"] != "workspace":
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
       
        # If the function returns None (for example, if pid == -1), 
        # clickable_image_box will be None, and nothing will be appended on to the taskbar
        # Premature Widget Addition: If you try to append the box to the AdwWindow before 
        # the window has been fully realized (allocated size and position), this could trigger the warning.
        # like that:  Trying to snapshot AdwWindow ..... without a current allocation ?
        # so that explains the use of GLib.idle_add() 
        # to ensure the UI loop has time to process allocations first.
        GLib.idle_add(lambda: self.utils.append_clickable_image(self.taskbar, button))

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

    def view_exist(self, id):
        ids = self.wf_utils.list_ids()
        if id in ids:
            view = self.sock.get_view(id)
            layer = view["layer"] != "workspace"
            role = view["role"] != "toplevel"
            mapped = view["mapped"] is False
            app_id = view["app-id"] == "nil"
            pid = view["pid"] == -1
            view_type = view["type"] != "toplevel"
            if layer or role or mapped or app_id or pid or view_type:
                return False
            return True
        return False

    def update_taskbar_for_hidden_views(self):
        #the goal of this function is to catch taskbar buttons which is not toplevel 
        #and should be in the task list, happens that sometimes there is not enough events 
        #to remove the button on the fly
        #this a made for hide view plugin which hide a view but still has no event to trigger
        #the taskbar button removal
        for button_id in self.buttons_id:
            view = self.sock.get_view(button_id)
            if view["role"] == "desktop-environment":
                self.remove_button(view["id"])
        #also update the view when unhide
        for view in self.sock.list_views():
            if view["role"] == "toplevel":
                if view["id"] not in self.buttons_id:
                    self.new_taskbar_view("h", "taskbar", view["id"])

    def update_taskbar_list(self, view):
        if not self.view_exist(view["id"]):
            self.taskbar_remove(view["id"])

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
        if self.view_exist(id):
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
