#!/usr/bin/env python3
import os
from pathlib import Path


os.environ["GI_TYPELIB_PATH"] = os.path.expanduser('~/.local/lib/gtk4-layer-shell/lib/girepository-1.0')

from ctypes import CDLL

CDLL("libgtk4-layer-shell.so")
from subprocess import Popen
from subprocess import check_output
import gi

import sys


from waypanel.src.core.utils import Utils as utils
from waypanel.src.core.create_panel import *
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GObject
import datetime
import importlib
from wayfire.ipc import *
import netifaces
import soundcard as sc

gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell

spam_loader = importlib.util.find_spec("wayfire")
found = spam_loader is not None

sys.setrecursionlimit(1600)

if not found:
    print("Module wayfire not found, try | pip install wayfire | and try again")
    sys.exit()

spam_loader = importlib.util.find_spec("gi")
found = spam_loader is not None

if not found:
    print("Module 'gi' not found, install python gobject")

import psutil
import pulsectl
import toml
from collections import ChainMap

from waypanel.src.plugins.dockbar import Dockbar
from waypanel.src.plugins.bookmarksPopover import PopoverBookmarks
from waypanel.src.plugins.dashboardPopover import PopoverDashboard
from waypanel.src.plugins.dashboardSoundCard import SoundCardDashboard
from waypanel.src.plugins.dashboardBluetooth import BluetoothDashboard
from waypanel.src.plugins.dashboardSystem import SystemDashboard
from waypanel.src.plugins.folders import PopoverFolders
from waypanel.src.plugins.clipboardMenu import MenuClipboard
from waypanel.src.plugins.launcherMenu import MenuLauncher
from waypanel.src.core.utils import Utils
from waypanel.src.core.background import *
from wayfire.ipc import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils


