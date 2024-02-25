import os
import signal
import toml
import gi
import json
import psutil
from subprocess import Popen, call, check_output as out
from collections import ChainMap
import threading
from src.core.create_panel import (
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell
from gi.repository import Gtk, Adw, GLib, Gio, GObject
from ..core.create_panel import (
    CreatePanel,
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)
from ..core.utils import Utils
import numpy as np
import wayfire as ws


class InvalidGioTaskError(Exception):
    pass


class AlreadyRunningError(Exception):
    pass


class BackgroundTaskbar(GObject.Object):
    __gtype_name__ = "BackgroundTaskbar"

    def __init__(self, function, finish_callback, **kwargs):
        super().__init__(**kwargs)

        self.function = function
        self.finish_callback = finish_callback
        self._current = None

    def start(self):
        if self._current:
            AlreadyRunningError("Task is already running")

        finish_callback = lambda self, task, nothing: self.finish_callback()

        task = Gio.Task.new(self, None, finish_callback, None)
        task.run_in_thread(self._thread_cb)

        self._current = task

    @staticmethod
    def _thread_cb(task, self, task_data, cancellable):
        try:
            retval = self.function()
            task.return_value(retval)
        except Exception as e:
            task.return_value(e)

    def finish(self):
        task = self._current
        self._current = None

        if not Gio.Task.is_valid(task, self):
            raise InvalidGioTaskError()

        value = task.propagate_value().value

        if isinstance(value, Exception):
            raise value

        return value


class Dockbar(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialize Utils and set configuration paths
        self.utils = Utils()
        self.home = os.path.expanduser("~")
        self.webapps_applications = os.path.join(self.home, ".local/share/applications")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.psutil_store = {}
        self.panel_cfg = self.utils.load_topbar_config()
        self.taskbar_list = [None]
        sock = self.compositor()
        self.all_pids = [i["id"] for i in sock.list_views()]
        self.timeout_taskbar = None
        self.buttons_pid = {}
        self.has_taskbar_started = False
        self.stored_windows = []
        self.window_created_now = None

    # Start the Dockbar application
    def do_start(self):
        # Set up a timeout to periodically check process IDs
        # GLib.timeout_add(300, self.update_active_window_shell)
        self.start_thread_compositor()
        # Populate self.stored_windows during panel start
        sock = self.compositor()
        self.stored_windows = [i["id"] for i in sock.list_views()]

        # Read configuration from topbar toml
        with open(self.topbar_config, "r") as f:
            panel_toml = toml.load(f)

            # Iterate over panel configurations
            for p in panel_toml:
                # Check if the panel is positioned on the left side
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

                # Check if the panel is positioned on the left side
                if "right" == p:
                    exclusive = panel_toml[p]["Exclusive"] == "True"
                    position = panel_toml[p]["position"]
                    # Create a right panel and associated components
                    self.right_panel = CreatePanel(
                        self, "RIGHT", position, exclusive, 32, 0, "RightBar"
                    )
                    workspace_buttons = self.utils.CreateFromAppList(
                        self.workspace_list_config, "v", "RightBar", None, True
                    )
                    self.right_panel.set_content(workspace_buttons)
                    self.right_panel.present()

                # Check if the panel is positioned at the bottom
                if "bottom" == p:
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
                    self.Taskbar("h", "taskbar", 0)

            # LayerShell.set_layer(self.left_panel, LayerShell.Layer.TOP)
            # LayerShell.set_layer(self.bottom_panel, LayerShell.Layer.TOP)

    def on_compositor_finished(self):
        # non working code
        try:
            self.taskbarwatch_task.finish()
        except Exception as err:
            print(err)

    def start_thread_compositor(self):
        self.scale_task = BackgroundTaskbar(
            self.ScaleWatch, lambda: self.on_compositor_finished
        )
        self.scale_task.start()

        self.taskbarwatch_task = BackgroundTaskbar(
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

    def TaskbarWatch(self):
        sock = self.compositor()
        sock.watch()
        view = None
        while True:
            try:
                msg = sock.read_message()
                if "view" in msg:
                    view = msg["view"]

                if "event" in msg:
                    if msg["event"] == "view-title-changed":
                        self.on_title_changed(msg["view"])

                    if msg["event"] == "app-id-changed":
                        self.on_app_id_changed()

                    if msg["event"] == "view-focused":
                        self.on_view_focused()
                        if view is not None:
                            if view["role"] == "toplevel":
                                self.on_view_role_toplevel_focused(view)

                    if msg["event"] == "view-mapped":
                        self.on_view_created()

                    if msg["event"] == "view-unmapped":
                        self.on_view_destroyed(msg["view"])

                    if msg["event"] == "plugin-activation-state-changed":
                        # if plugin state is true (activated)
                        if msg["state"] is True:
                            if msg["plugin"] == "expo":
                                self.on_expo_activated()
                            if msg["plugin"] == "scale":
                                self.on_scale_activated()

                        # if plugin state is false (desactivated)
                        if msg["state"] is False:
                            if msg["plugin"] == "expo":
                                self.on_expo_desactivated()
                            if msg["plugin"] == "scale":
                                self.on_scale_desactivated()
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

    def on_scale_activated(self):
        set_layer_position_exclusive(self.left_panel)
        set_layer_position_exclusive(self.right_panel)
        set_layer_position_exclusive(self.bottom_panel)

    def on_scale_desactivated(self):
        unset_layer_position_exclusive(self.left_panel)
        unset_layer_position_exclusive(self.right_panel)
        unset_layer_position_exclusive(self.bottom_panel)

    def on_view_created(self):
        self.taskbar_window_created()

    def on_view_destroyed(self, view):
        pid = view["pid"]
        self.taskbar_window_destroyed(pid)

    def on_title_changed(self, view):
        self.Taskbar("h", "taskbar")
        self.update_active_window_shell(view["id"])
        # if msg["event"] == "view-focused":
        # GLib.idle_add(self.update_title_topbar)

    def taskbar_window_created(self):
        self.Taskbar("h", "taskbar")

    def taskbar_window_destroyed(self, pid):
        self.taskbar_remove(pid)

    def ScaleWatch(self):
        self.event_scale_view()

    def compositor(self):
        addr = os.getenv("WAYFIRE_SOCKET")
        return ws.WayfireSocket(addr)

    def Taskbar(self, orientation, class_style, update_button=False, callback=None):
        sock = self.compositor()

        # Load configuration from dockbar_config file
        with open(self.dockbar_config, "r") as f:
            config = toml.load(f)

        # Extract desktop_file paths from the configuration
        launchers_desktop_file = [config[i]["desktop_file"] for i in config]

        for i in sock.list_views():
            wm_class = i["app-id"].lower()
            initial_title = i["title"].split()[0].lower()
            title = i["title"]
            pid = i["pid"]
            view_id = i["id"]

            # Skip windows with wm_class found in launchers_desktop_file if update_button is False
            if wm_class in launchers_desktop_file and not update_button:
                continue

            # Skip windows with pid found in self.taskbar_list if update_button is False
            if pid in self.taskbar_list and not update_button:
                continue

            button = self.utils.create_taskbar_launcher(
                wm_class,
                title,
                initial_title,
                orientation,
                class_style,
                view_id,
            )
            # Append the button to the taskbar
            self.taskbar.append(button)

            # Store button information in dictionaries for easy access
            self.buttons_pid[pid] = [button, initial_title, view_id]

            # Add the pid to the taskbar_list to keep track of added windows
            self.taskbar_list.append(pid)

        # Return True to indicate successful execution of the Taskbar function
        return True

    def update_taskbar(
        self,
        orientation,
        class_style,
        view_id,
        callb1ack=None,
    ):
        sock = self.compositor()
        view = sock.get_view(view_id)
        pid = view["pid"]
        title = view["title"]
        wm_class = view["app-id"]
        initial_title = title.split(" ")[0].lower()
        # Create a taskbar launcher button using utility function
        button = self.utils.create_taskbar_launcher(
            wm_class, title, initial_title, orientation, class_style, view_id
        )

        # Append the button to the taskbar
        self.taskbar.append(button)

        # Store button information in dictionaries for easy access
        self.buttons_pid[pid] = [button, initial_title, view_id]

        # Return True to indicate successful execution of the update_taskbar function
        return True

    def update_active_window_shell(self, id):
        sock = self.compositor()
        view = sock.get_view(id)
        pid = view["pid"]
        button = self.buttons_pid[pid][0]
        self.taskbar.remove(button)
        self.update_taskbar("h", "taskbar", id)
        return True

    def taskbar_remove(self, pid):
        # Iterate over copied dictionary to avoid concurrent modification
        # Remove button and associated data
        sock = self.compositor()
        list_pids = [i for i in sock.list_pids()]
        for pid in self.buttons_pid.copy():
            if pid not in list_pids:
                button = self.buttons_pid[pid][0]
                self.taskbar.remove(button)
                self.taskbar_list.remove(pid)
                del self.buttons_pid[pid]
        return True

    # Append a window to the dockbar
    def dockbar_append(self, *_):
        w = self.instance.get_active_window()
        initial_title = w.initial_title.lower()
        wclass = w.wm_class.lower()
        wclass = "".join(wclass)
        icon = initial_title
        cmd = initial_title
        desktop_file = ""

        # Adjusting for special cases like zsh or bash
        if initial_title in ["zsh", "bash", "fish"]:
            title = w.title.split(" ")[0]
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
                    webapp_path, w.initial_title
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
