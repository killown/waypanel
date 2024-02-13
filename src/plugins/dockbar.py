import os
import signal
import toml
import gi
import json
import psutil
from subprocess import Popen, call, check_output as out
from collections import ChainMap
import threading


gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell
from gi.repository import Gtk, Adw, GLib, Gio, GObject
from ..core.create_panel import *
from ..core.utils import Utils
import numpy as np
import waypy as ws


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
        # GLib.timeout_add(300, self.check_pids)
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

    def set_layer_position_exclusive(self, msg):
        if msg["view"] is None:
            # update taskbar if overview is activated
            LayerShell.set_layer(self.left_panel, LayerShell.Layer.TOP)
            LayerShell.set_layer(self.bottom_panel, LayerShell.Layer.TOP)

        else:
            self.compositor_window_changed()
            # LayerShell.set_exclusive_zone(self.left_panel, 0)
            # LayerShell.set_exclusive_zone(self.bottom_panel, 0)
            LayerShell.set_layer(self.left_panel, LayerShell.Layer.BOTTOM)
            LayerShell.set_layer(self.bottom_panel, LayerShell.Layer.BOTTOM)

    def event_scale_view(self):
        sock = self.compositor()
        sock.watch()
        while 1:
            msg = sock.read_message()
            if "event" in msg:
                print(msg)
                # lets try to not break the loop then catch the Exception
                try:
                    self.set_layer_position_exclusive(msg)
                except Exception as e:
                    print(e)

    def on_compositor_finished(self):
        # non working code
        try:
            retval = self.taskbarwatch_task.finish()
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
        self.update_active_window_shell()

    def TaskbarWatch(self):
        sock = self.compositor()
        sock.watch()
        while True:
            msg = sock.read_message()
            view = msg["view"]
            if view is None:
                return
            # window created
            if "event" in msg and msg["event"] == "view-mapped":
                self.taskbar_window_created(view["pid"])
            # window destroyed
            if "event" in msg and msg["event"] == "view-unmapped":
                self.taskbar_window_destroyed(view["pid"])

    def taskbar_window_created(self, pid):
        self.Taskbar("h", "taskbar", pid)

    def taskbar_window_destroyed(self, pid):
        self.taskbar_remove(pid)

    def ScaleWatch(self):
        self.event_scale_view()

    def compositor(self):
        addr = os.getenv("WAYFIRE_SOCKET")
        return ws.WayfireSocket(addr)

    def Taskbar(
        self, orientation, class_style, pid, update_button=False, callback=None
    ):
        sock = self.compositor()

        # Load configuration from dockbar_config file
        with open(self.dockbar_config, "r") as f:
            config = toml.load(f)

        # Extract desktop_file paths from the configuration
        launchers_desktop_file = [config[i]["desktop_file"] for i in config]

        for i in sock.list_views():
            # in case there is no views

            wm_class = i["app-id"].lower()
            initial_title = i["title"].split()[0].lower()

            # some classes and initial titles has whitespaces which will lead to not found icons
            if " " in initial_title:
                initial_title = initial_title.split()[0]
            if " " in wm_class:
                wm_class = wm_class.split()[0]

            title = i["title"]
            pid = i["pid"]
            view_id = i["id"]

            # Skip windows with wm_class found in launchers_desktop_file if update_button is False
            if wm_class in launchers_desktop_file and not update_button:
                continue

            # Skip windows with pid found in self.taskbar_list if update_button is False
            if pid in self.taskbar_list and not update_button:
                continue

            # Quick fix for nautilus initial class
            if "org.gnome.nautilus" in wm_class:
                initial_title = "nautilus"
            # Create a taskbar launcher button using utility function
            pid_view_id = {pid: view_id}
            button = self.utils.create_taskbar_launcher(
                wm_class,
                title,
                initial_title,
                orientation,
                class_style,
                pid_view_id,
            )
            print(button.get_name())
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
        pid,
        wm_class,
        initial_title,
        title,
        orientation,
        class_style,
        view_id,
        callback=None,
    ):
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

    def update_active_window_shell(self):
        sock = self.compositor()
        focused_view = sock.get_focused_view()
        initial_title = focused_view["title"].split()[0]

        # Check if the active window has the title "zsh"
        if initial_title in ["zsh", "fish", "bash"]:
            title = focused_view["title"]
            wm_class = focused_view["app-id"]
            pid = focused_view["pid"]

            # Quick fix for nautilus initial class
            if "org.gnome.nautilus" in wm_class.lower():
                initial_title = "nautilus"

            if pid in self.buttons:
                btn = self.buttons[pid]
                btn_title = btn[1]

                # Check if the title has changed
                if title != btn_title:
                    self.taskbar.remove(btn)
                    self.update_taskbar(
                        pid, wm_class, initial_title, title, "h", "taskbar", id
                    )

    def check_pids(self):
        # *** Need a fix since this code depends on the Hyprshell plugin
        if not instance.get_workspace_by_name("OVERVIEW"):
            return True

        # do not check anything if no window closed or created
        if not self.is_any_window_created_or_closed():
            self.update_active_window_shell()
            return True

        try:
            # Get the active window and all PIDs of windows with wm_class
            active_window = instance.get_active_window()
            list_pids = [i for i in sock.list_pids() if pid == i]

            # Check if the PIDs have changed
            if all_pids != self.all_pids:
                self.taskbar_remove()
                self.all_pids = all_pids
                self.Taskbar("h", "taskbar")
                return True
            self.update_active_window_shell()
        except Exception as e:
            print(e)

        # Return True to indicate successful execution of the check_pids function
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