class Panel(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialize utilities and connect to activation event
        self._initialize_utilities()
        self.connect("activate", self.on_activate)

        # Setup panel boxes
        self._setup_panel_boxes()

        self.toggle_mute = {}
        self.volume = 0
        self.clock_box = Gtk.Box()
        self.args = sys.argv

        # Configuration paths
        self._setup_config_paths()

        # Load configurations
        self.panel_cfg = self.load_topbar_config()

        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)


        self.utils = utils()

        self.get_icon = self.utils.get_icon
        self.active_window_changed = None
        self.notifications = []
        self.popover_bookmarks = None
        self.popover_folders = None
        self.popover_launcher = None
        self.popover_clipboard = None
        self.set_cpu_usage_state = []
        self.clipboard_text_copy = None
        self.active_window_changed = None
        self.waypanel_started_now = True
        self.window_title_from_topbar = None
        self.active_window = None
        self.last_view_toplevel_focused = None
        self.last_focused_output = None
        self.is_scale_active = None
        self.focused_output = None
        self.dpms_monitors_timeout = 3600
        self.vol_slider = None
        self.icon_vol_slider = None
        self.workspace_empty = None
        self.timeout_ids = {}
        self.turn_off_monitors_timeout = None
        self.signal_view_destroyed = False
        self.was_last_focused_view_maximized = None
        self.previous_workspace = {}
        self.request_switch_keyboard_on_demand_to_none = None
        with open(self.topbar_config) as topbar_config:
            config = toml.load(topbar_config)

        self.tilling_enabled = config["views"]["tilling"]
        self.maximize_views_on_expo_enabled = config["views"]["maximize_views_on_expo"]

        self.window_title_topbar_length = config["window_title_lenght"]["size"]

        # Monitor dimensions to set the panel size
        self.monitor_width, self.monitor_height = 0, 0
        if "monitor" in config:
            self.monitor_width, self.monitor_height = (
                config["monitor"]["width"],
                config["monitor"]["height"],
            )
        self.monitor_name = None
        try:
            self.monitor_name = config["monitor"]["name"]
        except KeyError:
            print("configure [monitor] in .config/panel.toml")
            sys.exit()

        with open(self.topbar_config, "r") as f:
            self.topbar_config_loaded = toml.load(f)

            #self.background_panel_enabled = self.topbar_config_loaded["background_panel"][
            #"enabled"]

        with open(self.dockbar_config, "r") as f:
            self.dockbar_config_loaded = toml.load(f)

    def _initialize_utilities(self):
        """Initialize utility functions and properties."""
        self.utils = Utils(application_id="com.github.utils")

    def _setup_panel_boxes(self):
        """Setup panel boxes and related configurations."""
        self.top_panel_box_left = Gtk.Box(spacing=10)
        self.top_panel_box_systray = Gtk.Box(spacing=2)
        self.top_panel_box_for_buttons = Gtk.Box(spacing=6)
        self.top_panel_box_window_title = Gtk.Box(spacing=6)
        self.top_panel_box_widgets_left = Gtk.Box(spacing=6)
        self.top_panel_box_left.append(self.top_panel_box_widgets_left)
        self.top_panel_box_left.append(self.top_panel_box_window_title)
        self.top_panel_box_right = Gtk.Box(spacing=10)
        self.top_panel_grid_right = Gtk.Grid(column_spacing=10)
        self.top_panel_grid_right.attach(self.top_panel_box_right, 1, 0, 1, 2)
        self.top_panel_grid_right.attach_next_to(
            self.top_panel_box_systray,
            self.top_panel_box_right,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )
        self.top_panel_grid_right.attach_next_to(
            self.top_panel_box_for_buttons,
            self.top_panel_box_systray,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )

        self.top_panel_box_center = Gtk.Box(spacing=6)
        self.top_panel_box_full = Gtk.Grid()
        self.top_panel_box_full.set_column_homogeneous(True)
        self.top_panel_box_full.attach(self.top_panel_box_left, 1, 0, 1, 2)
        self.top_panel_box_full.attach_next_to(
            self.top_panel_box_center,
            self.top_panel_box_left,
            Gtk.PositionType.RIGHT,
            1,
            2,
        )
        self.top_panel_box_full.attach_next_to(
            self.top_panel_grid_right,
            self.top_panel_box_center,
            Gtk.PositionType.RIGHT,
            1,
            3,
        )
        # load the Dockbar
        self.dock = Dockbar(application_id="com.github.dockbar")

        self.clock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.scripts = os.path.join(self.home, ".config/waypanel/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.topbar_launcher_config = os.path.join(
            self.config_path, "topbar-launcher.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_path)
            os.makedirs(self.scripts)

    def on_activate(self, app):
        # FIXME: need to create a way to allow setup positions of widgets
        self.monitor_width_height()
        # start cmd output session, cmd.toml
        self.cmd_output()
        self.close_fullscreen_buttons()
        self.right_position_launcher_topbar()
        self.setup_panels()
        self.setup_clock_widget()
        self.update_widget_with_timeout()
        self.setup_background_panel_widgets()
        self.setup_panel_buttons()
        self.setup_panel_position()
        self.setup_gestures()

        required_plugins = [
            "stipc",
            "ipc",
            "ipc-rules",
            "resize",
            "window-rules",
            "wsets",
            "session-lock",
            "wm-actions",
            "move",
            "vswitch",
            "grid",
            "place",
            "scale",
        ]

        #extra_features = ExtraFeatures()
        #enabled_plugins = extra_features.list_enabled_plugins()

        COLOR_RESET = "\033[0m"
        COLOR_RED = "\033[91m"

        #for plugin in required_plugins:
        #    if plugin not in enabled_plugins:
        #        print(
        #            "\n{0}ERROR:{2} The plugin: {0}'{1}'{2} is required to start the shell!!!!".format(
        #                COLOR_RED,
        #                plugin,
        #                COLOR_RESET,
        #            )
        #        )
        #        print("Required Plugin List: {}".format(required_plugins))
        #        sys.exit()

        # plugins
        self.MenuLauncher = MenuLauncher()
        self.MenuLauncher.create_menu_popover_launcher(self, app)

        bookmarks_file = os.path.join(self.home, ".bookmarks")
        if os.path.exists(bookmarks_file):
            self.PopoverBookmarks = PopoverBookmarks()
            self.PopoverBookmarks.create_menu_popover_bookmarks(self, app)
        self.PopoverFolders = PopoverFolders()
        self.PopoverFolders.create_menu_popover_folders(self, app)
        self.MenuClipboard = MenuClipboard()
        self.MenuClipboard.create_popover_menu_clipboard(self, app)

        # bluetooth manager
        self.top_panel_box_systray.append(self.bluetooth_manager())

        # volume
        self.top_panel_box_systray.append(self.volume_slider())

        # menus
        self.menus = self.create_new_menu()
        self.setup_menus()

        # system dashboard
        self.top_panel_box_systray.append(self.system_dashboard())

        # the title is only updated when a event happens, so needed to update in the panel start
        self.update_title_topbar()
        self.start_thread_all_events()

        # Start monitoring CSS file for changes
        self.monitor = Gio.File.new_for_path(self.style_css_config).monitor(
            Gio.FileMonitorFlags.NONE, None
        )
        self.monitor.connect("changed", self.on_css_file_changed)

        self.get_focused_output = self.sock.get_focused_output()

        self.output_is_ready_to_dpms_off = {}
        for output_name in self.wf_utils.list_outputs_names():
            self.output_is_ready_to_dpms_off[output_name] = False

        with open(self.topbar_config, "r") as f:
            panel_toml = toml.load(f)

        timeout_all = panel_toml["dpms"]["timeout_all"]
        timeout_single = panel_toml["dpms"]["timeout_single"]
        self.dpms_enabled = panel_toml["dpms"]["enabled"]
        self.turn_off_monitors_timeout = GLib.timeout_add_seconds(
            timeout_all, self.dpms_manager
        )
        self.turn_off_monitor_timeout = timeout_single

    def do_activate(self):
        self.show_panels()

    # def freedesktop_notifications(self):
    # DBusGMainLoop(set_as_default=True)
    # bus = dbus.SessionBus()
    # string = "interface='org.freedesktop.Notifications',member='Notify', eavesdrop='true'"
    # bus.add_match_string(string)
    # bus.add_message_filter(self.notification_msg)

    def get_folder_location(self, folder_name):
        """
        Get the location of a specified folder for the current user.

        :param folder_name: The name of the folder to locate.
                            Possible values: "DOCUMENTS", "DOWNLOAD", "MUSIC", "PICTURES", "VIDEOS", etc.
        :return: The path to the specified folder, or None if it cannot be determined or does not exist.
        """
        folder_location = None
        try:
            # Get the user's specified folder using xdg-user-dir
            folder_path = Gio.File.new_for_uri(
                f"xdg-user-dir://{folder_name.upper()}"
            ).get_path()
            folder_location = Gio.File.new_for_path(folder_path)
        except Exception as e:
            print(f"Error: {e}")

        return folder_location.get_path() if folder_location else None

    def wayland_instance_watch(self):
        self.wayinstance.signal_active_window_changed.connect(
            self.wayland_window_changed
        )

    def update_background_panel(self):
        
        # if sock.is_focused_view_fullscreen():
        #    return True
        view = self.sock.get_focused_view()
        title = view["title"]
        title = self.utils.filter_utf8_for_gtk(title)
        workspace_id = self.wf_utils.get_active_workspace_number()
        pid = view["pid"]
        wclass = view["app-id"]
        initial_title = title.split()[0]
        # Update title and icon
        self.update_widgets(
            title,
            wclass,
            initial_title,
            pid,
            workspace_id,
        )
        if self.is_scale_active:
            return True
        else:
            return False

    def handle_tilling_layout(self, view):
        if view["type"] == "toplevel" and view["parent"] == -1:
            # this is needed, self.sock, if pass sock from watch, it will fail 
            wx = self.wf_utils.get_active_workspace()["x"] 
            wy = self.wf_utils.get_active_workspace()["y"]
            wset = self.sock.get_focused_view()["wset-index"]
            layout = self.sock.get_tiling_layout(wset, wx, wy)
            all_views = self.wf_utils.tile_list_views(layout)
            output = self.sock.get_focused_output()
            desired_layout = {}
            if not all_views or (len(all_views) == 1 and all_views[0][0] == view["id"]):
                desired_layout = {
                    "vertical-split": [{"view-id": view["id"], "weight": 1}]
                }
                self.sock.set_tiling_layout(wset, wx, wy, desired_layout)
                return

            main_view = all_views[0][0]
            weight_main = all_views[0][1]
            stack_views_old = [v for v in all_views[1:] if v[0] != view["id"]]
            weight_others = max(
                [v[1] for v in stack_views_old],
                default=output["workarea"]["width"] - weight_main,
            )

            if main_view == view["id"]:
                return

            if not stack_views_old:
                desired_layout = {
                    "vertical-split": [
                        {"view-id": main_view, "weight": 1},
                        {"view-id": view["id"], "weight": 1},
                    ]
                }
                self.sock.set_tiling_layout(wset,wx,wy,desired_layout)
                return

            stack = [{"view-id": v[0], "weight": v[2]} for v in stack_views_old]
            stack += [
                {
                    "view-id": view["id"],
                    "weight": sum([v[2] for v in stack_views_old])
                    / len(stack_views_old),
                }
            ]

            desired_layout = {
                "vertical-split": [
                    {"weight": weight_main, "view-id": main_view},
                    {"weight": weight_others, "horizontal-split": stack},
                ]
            }

            self.sock.set_tiling_layout(wset, wx, wy, desired_layout)

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
                if msg["plugin"] == "builtin-close-view":
                    self.on_view_destroyed()
            else:
                if msg["plugin"] == "expo":
                    self.on_expo_desactivated()
                if msg["plugin"] == "scale":
                    self.on_scale_desactivated()

    def handle_view_event(self, msg, view):
        event = None
        if "event" not in msg:
            return
        else:
            event = msg["event"]

        if event == "view-unmapped":
            self.on_view_destroyed()

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

        if event == "view-title-changed":
            self.on_title_changed()

        if event == "view-tiled" and view:
            if self.wf_utils.is_view_maximized(view["id"]):
                self.was_last_focused_view_maximized = True

        if event == "app-id-changed":
            self.on_app_id_changed()

        if event == "view-focused":
            self.on_view_role_toplevel_focused(view["id"])
            self.on_view_focused()
            self.last_focused_output = view["output-id"]

        if event == "view-mapped":
            self.on_view_created(view)

    def set_previous_workspace_with_views(self, msg):       
        focused_output = self.wf_utils.get_focused_output_name()
        wviews = self.wf_utils.get_workspaces_with_views()
        pw = msg["previous-workspace"]

        # only set previous workspaces that has views
        if any(i for i in wviews if pw["x"] == i["x"] and pw["y"] == i["y"]):
            self.previous_workspace[focused_output] = pw
        else:
            wviews = self.wf_utils.get_workspaces_with_views()
            wviews = {"x": wviews[-1]["x"], "y": wviews[-1]["y"]}
            self.previous_workspace[focused_output] = wviews

    def handle_workspace_events(self, msg):
        if "event" not in msg:
            return

        if msg["event"] == "wset-workspace-changed":
            self.set_previous_workspace_with_views(msg)

    def handle_output_events(self, msg):
        if "event" not in msg:
            return
        if msg["event"] == "output-gain-focus":
            self.output_get_focus()
            return

    def all_events_watch(self):
        while True:
            try:
                sock = WayfireSocket()
                sock.watch()
                view = None
                while True:
                    msg = sock.read_message()
                    # dpms counter
                    GLib.source_remove(self.turn_off_monitors_timeout)
                    self.turn_off_monitors_timeout = GLib.timeout_add_seconds(
                        self.dpms_monitors_timeout, self.dpms_manager
                    )
                    if "event" not in msg:
                        continue

                    if "view" in msg:
                        if msg["view"]["pid"] == -1:
                            continue

                    self.handle_output_events(msg)

                    if msg["event"] == "view-mapped":
                        # for some reason sock fails if pass to handle tilling
                        self.handle_tilling_layout(view)

                    if "view" in msg:
                        view = msg["view"]
                        self.handle_view_event(msg, view)

                    self.handle_plugin_event(msg)
                    self.handle_workspace_events(msg)
            except Exception as e:
                print(e)

    def on_view_role_toplevel_focused(self, view_id):
        # last view focus only for top level Windows
        # means that views like layer shell won't have focus set in this var
        # this is necessary for example, if you click in the maximize buttons
        # in the top bar then you need a toplevel window to maximize_last_view
        # if not, it will try to maximize the LayerShell
        # big comment because I am sure I will forget why I did this
        self.last_view_toplevel_focused = view_id

    def dpms_manager(self, timeout=0):
        # if timeout is zero, turn off all monitors and return false for probably glib.timeout
        if timeout == 0:
            print(
                "{self.dpms_monitors_timeout} hour of inactivity. Turning off monitor(s)..."
            )
            # no dpms while the focused view is fullscreen
            if not self.wf_utils.is_focused_view_fullscreen():
                self.wf_utils.dpms("off")
                return False
            else:
                return True

        monitors = self.utils.dpms_status()
        focused_monitor = self.wf_utils.get_focused_output_name()
        self.cancel_timeout_if_monitor_has_focus(focused_monitor)

        # Turn on monitors that are currently off
        for mon in monitors:
            if monitors[mon] == "off":
                self.utils.dpms("on", mon)

        # Set up timeouts for monitors that are not focused and not already timed out
        for mon in monitors:
            if monitors[mon] != focused_monitor:
                monitor_id = self.wf_utils.get_output_id_by_name(mon)
                if not self.wf_utils.has_ouput_fullscreen_view(monitor_id):
                    if (
                        mon not in self.timeout_ids
                    ):  # Check if timeout is not already set
                        # Set up a GLib timeout and store its ID
                        self.timeout_ids[mon] = GLib.timeout_add_seconds(
                            timeout, self.set_output_ready_for_dpms_off, mon
                        )

    def set_output_ready_for_dpms_off(self, mon):
        if self.monitor_has_focus(mon):
            return
        monitor_id = self.wf_utils.get_output_id_by_name(mon)
        if self.wf_utils.has_ouput_fullscreen_view(monitor_id):
            return
        self.utils.dpms("off", mon)
        # Remove the timeout ID from the dictionary
        self.timeout_ids.pop(mon, None)
        return False

    def monitor_has_focus(self, mon):
        focused_monitor = self.wf_utils.get_focused_output_name()
        return mon == focused_monitor

    def cancel_timeout_if_monitor_has_focus(self, mon):
        if self.monitor_has_focus(mon):
            timeout_id = self.timeout_ids.get(mon)
            if timeout_id:
                GLib.source_remove(timeout_id)
                self.timeout_ids.pop(mon, None)

    def output_get_focus(self):
        focused_output_name = self.wf_utils.get_focused_output_name()
        self.utils.run_cmd("xrandr --output {0}".format(focused_output_name))
        if self.dpms_enabled:
            self.dpms_manager(self.turn_off_monitor_timeout)

    def on_moving_view(self):
        return

    def on_title_changed(self):
        self.update_title_topbar()

    # created view must start as maximized to auto tilling works
    def on_view_created(self, view):
        # 
        # view_id = view["id"]
        # config_path = os.path.join(self.home, ".config/waypanel/")
        shader = os.path.join(config_path, "shaders/border")
        # if os.path.exists(shader):
        #    sock.set_view_shader(view_id, shader)

        # 
        # if self.tilling_enabled == "False":
        #    return
        # if sock.is_view_maximized(view["id"]):
        #    sock.tilling()
        return

    def on_view_destroyed(self):
        # FIXME: awaiting a fix in wayfire that is spamming unmapped views when switching tabs
        # if view_id in self.list_ids():
        #    return

        # if it check if workspace has views too fast, will still get the id from destroyed view
        # and thus never change to next workspace
        # sleep(0.2)
        # this signal will be cleared with {'event': 'view-focused', 'view': None}
        # useful when focusing empty workspaces
        # if no signal like that, the go_next_workspace_with_views will be triggered
        # and never will allow to visit an empty workspace
        # workspace_from_view = self.sock.get_workspace_from_view(view_id)
        # if not self.sock.has_workspace_views(workspace_from_view):
        #    sock.go_next_workspace_with_views()
        # sock.focus_next_view_from_active_workspace()

        return

    def on_app_id_changed(self):
        self.update_title_topbar()

    def on_expo_activated(self):
        return

    def on_expo_desactivated(self):
        # when you move a view in expo, it sometimes will leave workspace area
        # isn't the panel goal to change compositor behaviour
        # but for some a nice quick fix, if you dont need this
        # just disable this function call
        self.maximize_last_view_on_expo_desacivated()
        return

    def on_scale_activated(self):
        # call it once to update without waiting timeout_add
        # then timeout_add until scale is false

        #if self.background_panel_enabled:
        #    self.update_background_panel()
        #    self.set_cpu_usage()
        #    GLib.timeout_add_seconds(1, self.set_cpu_usage)
        #    GLib.timeout_add_seconds(1, self.update_background_panel)
        #    set_layer_position_exclusive(self.update_background_panel)
        self.is_scale_active = True

    def on_scale_desactivated(self):
        #if self.background_panel_enabled:
        #    unset_layer_position_exclusive(self.update_background_panel)
        self.is_scale_active = False

    def on_view_focused(self):
        self.update_title_topbar()

    def maximize_last_view_on_expo_desacivated(self):
        if self.maximize_views_on_expo_enabled == "False":
            return
        if self.wf_utils.is_focused_view_fullscreen:
            return
        # check if the workspace has only one view so maximize this view
        ws_info = self.get_active_workspace_info()
        ws_with_views = [
            i
            for i in self.wf_utils.get_workspaces_with_views()
            if i["x"] == ws_info["x"] and i["y"] == ws_info["y"]
        ]
        ws_count = len(ws_with_views)
        if ws_count != 1:
            return
        id = ws_with_views[0]["view-id"]
        if ws_count == 1:
            self.maximize(id)
        # id = self.last_view_toplevel_focused
        # 
        # sock.maximize(id)
        return

    def start_thread_all_events(self):
        self.all_events = Background(
            self.all_events_watch, lambda: self.on_compositor_finished
        )
        self.all_events.start()

    def on_compositor_finished(self):
        # non working code
        try:
            self.all_events_watch.finish()
        except Exception as err:
            print(err)

    def focused_window_info(self):
        
        return self.sock.get_focused_view()

    def list_views(self):
        
        return self.sock.list_views()

    # this function need a rework, get active monitor
    # remove manual query once you find a way to get active monitor
    def monitor_width_height(self):
        # get monitor info and set the width, height for the panela
        
        focused_view = self.sock.get_focused_view()
        # there is no monitor focused output while there is no views
        if focused_view:
            output = self.get_monitor_info()
            output = output[self.monitor_name]
            self.monitor_width = output[0]
            self.monitor_height = output[1]

    def setup_menus(self):
        for menu in self.menus.values():
            self.top_panel_box_systray.append(menu)
            self.top_panel_box_systray.set_halign(Gtk.Align.END)
            self.top_panel_box_systray.set_hexpand(True)

    def setup_background_panel_widgets(self):
        # notes label
        self.todo_button = Adw.ButtonContent()
        self.todo_button.add_css_class("todo_label")
        self.todo_button.set_icon_name("task-due")
        todo = os.path.join(self.home, "Documentos", "todo.txt")

        try:
            txt = open(todo, "r").readlines()[-1]
            self.todo_button.set_label(txt.strip())
            # GLib.timeout_add(600000, self.todo_txt)
        except IndexError:
            print("todo.txt is empity or does not exist")

        self.tbbox = Gtk.Box(spacing=20)
        self.tblabelspace = Gtk.Label(label="    ")
        self.tbworkspace = self.utils.btn_background(
            "tbworkspace", "gnome-panel-workspace-switcher"
        )
        self.tbpid = self.utils.btn_background("tbpid", "view-process-tree")
        self.tbclass = self.utils.btn_background("tbclass", "cs-windows-symbolic")
        self.tbcpusage = self.utils.btn_background(
            "tbcpusage", "preferences-devices-cpu"
        )
        self.tbmemusage = self.utils.btn_background(
            "tbmemusage", "indicator-sensors-memory"
        )
        self.tbsinkinput = self.utils.btn_background(
            "tbsinkinput", "multimedia-volume-control-symbolic"
        )
        # self.tbSIGKILL = self.utils.btn_background("tbSIGKILL", "window-close-symbolic")
        self.tbdiskusage = self.utils.btn_background(
            "tbdiskusage", "disk-usage-analyzer"
        )
        self.tbvol = self.utils.btn_background("tbvol", "audio-volume-high-symbolic")
        self.tbcard = self.utils.btn_background("tbvoltbcard", "audio-card")
        self.tbnet = self.utils.btn_background(
            "tbnet", "notification-network-ethernet-connected"
        )
        self.tbdiskusage.set_label("Disk Usage")
        self.tbsinkinput.set_label("Toggle Mute")
        # self.tbSIGKILL.set_label("SIGKILL")
        # self.tbexe = self.utils.btn_background("tbexe", "exec")
        self.tbbox.append(self.tblabelspace)
        self.tbbox.append(self.tbworkspace)
        self.tbbox.append(self.tbclass)
        self.tbbox.append(self.tbpid)
        # self.tbbox.append(self.tbSIGKILL)
        # self.tbbox.append(self.tbsinkinput)
        # self.tbbox.append(self.tbcard)
        self.tbbox.append(self.tbvol)
        self.tbbox.append(self.tbnet)
        self.tbbox.append(self.tbcpusage)
        self.tbbox.append(self.tbmemusage)
        # self.tbbox.append(self.tbexe)
        self.tbbox.append(self.tbdiskusage)
        self.tbbox.append(self.todo_button)

        # self.tbSIGKILL.connect("clicked", self.sigkill_activewindow)
        self.top_panel_background.set_content(self.tbbox)

    def update_widget_with_timeout(self):
        if os.path.exists("/usr/bin/mullvad"):
            GLib.timeout_add(10000, self.mullvad_status)

    def show_panels(self):
        if self.all_panels_enabled:
            self.top_panel.present()
            self.dock.do_start()
            #if self.background_panel_enabled:
            #    self.top_panel_background.present()
            # load the dockbar

    def setup_panel_buttons(self):
        if self.default_panel:
            self.top_panel.set_content(self.top_panel_box_full)
        if [i for i in self.args if "topbar" in i]:
            self.dockbar, _ = self.create_widgets("h", "TopBar")
            self.all_panels_enabled = False
            self.top_panel.present()

    def clock_dashboard(self, *_):
        # self.dashboard = Dashboard(application_id="org.waypanel.dashboard",flags= Gio.ApplicationFlags.FLAGS_NONE)
        # self.dashboard.run(sys.argv)
        # self.utils.run_app("python {0}/calendar.py".format(self.scripts))
        return

    def setup_gestures(self):
        # Setting up gestures for various UI components
        self.utils.create_gesture(self.todo_button, 1, self.take_note_app)
        # self.utils.create_gesture(self.clock_box, 1, self.clock_dashboard)
        self.utils.create_gesture(self.window_title, 1, self.manage_window_notes)
        self.utils.create_gesture(self.tbclass, 1, self.dock.dockbar_append)
        # self.utils.create_gesture(self.tbclass, 3, self.dock.join_windows)
        # self.utils.create_gesture(self.tbSIGKILL, 1, self.sigkill_activewindow)
        self.utils.create_gesture(self.tbvol, 1, self.toggle_mute_from_sink)

        # Gestures for top panel
        self.utils.create_gesture(
            self.top_panel_box_left, 2, self.left_gesture_middle_click
        )
        self.utils.create_gesture(
            self.top_panel_box_left, 3, self.left_gesture_right_click
        )

        # Gestures for center panel
        self.utils.create_gesture(
            self.top_panel_box_center, 2, self.center_gesture_middle_click
        )
        self.utils.create_gesture(
            self.top_panel_box_center, 3, self.center_gesture_right_click
        )

        # Gestures for right panel
        self.utils.create_gesture(
            self.top_panel_box_right, 1, self.right_gesture_left_click
        )
        self.utils.create_gesture(
            self.top_panel_box_right, 2, self.left_gesture_middle_click
        )
        self.utils.create_gesture(
            self.top_panel_box_right, 3, self.left_gesture_right_click
        )

        self.utils.create_gesture(self.top_panel_box_systray, 3, self.notify_client)

        # click will copy pid to clipboard
        self.tbpid_gesture = self.utils.create_gesture(
            self.tbpid, 1, self.copy_to_clipboard
        )

        # Adding scroll event to the full panel
        EventScroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        EventScroll.connect("scroll", self.scroll_event)
        self.top_panel_box_full.add_controller(EventScroll)

    def maximize_last_focused_view(self, *_):
        self.maximize(self.last_view_toplevel_focused)

    def close_last_focused_view(self, *_):
        self.sock.close_view(self.last_view_toplevel_focused)

    def close_fullscreen_buttons(self):
        # Creating close and full screen buttons for the top bar
        self.cf_box = Gtk.Box()
        self.maximize_button = self.utils.CreateButton(
            "window-maximize-symbolic",
            None,
            "maximize",
            None,
            use_function=self.maximize_last_focused_view,
        )
        self.close_button = self.utils.CreateButton(
            "window-close-symbolic",
            None,
            "close",
            None,
            use_function=self.close_last_focused_view,
        )
        self.minimize_button = self.utils.CreateButton(
            "window-minimize-symbolic",
            None,
            "minimize",
            None,
            use_function=self.minimize_view,
        )
        self.cf_box.append(self.minimize_button)
        self.cf_box.append(self.maximize_button)
        self.cf_box.append(self.close_button)
        self.cf_box.add_css_class("cf_box")
        self.top_panel_box_for_buttons.append(self.cf_box)

    def minimize_view(self, *kargs):
        view_id = self.sock.get_focused_view()["id"]
        print(view_id)
        self.sock.set_view_minimized(view_id, True)

    def right_position_launcher_topbar(self):
        # Creating close and full screen buttons for the top bar
        box = self.utils.CreateFromAppList(self.topbar_launcher_config, "h", "TopBar")
        self.top_panel_box_systray.append(box)

    def get_soundcard_list(self):
        return sc.all_speakers()

    def get_default_soundcard_id(self):
        return sc.default_speaker().id

    def get_default_soundcard_name(self):
        return sc.default_speaker().name

    def set_default_soundcard(self, id):
        cmd = "pactl set-default-sink {0}".format(id).split()
        Popen(cmd)

    def setup_clock_widget(self):
        # Configuring the clock widget for display
        self.clock_box.set_halign(Gtk.Align.CENTER)
        self.clock_box.set_hexpand(True)
        self.clock_box.set_baseline_position(Gtk.BaselinePosition.CENTER)
        self.clock_box.add_css_class("Clock")

        # Creating clock label with current date and time
        self.PopoverDashboard = PopoverDashboard()
        self.popover_dashboard = self.PopoverDashboard.create_menu_popover_dashboard(
            self, app
        )
        self.clock_label = self.popover_dashboard
        self.clock_label.set_label(datetime.datetime.now().strftime("%b %d  %H:%M"))
        self.clock_label.set_halign(Gtk.Align.CENTER)
        self.clock_label.add_css_class("ClockButton")
        self.clock_label.set_hexpand(True)
        self.clock_box.append(self.clock_label)

        # Adding the clock widget to the center panel
        self.top_panel_box_center.append(self.clock_box)

        # Schedule the initial update and then update every minute
        GLib.timeout_add_seconds(60 - datetime.datetime.now().second, self.update_clock)

    def update_clock(self):
        try:
            print("Updating clock...")

            # Update the label with the current date and time
            self.clock_label.set_label(datetime.datetime.now().strftime("%b %d  %H:%M"))

        except Exception as e:
            print("An error occurred while updating the clock:", e)

        # Schedule the next update after 60 seconds
        try:
            timeout_id = GLib.timeout_add_seconds(60, self.update_clock)
            if timeout_id == 0:
                print("Failed to schedule next update")
        except Exception as e:
            print("Error scheduling next update:", e)

        # Returning False means the timeout will not be rescheduled automatically
        return False

    def setup_panel_position(self):
        """
        Set up the position and content of various panels based on the command-line arguments.

        This method configures custom panel positions and widgets based on provided command-line arguments.
        """

        panel_configurations = {
            "topbar": ("h", "TopBar", self.top_panel),
            "rightbar": ("h", "RightBar", self.right_panel),
            "leftbar": ("v", "LeftBar", self.left_panel),
            "bottombar": ("h", "BottomBar", self.bottom_panel),
        }

        for arg, (orientation, panel_name, panel) in panel_configurations.items():
            if any(arg in i for i in self.args):
                dockbar, workspace_buttons = self.create_widgets(
                    orientation, panel_name
                )
                self.all_panels_enabled = False
                panel.present()

                if f"--{arg}-apps" in self.args:
                    panel.set_content(dockbar)
                elif f"--{arg}-workspaces" in self.args:
                    panel.set_content(workspace_buttons)
                elif f"--{arg}-todo" in self.args:
                    panel.set_content(self.todo_label_box)

    def on_css_file_changed(self, monitor, file, other_file, event_type):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            # Reload CSS when changes are done
            self.load_css_from_file()

    def load_css_from_file(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_file(Gio.File.new_for_path(self.style_css_config))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def on_waywatch_finished(self, task):
        try:
            task.finish()
        except Exception as err:
            print("Unhandled exception occured!", err.message)

    def setup_panels(self):
        self.top_panel_box_left.add_css_class("top_panel_box_left")
        self.top_panel_box_window_title.add_css_class("top_panel_box_window_title")
        self.top_panel_box_widgets_left.add_css_class("top_panel_box_widgets_left")
        self.top_panel_box_right.add_css_class("top_panel_box_right")
        self.top_panel_box_systray.add_css_class("top_panel_box_systray")
        self.top_panel_box_center.add_css_class("top_panel_box_center")
        self.top_panel_box_full.add_css_class("top_panel_box_full")
        self.panel_on_top = "TOP"
        self.exclusive = True
        self.all_panels_enabled = True

        self.load_css_from_file()

        self.top_panel_box_right.set_halign(Gtk.Align.FILL)
        self.top_panel_box_right.set_homogeneous(True)
        self.top_panel_box_right.set_hexpand(True)

        # setup window title
        self.window_title = Adw.ButtonContent()
        self.top_panel_box_window_title.append(self.window_title)
        self.window_title.add_css_class("WindowTitle")

        if "--custom" in self.args:
            self.default_panel = False

        if "--background" in self.args:
            self.exclusive = False

        self.default_panel = True
        with open(self.topbar_config, "r") as f:
            panel_toml = toml.load(f)
            for p in panel_toml:
                if "bottom" == p:
                    self.exclusive = True
                    if panel_toml[p]["Exclusive"] == "False":
                        self.exclusive = False

                    position = panel_toml[p]["position"]
                    self.bottom_panel = CreatePanel(
                        app, "BOTTOM", position, self.exclusive, 48, 0, "BottomBar"
                    )
                if "right" == p:
                    self.exclusive = True
                    if panel_toml[p]["Exclusive"] == "False":
                        self.exclusive = False
                    position = panel_toml[p]["position"]
                    self.right_panel = CreatePanel(
                        app, "RIGHT", position, self.exclusive, 0, 32, "RightBar"
                    )
                if "left" == p:
                    self.exclusive = True
                    if panel_toml[p]["Exclusive"] == "False":
                        self.exclusive = False
                    position = panel_toml[p]["position"]
                    self.left_panel = CreatePanel(
                        app, "LEFT", position, self.exclusive, 0, 48, "LeftBar"
                    )
                if "top" == p:
                    self.exclusive = True
                    if panel_toml[p]["Exclusive"] == "False":
                        self.exclusive = False
                    position = panel_toml[p]["position"]
                    self.top_panel = CreatePanel(
                        app,
                        "TOP",
                        position,
                        self.exclusive,
                        self.monitor_width,
                        24,
                        "TopBar",
                    )
                if "top_background" == p:
                    self.exclusive = True
                    if panel_toml[p]["Exclusive"] == "False":
                        self.exclusive = False
                    position = panel_toml[p]["position"]
                    self.top_panel_background = CreatePanel(
                        app,
                        "TOP",
                        position,
                        self.exclusive,
                        self.monitor_width,
                        24,
                        "TopBarBackground",
                    )

    def mullvad_status(self):
        """
        Check the status of the Mullvad VPN and update the menu label accordingly.

        This function checks the status of the Mullvad VPN by searching for files in
        the directory "/sys/class/net" that start with either "wg" or "tun".
        If the interface is "tun", it checks for the presence of "-mullvad" as well.
        It updates the label of the VPN menu item based on the status.

        Returns:
            bool: True if the function executes successfully.
        """
        vpn_menu = self.menus.get("VPN")  # Retrieve VPN menu

        if vpn_menu is None:
            return False

        net_files = os.listdir("/sys/class/net")

        is_mullvad_active = any(
            (file.startswith("wg") or file.startswith("tun")) for file in net_files
        )

        if not is_mullvad_active:
            is_mullvad_active = any(
                file.startswith("tun") and "-mullvad" in file for file in net_files
            )

        if is_mullvad_active:
            vpn_menu.set_icon_name("mullvad-symbolic")
        else:
            vpn_menu.set_icon_name("stock_disconnect")

        return True

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

    def create_widgets(self, orientation, class_style):
        """
        Create widgets based on the specified orientation and class style.

        This function creates widgets, such as a dockbar and workspace buttons, based on the specified
        orientation and class style, and returns the created widgets.

        Args:
            orientation (str): The orientation of the widgets (e.g., "horizontal", "vertical").
            class_style (str): The class style of the widgets.

        Returns:
            tuple: A tuple containing the created dockbar and workspace buttons.
        """
        dockbar = self.utils.CreateFromAppList(
            self.dockbar_config, orientation, class_style
        )
        workspace_buttons = self.utils.CreateFromAppList(
            self.workspace_list_config, orientation, class_style
        )
        return dockbar, workspace_buttons

    def todo_txt(self):
        """
        Update the label of the TODO button with the last line from the TODO.txt file.

        This function reads the last line from the TODO.txt file and updates the label of the TODO button
        with the content of the last line.

        Returns:
            bool: Always returns True.
        """
        # Define the path to the TODO.txt file
        todo_filepath = os.path.join(self.home, "Documentos", "todo.txt")

        # Read the last line from the TODO.txt file
        last_line = open(todo_filepath, "r").readlines()[-1]

        # Update the label of the TODO button with the content of the last line
        self.todo_button.set_label(last_line.strip())

        return True

    def on_button_press_event(self, _, event):
        """
        Handle the button press event.

        This function handles the button press event by checking the type of the event and the button
        that was pressed, and then performing the corresponding action.

        Args:
            widget: The widget that emitted the event.
            event: The event object containing information about the event.

        Returns:
            None
        """
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            return True

    def right_side_middle_click(self, *_):
        """
        Handle the middle click gesture on the right side.

        This function handles the middle click gesture on the right side by executing the "kitty" command
        to open the Kitty terminal emulator.

        Args:
            gesture: The gesture object.
            data: Additional data (unused).
            x: The x-coordinate of the click.
            y: The y-coordinate of the click.

        Returns:
            None
        """
        
        self.sock.toggle_expo()
        # Popen("kitty".split())

    def scroll_event(self, _, _dx, dy):
        """
        Handle the scroll event.

        This function handles the scroll event by checking the direction of the scroll and adjusting
        the volume accordingly using the "pactl" command.

        Args:
            controller: The controller object.
            _dx: The horizontal delta (unused).
            dy: The vertical delta representing the direction and speed of the scroll.

        Returns:
            None
        """
        # Check the direction of the scroll and adjust the volume using the "pactl" command
        if dy > 0:
            self.utils.run_app("pactl -- set-sink-volume @DEFAULT_SINK@  -8%")
        else:
            self.utils.run_app("pactl -- set-sink-volume @DEFAULT_SINK@  +8%")

        with pulsectl.Pulse("volume-increaser") as pulse:
            # Iterate through all the audio sinks
            for sink in pulse.sink_list():
                # Check if the sink is currently running (active)
                if "running" in str(sink.state):
                    # Calculate the volume percentage and round it to the nearest whole number
                    volume = round(sink.volume.values[0] * 100)

                    # Update the volume label with the current volume percentage
                    self.tbvol.set_label("{0}%".format(volume))
                    self.vol_slider.set_value(volume)

    def left_gesture_left_click(self, *_):
        # data format is (self, gesture, data, x, y)
        cmd = self.panel_cfg["left_side_gestures"]["left_click"]
        self.utils.run_app(cmd, True)

    def left_gesture_right_click(self, *_):
        self.wf_utils.go_next_workspace_with_views()
        # cmd = self.panel_cfg["left_side_gestures"]["right_click"]
        # self.utils.run_app(cmd, True)

    def left_gesture_middle_click(self, *_):
        
        self.sock.toggle_expo()
        # cmd = self.panel_cfg["left_side_gestures"]["middle_click"]
        # self.utils.run_app(cmd, True)

    def center_gesture_left_click(self, *_):
        
        self.sock.toggle_expo()
        # cmd = self.panel_cfg["center_side_gestures"]["left_click"]
        # self.utils.run_app(cmd, True)

    def center_gesture_middle_click(self, *_):
        
        self.sock.toggle_expo()
        # cmd = self.panel_cfg["center_side_gestures"]["middle_click"]
        # self.utils.run_app(cmd, True)

    def center_gesture_right_click(self, *_):
        self.wf_utils.go_next_workspace_with_views()
        # cmd = self.panel_cfg["left_side_gestures"]["right_click"]
        # self.utils.run_app(cmd, True)

    def right_gesture_left_click(self, *_):
        cmd = self.panel_cfg["right_side_gestures"]["left_click"]
        self.utils.run_app(cmd, True)

    def right_gesture_right_click(self, *_):
        
        self.sock.toggle_expo()
        # cmd = self.panel_cfg["right_side_gestures"]["right_click"]
        # self.utils.run_app(cmd, True)

    def right_gesture_middle_click(self, *_):
        
        self.sock.toggle_expo()
        # cmd = self.panel_cfg["right_side_gestures"]["middle_click"]
        # self.utils.run_app(cmd, True)

    def create_simple_action(self):
        """
        Create a simple action to run a command.

        This function creates a simple action named "run-command" that takes a string parameter.
        It connects the "activate" signal of the action to the menu_run_action method.

        Args:
            None

        Returns:
            None
        """
        # Create a simple action with the specified name and parameter type
        action = Gio.SimpleAction(
            name="run-command", parameter_type=GLib.VariantType("s")
        )

        # Connect the "activate" signal of the action to the menu_run_action method
        action.connect("activate", self.menu_run_action)

        # Add the action to the application
        app.add_action(action)

    def create_menu_item(self, menu, name, cmd):
        """
        Create a menu item with the specified name and command.

        This function creates a menu item with the specified name and command,
        sets its action to "app.run-command" with the command as the target value,
        and appends the menu item to the specified menu.

        Args:
            menu (Gio.Menu): The menu to which the menu item should be appended.
            name (str): The name of the menu item.
            cmd (str): The command associated with the menu item.

        Returns:
            None
        """
        # Create a new menu item with the specified name
        menuitem = Gio.MenuItem.new(name, None)

        # Set the action of the menu item to "app.run-command" with the command as the target value
        menuitem.set_action_and_target_value("app.run-command", GLib.Variant("s", cmd))
        # menuitem.set_icon("audio-card-symbolic")

        # Append the menu item to the specified menu
        menu.append_item(menuitem)

    def create_new_menu(self):
        """
        Create a new menu based on the configuration file.

        This function reads the menu configuration from a TOML file,
        creates a new menu based on the configuration, and returns a dictionary
        containing the menu buttons associated with the created menus.

        Args:
            None

        Returns:
            dict: A dictionary containing the menu buttons associated with the created menus.
        """
        # Read the menu configuration from the specified file
        with open(self.menu_config, "r") as f:
            menu_toml = toml.load(f)

        # Initialize a dictionary to store the menu buttons
        menu_buttons = {}

        # Iterate through the menu configuration and create the corresponding menus and menu items
        for m in menu_toml:
            if m == "icons":
                continue
            menu = Gio.Menu()
            btn = Gtk.MenuButton(label=m)
            btn.set_always_show_arrow(False)
            btn.set_can_focus(False)
            # if no icon is specified in [icons] from menu.toml then use Label instead
            try:
                btn.set_icon_name(menu_toml["icons"][m])
            except Exception as e:
                print(e)
                btn.set_label(label=m)

            btn.set_menu_model(menu)
            submenu = None
            dsubmenu = {}
            menu_buttons[m] = btn
            self.create_simple_action()
            for item in menu_toml[m].values():
                name = item[0]["name"]
                cmd = item[0]["cmd"]
                if "submenu" in item[0]:
                    submenu_label = item[0]["submenu"]
                    submenu = dsubmenu.get(submenu_label)
                    if submenu is None:
                        submenu = Gio.Menu()
                        dsubmenu[submenu_label] = submenu
                    self.create_menu_item(submenu, name, cmd)
                else:
                    self.create_menu_item(menu, name, cmd)
            if dsubmenu:
                [menu.append_submenu(k, dsubmenu[k]) for k in dsubmenu.keys()]

        # Return the dictionary containing the menu buttons
        return menu_buttons

    def sigkill_activewindow(self, *_):
        active_window = self.get_wayland_active_window()
        pid = active_window.pid
        cmd = "kill -9 {0}".format(pid)
        self.utils.run_app(cmd)

    def menu_run_action(self, action, param):
        self.utils.run_app(param.get_string())

    def load_topbar_config(self):
        with open(self.topbar_config, "r") as f:
            return toml.load(f)

    def copy_to_clipboard(self, *_):
        # lazy to not use wl-copy
        active_window = self.get_wayland_active_window()
        self.utils.run_app("wl-copy {0}".format(active_window.pid))
        self.utils.run_app("kitty --hold -- htop -p {0}".format(active_window.pid))

    def bluetooth_manager(self):
        bt = BluetoothDashboard()
        bt = bt.create_menu_popover_bluetooth(self, app)
        bt.set_icon_name("preferences-bluetooth-symbolic")
        return bt

    def system_dashboard(self):
        s = SystemDashboard()
        s = s.create_menu_popover_system(self, app)
        s.set_icon_name("shutdown_highlight-symbolic")
        return s

    def volume_slider(self):
        self.vol_slider_box = Gtk.Box()
        self.icon_vol_slider = SoundCardDashboard()
        self.icon_vol_slider = self.icon_vol_slider.create_menu_popover_soundcard(
            self, app
        )
        self.icon_vol_slider.set_icon_name("audio-volume-high-symbolic")
        self.vol_slider_box.append(self.icon_vol_slider)
        self.vol_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.vol_slider.set_range(0, 100)
        self.vol_slider_box.add_css_class("vol_slider_box")
        self.vol_slider.set_format_value_func()
        # self.vol_slider.set_draw_value(True)
        self.vol_slider.set_value(50)
        self.vol_slider.set_value_pos(Gtk.PositionType.RIGHT)
        self.vol_slider.connect("value-changed", self.on_slider_changed)
        self.vol_slider_box.append(self.vol_slider)
        return self.vol_slider_box

    def on_slider_changed(self, slider):
        vol = int(slider.get_value())

        if self.is_volume_muted:
            self.utils.run_app("pactl set-sink-mute @DEFAULT_SINK@ false")
            self.icon_vol_slider.set_icon_name("audio-volume-high-symbolic")

        self.utils.run_app("pactl -- set-sink-volume @DEFAULT_SINK@ {0}%".format(vol))
        self.vol_slider.set_value(vol)

        with pulsectl.Pulse("volume-increaser") as pulse:
            # Iterate through all the audio sinks
            for sink in pulse.sink_list():
                # Check if the sink is currently running (active)
                if "running" in str(sink.state):
                    # Calculate the volume percentage and round it to the nearest whole number
                    volume = round(sink.volume.values[0] * 100)

                    # Update the volume label with the current volume percentage
                    self.tbvol.set_label("{0}%".format(volume))
                    if volume == 0:
                        self.icon_vol_slider.set_icon_name(
                            "audio-volume-muted-symbolic"
                        )
                    if volume < 35:
                        self.icon_vol_slider.set_icon_name("audio-volume-low-symbolic")
                    if volume >= 35 and volume <= 75:
                        self.icon_vol_slider.set_icon_name(
                            "audio-volume-medium-symbolic"
                        )
                    if volume > 75:
                        self.icon_vol_slider.set_icon_name("audio-volume-high-symbolic")

    def sink_input_info(self):
        pactl = "pactl list sink-inputs".split()
        sink_inputs = check_output(pactl).decode()
        sinklist = sink_inputs.split("Sink Input #")
        info = {}
        info["sinklist"] = sinklist
        return info

    def is_volume_muted(self):
        volume_state = check_output(
            "pactl get-sink-mute @DEFAULT_SINK@".split()
        ).decode()
        if "no" in volume_state.split()[-1]:
            return False
        else:
            return True

    def on_toggle_volume(self, *_):
        # Creating clock label with current date and time
        self.soundcard_dashboard = PopoverDashboard()
        self.soundcard_dashboard = (
            self.soundcard_dashboard.create_menu_popover_dashboard(self, app)
        )

        # self.utils.run_app("pactl set-sink-mute @DEFAULT_SINK@ toggle")
        # if self.is_volume_muted():
        #     self.icon_vol_slider.set_icon_name("audio-volume-high-symbolic")
        # else:
        #     self.icon_vol_slider.set_icon_name("stock_volume-mute")

    def toggle_mute_from_sink(self, *_):
        
        title = self.sock.get_focused_view()["title"]
        title = self.utils.filter_utf8_for_gtk(title)
        info = self.sink_input_info()
        sinklist = info["sinklist"]
        for sink in sinklist:
            if title.lower() in sink.lower():
                sink = sink.split("\n")[0]
                self.utils.run_app("pactl set-sink-input-mute {0} toggle".format(sink))

    def notify_client(self, *_):
        self.utils.run_app("swaync-client -t")

    def disk_usage_by_pid(self):
        
        pid = self.wf_utils.get_focused_view_pid()
        p = psutil.Process(pid)
        io_counters = p.io_counters()
        disk_usage_process = io_counters[2] + io_counters[3]  # read_bytes + write_bytes
        return int(round(disk_usage_process / (1024**2), 2))

    def manage_window_notes(self, *_):
        """
        Manage notes for the active window.

        This function retrieves information about the active window, such as its initial title
        and window class, and updates a configuration file with this information. It also
        manages the creation and opening of a Markdown file for notes related to the window.

        Args:
            *_: Additional arguments (unused).

        Returns:
            None
        """
        # Retrieve information about the active window
        
        view = self.sock.get_view(self.last_view_toplevel_focused)
        title = view["title"]
        title = self.utils.filter_utf8_for_gtk(title)
        wm_class = view["app-id"].lower()
        initial_title = title.split()[0].lower()

        # Adjust the window class based on specific conditions
        if "firefox" in wm_class and "." in title:
            wm_class = title.split()[0]
        if wm_class == "kitty":
            wm_class = title.split()[0]
        if wm_class == "gnome-terminal-server":
            wm_class = title.split()[0]

        # Load existing window notes from the configuration file
        with open(self.window_notes_config, "r") as config_file:
            existing_notes = toml.load(config_file)

        # Create a new entry for the active window and update the configuration
        new_entry = {wm_class: {"initial_title": initial_title, "title": title}}
        updated_notes = ChainMap(new_entry, existing_notes)

        # Save the updated notes back to the configuration file
        with open(self.window_notes_config, "w") as config_file:
            toml.dump(updated_notes, config_file)

        # Define the path and command for the Markdown file related to the window
        filepath = f"/home/neo/Notes/{wm_class}.md"
        cmd = f"marktext {filepath}"

        # Create the Markdown file if it doesn't exist
        if not os.path.isfile(filepath):
            Path(filepath).touch()

        # run the Markdown editor application
        self.utils.run_app(cmd)

    def output_loop(self, output, label):
        """
        Update the label with the output of a command.

        This function executes the specified command, captures its output, and updates
        the label widget with the captured output.

        Args:
            output (str): The command whose output will be displayed in the label.
            label (Gtk.Label): The label widget to update with the command output.

        Returns:
            bool: True if the label content is successfully updated, False otherwise.
        """  # Execute the specified command and capture its output
        command_output = check_output(output.split()).decode().replace("\n", "")

        # Set the label content with the captured output using markup
        separator = " "
        label.set_markup(command_output + separator)

        # Remove the previously scheduled source for single execution
        GLib.Source.remove(self.exec_once)

        # Return True to indicate successful update
        return True

    def create_cmd_label(self, output, position, css_class, refresh):
        """
        Create and configure a label widget to display command output.

        This function creates a label widget with the specified CSS class and adds it to a box container
        based on the specified position. It also schedules periodic updates of the label content.

        Args:
            output (str): The command whose output will be displayed in the label.
            position (str): The position where the label should be added ('left', 'right', or 'center').
            css_class (str): The CSS class to apply to the label and the box container.
            refresh (int): The interval in milliseconds for refreshing the label content.

        Returns:
            None
        """
        # Create a new label widget
        label = Gtk.Label()

        # Create a new box container
        box = Gtk.Box()

        # Configure the box container properties
        box.set_halign(Gtk.Align.END)
        box.set_hexpand(False)
        box.set_baseline_position(Gtk.BaselinePosition.BOTTOM)

        # Add the specified CSS class to the box container and the label
        box.add_css_class(css_class)
        label.add_css_class(css_class)

        # Add the label to the box container
        box.append(label)

        # Determine the position to add the box container and label
        if position == "left":
            self.top_panel_box_left.append(box)
        elif position == "right":
            self.top_panel_box_systray.append(box)
        elif position == "center":
            self.clock_box.append(box)

        # Schedule the periodic updates of the label content
        self.exec_once = GLib.timeout_add(
            refresh, lambda: self.output_loop(output, label)
        )
        GLib.timeout_add(refresh, lambda: self.output_loop(output, label))

    def cmd_output(self):
        """
        Read command settings from a configuration file and create corresponding command labels.

        This function reads command settings from a TOML configuration file, iterates through each setting,
        and creates and configures the corresponding command label using the create_cmd_label function.

        Args:
            None

        Returns:
            None
        """
        # Read command settings from the configuration file
        with open(self.cmd_config, "r") as config_file:
            cmd_settings = toml.load(config_file)

        # Iterate through each command setting and create/configure the corresponding command label
        for label_key in cmd_settings:
            output = cmd_settings[label_key]["cmd"]
            position = cmd_settings[label_key]["position"]
            refresh = cmd_settings[label_key]["refresh"]
            css_class = cmd_settings[label_key]["css_class"]

            # Create and configure the command label with the specified settings
            self.create_cmd_label(output, position, css_class, refresh)

    def volume_watch(self):
        """
        Watch for changes in the volume and update the volume and card labels accordingly.

        This function uses the `pulsectl` library to monitor the volume and updates the labels
        with the current volume percentage and the description of the active audio sink.

        """
        # Initialize PulseAudio client
        with pulsectl.Pulse("volume-increaser") as pulse:
            # Iterate through all the audio sinks
            for sink in pulse.sink_list():
                # Check if the sink is currently running (active)
                if "running" in str(sink.state):
                    # Calculate the volume percentage and round it to the nearest whole number
                    volume = round(sink.volume.values[0] * 100)

                    # Update the volume label with the current volume percentage
                    self.tbvol.set_label("{0}%".format(volume))

                    # Update the card label with the description of the active audio sink
                    self.tbcard.set_label("{0}".format(sink.description))

    def update_title_topbar(self):
        try:
            title = self.wf_utils.get_focused_view_title()
            title = self.utils.filter_utf8_for_gtk(title)
            initial_title = title.split()[0]
            if title == "":
                return True
            wclass = self.wf_utils.get_focused_view_app_id()

            title = self.modify_title(title)

            # Limit the title length
            title = title[: self.window_title_topbar_length]

            # Apply custom icon if available
            custom_icon = self.apply_custom_icon(wclass)
            if custom_icon:
                wclass = custom_icon

            # Update title and icon
            self.update_title_and_icons(title, wclass, initial_title)
        except Exception as e:
            print(e)
        return True

    def has_active_window_changed(self):
        # Get the currently active window
        active_window = self.get_wayland_active_window()

        # Extract the address of the active window
        address = active_window.address

        # Check if the panel has just started; if yes, update the widgets
        # This ensures that the title from the active window updates when the panel starts
        if self.active_window_changed is None:
            if self.waypanel_started_now:
                self.active_window_changed = address
                self.waypanel_started_now = False
                return True

        # Check if the active window address has changed
        if self.active_window_changed != address:
            self.active_window_changed = address
            return True
        else:
            # No change in the active window
            return False

    def update_widgets(self, title, wm_class, initial_title, pid, workspace_id):
        is_fullscreen = self.wf_utils.is_focused_view_fullscreen()
        if is_fullscreen:
            return True
        # Modify title based on certain patterns
        title = self.modify_title(title)
        # Limit the title length
        title = title[: self.window_title_topbar_length]

        self.update_title_and_icons(title, wm_class, initial_title)

        gws = netifaces.gateways()
        if gws["default"]:
            gw = list(gws["default"].values())[0][-1]
            if self.is_interface_up(gw):
                self.tbnet.set_icon_name("network-wired-symbolic")
                self.tbnet.set_label(gw)
        else:
            self.tbnet.set_icon_name("network-wired-unavailable")
            self.tbnet.set_label("Disconnected")

        # Fetch and format process information
        mem_usage, exe, cpu_usage = self.fetch_process_info(pid)
        # Update widget labels and icons
        self.update_widget_labels(workspace_id, pid, wm_class, mem_usage, exe)

    def extract_widget_info(self, active_window):
        """Extract and return widget-related information."""
        title = active_window.title[0:100]
        title = self.utils.filter_utf8_for_gtk(title)
        workspace_id = active_window.workspace_id
        pid = active_window.pid
        wclass = active_window.initial_wm_class.lower()
        initial_title = active_window.initial_title
        return title, workspace_id, pid, wclass, initial_title

    def apply_custom_icon(self, wclass):
        """Apply custom icon if available."""
        panel_cfg = self.panel_cfg["change_icon_title"]
        if wclass in panel_cfg:
            return panel_cfg[wclass]

    def is_interface_up(self, interface):
        addr = netifaces.ifaddresses(interface)
        return netifaces.AF_INET in addr

    def fetch_process_info(self, pid):
        """Fetch and return process information."""
        if pid not in self.psutil_store.keys():
            process = psutil.Process(pid)
            self.psutil_store[pid] = process
        mem_usage = self.utils.convert_size(
            int(self.psutil_store[pid].memory_info().rss)
        )
        exe = self.psutil_store[pid].exe()
        cpu_usage = int(self.psutil_store[pid].cpu_percent())
        return mem_usage, exe, cpu_usage

    def set_cpu_usage(self):
        
        pid = self.sock.get_focused_view()["pid"]
        allow_to_set_zero = False
        """Fetch and return process information."""
        if pid not in self.psutil_store.keys():
            process = psutil.Process(pid)
            self.psutil_store[pid] = process
        cpu_usage = int(self.psutil_store[pid].cpu_percent())

        # if there is 4 seconds with 0% them we allow to the label
        # if not, this would spam 0% randomly
        if self.set_cpu_usage_state.count(0) > 4:
            allow_to_set_zero = True
            self.set_cpu_usage_state = []
        else:
            allow_to_set_zero = False

        self.set_cpu_usage_state.append(cpu_usage)

        if allow_to_set_zero is True or cpu_usage > 0:
            self.tbcpusage.set_label("CPU: {0}%".format(cpu_usage))
            print(self.tbcpusage.get_label())

        if self.is_scale_active:
            return True
        else:
            return False

    def modify_title(self, title):
        """Modify title based on certain patterns."""
        title = self.utils.filter_utf8_for_gtk(title)
        if "." in title:
            parts = title.split(" ", 1)
            if parts[0].startswith("www."):
                title = parts[0][4:]  # Assuming "www." always has a length of 4
            else:
                title = parts[0]

        if " — " in title:
            title = title.split(" — ", 1)[0]

        return title

    def update_title_and_icons(self, title, wm_class, initial_title):
        """Update title and icons."""
        # some classes and initial titles has whitespaces which will lead to not found icons
        title = self.utils.filter_utf8_for_gtk(title)
        icon = self.get_icon(wm_class, initial_title, title)
        if icon:
            self.window_title.set_icon_name(icon)
            self.tbclass.set_icon_name(icon)

        # Set window label
        self.window_title.set_label(title)

    def update_widget_labels(self, workspace_id, pid, wclass, mem_usage, exe):
        """Update widget labels."""

        # Only update labels related to window details if the window has changed
        self.tbpid.set_label("PID: {0}".format(pid))
        self.tbclass.set_label("{0}".format(wclass))
        # self.tbexe.set_label("Exe: {0}".format(exe))
        self.tbdiskusage.set_label("Disk: {0}MB".format(self.disk_usage_by_pid()))

        # Update labels for general information
        self.tbworkspace.set_label("Workspace: {0}".format(workspace_id))
        # self.tbcpusage.set_label("CPU: {0}%".format(cpu_usage))
        self.tbmemusage.set_label("MEM: {0}".format(mem_usage))

        # Update volume information
        self.volume_watch()




sock = WayfireSocket()
home = os.path.expanduser("~")
config_path = os.path.join(home, ".config/waypanel")
panel_config = os.path.join(config_path, "panel.toml")
with open(panel_config) as panel_config:
    config = toml.load(panel_config)
monitor_name = None
try:
    monitor_name = config["monitor"]["name"]
except KeyError:
    print("configure [monitor] in .config/panel.toml")
    sys.exit()

argv = sys.argv
if len(argv) > 0:
    monitor_name = argv[0].strip()

app = Panel(application_id="com.waypanel.{0}.GtkApplication".format(monitor_name))
app.run(None)
sock.watch()
while True:
    msg = sock.read_message()
    if "event" in msg:
        event = msg["event"]
        if monitor_name == msg["output"]["name"]:
            if event == "output-added":
                app.run(None) 


