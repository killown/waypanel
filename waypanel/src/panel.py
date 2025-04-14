#!/usr/bin/env python3
import datetime
import os
import sys
import time
from collections import ChainMap
from pathlib import Path
from subprocess import Popen, check_output
import importlib
import pkgutil
import pulsectl
import soundcard as sc
import toml
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from wayfire import WayfireSocket as OriginalWayfireSocket
from wayfire.core.template import get_msg_template
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.extra.stipc import Stipc

from waypanel.src.core.create_panel import (
    CreatePanel,
)
from waypanel.src.core.utils import Utils
from waypanel.src.core.utils import Utils as utils
from waypanel.src.ipc_server.ipc_client import WayfireClientIPC
from waypanel.src.plugins.dockbar import Dockbar

# to get the gtk and gdk completions
# pip install pygobject-stubs --no-cache-dir --config-settings=config=Gtk4,Gdk


class WayfireSocket(OriginalWayfireSocket):
    def hide_view(self, view_id):
        message = get_msg_template("hide-view/hide")
        message["data"]["view-id"] = view_id
        self.send_json(message)

    def unhide_view(self, view_id):
        message = get_msg_template("hide-view/unhide")
        message["data"]["view-id"] = view_id
        self.send_json(message)


class Panel(Adw.Application):
    def __init__(self, logger, application_id=None):
        super().__init__(application_id=application_id)
        """
        Initializes the application and sets up required configurations and components.

        Args:
            application_id (str): The application ID.
        """
        self.logger = logger
        self.panel_instance = None
        # Initialize utilities and connect to activation event
        self._initialize_utilities()
        self.connect("activate", self.on_activate)

        # Setup panel boxes and configuration paths
        self._setup_panel_boxes()
        self._setup_config_paths()

        # Initialize variables and configurations
        self.toggle_mute = {}
        self.volume = 0
        self.args = sys.argv
        self.source_id = None  # Store the source ID for the GLib.timeout

        # Load configurations
        self.panel_cfg = self.load_topbar_config()

        # Initialize Wayfire components
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.ipc_client = WayfireClientIPC(self.handle_event)
        self.ipc_client.wayfire_events_setup("/tmp/waypanel.sock")

        self.fd = None
        self.utils = utils()
        self.stipc = Stipc(self.sock)
        self.get_icon = self.utils.get_icon

        # Initialize state variables
        self.active_window_changed = None
        self.notifications = []
        self.popover_bookmarks = None
        self.popover_clipboard = None
        self.set_cpu_usage_state = []
        self.clipboard_text_copy = None
        self.waypanel_started_now = True
        self.view_title_top_panel = None
        self.active_window = None
        self.last_toplevel_focused_view = None
        self.last_focused_output = None
        self.is_scale_active = None
        self.focused_output = None
        self.vol_slider = None
        self.dockbar_pending_events = []
        self.icon_vol_slider = None
        self.floating_volume_plugin = None
        self.workspace_empty = None
        self.timeout_ids = {}
        self.turn_off_monitors_timeout = None
        self.signal_view_destroyed = False
        self.was_last_focused_view_maximized = None
        self.previous_workspace = {}
        self.request_switch_keyboard_on_demand_to_none = None
        self.maximize_button = None
        self.minimize_button = None
        self.monitor = None
        self.get_focused_output = None
        self.panel_config_loaded = self.load_config()
        config = self.panel_config_loaded

        self.simple_title_enabled = config["panel"]["views"]["tilling"]
        self.maximize_views_on_expo_enabled = config["panel"]["views"][
            "maximize_views_on_expo"
        ]

        # Set monitor dimensions
        monitor = next(
            (output for output in self.sock.list_outputs() if "-1" in output["name"]),
            self.sock.list_outputs()[0],
        )
        self.monitor_width, self.monitor_height = (
            monitor["geometry"]["width"],
            monitor["geometry"]["height"],
        )

        if "monitor" in config:
            self.monitor_width, self.monitor_height = (
                config["monitor"]["width"],
                config["monitor"]["height"],
            )

        self.monitor_name = self.sock.list_outputs()[0]["name"]
        if "monitor" in config and "name" in config["monitor"]:
            self.monitor_name = config["monitor"]["name"]
        else:
            self.logger.info("Using the first monitor from the list.")

    def set_panel_instance(self, panel_instance):
        self.panel_instance = panel_instance

    def _initialize_utilities(self):
        """Initialize utility functions and properties."""
        self.utils = Utils(application_id="com.github.utils")

    def _setup_panel_boxes(self):
        """Setup panel boxes and related configurations."""
        self.top_panel_box_left = Gtk.Box()
        self.top_panel_box_systray = Gtk.Box()
        self.top_panel_box_for_buttons = Gtk.Box()
        self.top_panel_box_widgets_left = Gtk.Box()
        self.top_panel_box_left.append(self.top_panel_box_widgets_left)
        self.top_panel_box_right = Gtk.Box()
        self.top_panel_grid_right = Gtk.Grid()
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

        self.top_panel_box_center = Gtk.Box()
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
        self.dock = Dockbar(application_id="com.github.dockbar", logger=self.logger)
        self.top_panel_box_center.set_halign(Gtk.Align.CENTER)
        self.top_panel_box_center.set_valign(Gtk.Align.CENTER)
        self.top_panel_box_center.set_hexpand(False)

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        config_paths = self.utils.setup_config_paths()
        # Set instance variables from the dictionary
        self.home = config_paths["home"]
        self.waypanel_cfg = os.path.join(self.home, ".config/waypanel/waypanel.toml")
        self.scripts = config_paths["scripts"]
        self.config_path = config_paths["config_path"]
        self.style_css_config = config_paths["style_css_config"]
        self.cache_folder = config_paths["cache_folder"]

    def on_activate(self, app):
        """
        Initializes the shell and sets up all required components.

        Args:
            app: The application instance.
        """
        # Initialize monitor dimensions and UI components
        self.cmd_output()
        self.close_fullscreen_buttons()
        self.right_position_launcher_topbar()
        self.setup_panels()
        self.setup_panel_buttons()

        # Verify required plugins are enabled
        required_plugins = {
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
        }
        enabled_plugins = set(
            self.sock.get_option_value("core/plugins")["value"].split()
        )

        missing_plugins = required_plugins - enabled_plugins
        if missing_plugins:
            self.logger.error(
                f"\n\033[91mERROR:\033[0m The following plugins are required to start the shell: {missing_plugins}"
            )
            self.logger.info(f"Required Plugin List: {required_plugins}")
            sys.exit()

        self.menus = self.create_new_menu()
        self.setup_menus()

        self.load_plugins()

        # Hide desktop-environment views with unknown type
        for view in self.sock.list_views():
            if view["role"] == "desktop-environment" and view["type"] == "unknown":
                self.hide_view_instead_closing(view, ignore_toplevel=True)

        self.get_focused_output = self.sock.get_focused_output()

    def load_config(self):
        if not hasattr(self, "_cached_config"):
            with open(self.waypanel_cfg, "r") as f:
                self._cached_config = toml.load(f)
        return self._cached_config

    def check_widgets_ready(self):
        if (
            self.utils.is_widget_ready(self.top_panel_box_left)
            and self.utils.is_widget_ready(self.top_panel_box_widgets_left)
            and self.utils.is_widget_ready(self.top_panel_box_right)
            and self.utils.is_widget_ready(self.top_panel_box_systray)
            and self.utils.is_widget_ready(self.top_panel_box_center)
            and self.utils.is_widget_ready(self.top_panel_box_full)
        ):
            # Apply CSS classes
            self.top_panel_box_left.add_css_class("top_panel_box_left")
            self.top_panel_box_widgets_left.add_css_class("top_panel_box_widgets_left")
            self.top_panel_box_right.add_css_class("top_panel_box_right")
            self.top_panel_box_systray.add_css_class("top_panel_box_systray")
            self.top_panel_box_center.add_css_class("top_panel_box_center")
            self.top_panel_box_full.add_css_class("top_panel_box_full")
            return False
        else:
            # Retry after a delay
            GLib.timeout_add(1, self.check_widgets_ready)
            return True

    def do_activate(self):
        # activate auto start apps
        # GLib.timeout_add(4000, self.autostart)
        self.load_css_from_file()
        # Start monitoring CSS file for changes
        self.monitor = Gio.File.new_for_path(self.style_css_config).monitor(
            Gio.FileMonitorFlags.NONE, None
        )
        self.monitor.connect("changed", self.on_css_file_changed)
        self.check_widgets_ready()
        # setup gestures after widgets is ready
        self.setup_gestures()
        self.show_panels()

    def autostart(self):
        # auto start some apps in systray
        autostart = {"thunderbird": "thunderbird"}
        for app in autostart.keys():
            self.stipc.run_cmd(app)
            counter = 0
            while counter <= 10:  # 10 seconds limit
                view = [
                    i
                    for i in self.sock.list_views()
                    if autostart[app].lower() in i["app-id"].lower()
                ]
                if view:
                    self.hide_view_instead_closing(view[-1])
                    break
                counter += 1
                time.sleep(1)

    def load_plugins(self):
        """Dynamically load all plugins from the src.plugins package.
        Plugins that return False for their position or are disabled via ENABLE_PLUGIN
        or listed in the `disabled` field in waypanel.toml will be skipped.
        Additionally, update the [plugins] section in waypanel.toml to reflect the valid plugins."""

        # Path to the configuration file
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")

        # Load the TOML configuration
        try:
            if not os.path.exists(waypanel_config_path):
                self.logger.error(
                    f"Configuration file not found at '{waypanel_config_path}'."
                )
                return

            with open(waypanel_config_path, "r") as f:
                config = toml.load(f)

            # Ensure the [plugins] section exists
            if "plugins" not in config:
                config["plugins"] = {"list": "", "disabled": ""}

            # Parse the disabled plugins list
            disabled_plugins = set(config["plugins"].get("disabled", "").split())

        except Exception as e:
            self.logger.error(f"Failed to load configuration file: {e}")
            return

        # Initialize lists to track valid plugins
        valid_plugins = []
        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        plugin_names = [name for _, name, _ in pkgutil.iter_modules([plugin_dir])]
        plugin_metadata = []

        # Load plugin metadata
        for module_name in plugin_names:
            start_time = time.time()  # Start timing

            try:
                # Skip plugins listed in the `disabled` field
                if module_name in disabled_plugins:
                    self.logger.info(
                        f"Skipping plugin listed in 'disabled': {module_name}"
                    )
                    continue

                module = importlib.import_module(f"waypanel.src.plugins.{module_name}")

                # Check if the plugin has required functions
                if hasattr(module, "position") and hasattr(module, "initialize_plugin"):
                    # Check if the plugin is enabled via ENABLE_PLUGIN
                    is_plugin_enabled = getattr(module, "ENABLE_PLUGIN", True)
                    if not is_plugin_enabled:
                        self.logger.info(f"Skipping disabled plugin: {module_name}")
                        continue

                    position_result = module.position()

                    # Handle background-only plugins (position is False)
                    if position_result is False:
                        self.logger.info(
                            f"Initializing background-only plugin: {module_name}"
                        )
                        module.initialize_plugin(self, self)  # Initialize directly
                        valid_plugins.append(module_name)  # Add to valid list
                        elapsed_time = (
                            time.time() - start_time
                        )  # Calculate elapsed time
                        self.logger.info(
                            f"Background plugin '{module_name}' loaded in {elapsed_time:.4f} seconds"
                        )
                        continue

                    # Unpack position and order for regular plugins
                    try:
                        position, order = position_result
                    except (TypeError, ValueError):
                        self.logger.error(
                            f"Module {module_name} returned an invalid position. Skipping."
                        )
                        continue

                    # Validate position
                    if position not in ("left", "right", "center"):
                        self.logger.error(
                            f"Invalid position '{position}' returned by module {module_name}. Skipping."
                        )
                        continue

                    # Add plugin metadata for sorting and initialization
                    plugin_metadata.append((module, position, order))
                    valid_plugins.append(module_name)  # Add to valid list

                else:
                    self.logger.error(
                        f"Module {module_name} is missing required functions. Skipping."
                    )

            except Exception as e:
                elapsed_time = (
                    time.time() - start_time
                )  # Calculate elapsed time even if there's an error
                self.logger.error(
                    f"Failed to load plugin {module_name}: {e} (processed in {elapsed_time:.4f} seconds)"
                )
                continue

            elapsed_time = time.time() - start_time  # Calculate elapsed time
            self.logger.info(
                f"Plugin '{module_name}' processed in {elapsed_time:.4f} seconds"
            )

        # Sort plugins by their `order` value
        plugin_metadata.sort(key=lambda x: x[2])  # Sort by the third element (order)

        # Initialize plugins in sorted order
        for module, position, _ in plugin_metadata:
            start_time = time.time()  # Start timing

            try:
                # Determine the target panel box based on the position
                if position == "left":
                    target_box = self.top_panel_box_left
                elif position == "right":
                    target_box = self.top_panel_box_right
                elif position == "center":
                    target_box = self.top_panel_box_center
                else:
                    self.logger.error(
                        f"Invalid position '{position}' returned by module {module.__name__}. Skipping."
                    )
                    continue

                # Call the `initialize_plugin` function, passing the main app instance
                module.initialize_plugin(self, self)

                elapsed_time = time.time() - start_time  # Calculate elapsed time
                self.logger.info(
                    f"Plugin '{module.__name__}' initialized in {elapsed_time:.4f} seconds"
                )

            except Exception as e:
                elapsed_time = (
                    time.time() - start_time
                )  # Calculate elapsed time even if there's an error
                self.logger.error(
                    f"Failed to initialize plugin {module.__name__}: {e} (processed in {elapsed_time:.4f} seconds)"
                )

        # Update the [plugins] section in the TOML configuration
        config["plugins"]["list"] = " ".join(valid_plugins)
        config["plugins"]["disabled"] = " ".join(disabled_plugins)

        # Save the updated configuration back to the file
        try:
            with open(waypanel_config_path, "w") as f:
                toml.dump(config, f)
        except Exception as e:
            self.logger.error(f"Failed to save updated configuration: {e}")

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
            self.logger.error(f"Error: {e}")

        return folder_location.get_path() if folder_location else None

    @staticmethod
    def handle_exceptions(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.error(f"An error occurred in {func.__name__}: {e}")
                return None

        return wrapper

    def file_exists(self, full_path):
        return os.path.exists(full_path)

    def focused_view_title(self):
        view = self.sock.get_focused_view()
        if view:
            return self.utils.filter_utf_for_gtk(view["title"])

    def handle_event_checks(self, msg, required_keys=None):
        """
        Perform common checks on the event message.
        Args:
            msg (dict): The event message.
            required_keys (list): List of keys that must be present in the message.
        Returns:
            bool: True if the checks pass, False otherwise.
        """
        if not isinstance(msg, dict):
            return False

        if "event" not in msg:
            return False

        if required_keys:
            for key in required_keys:
                if key not in msg:
                    return False

        return True

    def handle_plugin_event(self, msg):
        if not self.handle_event_checks(
            msg, required_keys=["event", "plugin", "state"]
        ):
            return True

        if msg["event"] == "plugin-activation-state-changed":
            if msg["state"]:
                if msg["plugin"] == "expo":
                    self.on_expo_activated()
                elif msg["plugin"] == "scale":
                    self.on_scale_activated()
                elif msg["plugin"] == "move":
                    self.on_moving_view()
            else:
                if msg["plugin"] == "expo":
                    self.on_expo_desactivated()
                elif msg["plugin"] == "scale":
                    self.on_scale_desactivated()

        return True

    def handle_view_event(self, msg):
        # Validate the event using handle_event_checks
        if not self.handle_event_checks(msg, required_keys=["event"]):
            return True

        event = msg["event"]
        view = msg.get("view")

        # Common checks for view-related events
        if view is None:
            return True

        if view["pid"] == -1 or view.get("role") != "toplevel":
            return True

        if view.get("app-id") in ["", "nil"]:
            return True

        # Handle specific events
        if event == "view-unmapped":
            self.on_view_destroyed()
            return True

        if event == "view-title-changed":
            self.on_title_changed()

        elif event == "view-tiled" and view:
            pass  # No action needed here

        elif event == "app-id-changed":
            self.on_app_id_changed()

        elif event == "view-focused":
            self.on_view_role_toplevel_focused(view["id"])
            self.on_view_focused()
            self.last_focused_output = view["output-id"]

        elif event == "view-mapped":
            self.on_view_created(view)

        return True

    def handle_workspace_events(self, msg):
        if "event" not in msg:
            return

    def handle_output_events(self, msg):
        if not self.handle_event_checks(msg, required_keys=["event"]):
            return

        if msg["event"] == "output-gain-focus":
            self.output_get_focus()

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
            self.handle_view_event(msg)
            self.handle_output_events(msg)
            self.handle_plugin_event(msg)
            self.handle_workspace_events(msg)
        except Exception as e:
            self.logger.error(e)

        return True

    def on_view_role_toplevel_focused(self, view_id):
        # last view focus only for top level Windows
        # means that views like layer shell won't have focus set in this var
        # this is necessary for example, if you click in the maximize buttons
        # in the top bar then you need a toplevel window to maximize_last_view
        # if not, it will try to maximize the LayerShell
        # big comment because I am sure I will forget why I did this
        self.last_toplevel_focused_view = view_id

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

    def on_moving_view(self):
        return True

    def on_title_changed(self):
        return

    # created view must start as maximized to auto tilling works
    def on_view_created(self, view):
        #
        # view_id = view["id"]
        # config_path = os.path.join(self.home, ".config/waypanel/")
        # shader = os.path.join(self.config_path, "shaders/border")
        # if os.path.exists(shader):
        #    sock.set_view_shader(view_id, shader)
        return True

    def on_view_destroyed(self):
        return True

    def on_app_id_changed(self):
        return True

    def on_expo_activated(self):
        return True

    def on_expo_desactivated(self):
        # when you move a view in expo, it sometimes will leave workspace area
        # isn't the panel goal to change compositor behaviour
        # but for some a nice quick fix, if you dont need this
        # just disable this function call
        return True

    # events that will make the dockbars clickable or not
    def on_scale_activated(self):
        self.is_scale_active = True

    def on_scale_desactivated(self):
        self.is_scale_active = False

    def on_view_focused(self):
        return

    def list_views(self):
        return self.sock.list_views()

    # this function need a rework, get active monitor
    # remove manual query once you find a way to get active monitor
    def monitor_width_height(self):
        # get monitor info and set the width, height for the panela

        focused_view = self.sock.get_focused_view()
        # there is no monitor focused output while there is no views
        if focused_view:
            output = self.utils.get_monitor_info()
            output = output[self.monitor_name]
            self.monitor_width = output[0]
            self.monitor_height = output[1]

    def setup_menus(self):
        for menu in self.menus.values():
            self.top_panel_box_systray.append(menu)
            self.top_panel_box_systray.set_halign(Gtk.Align.END)
            self.top_panel_box_systray.set_hexpand(True)

    def show_panels(self):
        if self.all_panels_enabled:
            self.top_panel.present()
            self.dock.do_start()

    def setup_panel_buttons(self):
        if self.default_panel:
            self.top_panel.set_content(self.top_panel_box_full)
        if [i for i in self.args if "topbar" in i]:
            self.dockbar, _ = self.create_widgets("h", "TopBar")
            self.all_panels_enabled = False
            self.top_panel.present()

    def setup_gestures(self):
        # Gestures for top panel
        self.utils.create_gesture(
            self.top_panel_box_left, 2, self.top_panel_left_gesture_mclick
        )
        self.utils.create_gesture(
            self.top_panel_box_left, 3, self.top_panel_left_gesture_rclick
        )

        # Gestures for center panel
        self.utils.create_gesture(
            self.top_panel_box_center, 2, self.top_panel_center_gesture_mclick
        )
        self.utils.create_gesture(
            self.top_panel_box_center, 3, self.top_panel_center_gesture_rclick
        )

        # Gestures for right panel
        self.utils.create_gesture(
            self.top_panel_box_right, 1, self.top_panel_right_gesture_lclick
        )
        self.utils.create_gesture(
            self.top_panel_box_right, 2, self.top_panel_left_gesture_mclick
        )
        self.utils.create_gesture(
            self.top_panel_box_right, 3, self.top_panel_left_gesture_rclick
        )

        # Adding scroll event to the full panel
        EventScroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        EventScroll.connect("scroll", self.scroll_event)
        self.top_panel_box_full.add_controller(EventScroll)

    def maximize_last_focused_view(self, *_):
        pass

    def next_visibe_view_active_workspace(self):
        view_ids = self.wf_utils.get_views_from_active_workspace()
        views = [
            i["id"]
            for i in self.sock.list_views()
            if i["id"] in view_ids and i["role"] == "toplevel"
        ]
        if views:
            view_id = views[0]
            if view_id:
                return view_id

    def hide_view_instead_closing(self, view, ignore_toplevel=None):
        if view:
            if view["role"] != "toplevel" and ignore_toplevel is None:
                return
            button = Gtk.Button()
            button.connect("clicked", lambda widget: self.on_hidden_view(widget, view))
            self.top_panel_box_center.append(button)
            self.utils.handle_icon_for_button(view, button)
            self.sock.hide_view(view["id"])

    def close_last_focused_view(self, *_):
        if self.last_toplevel_focused_view:
            view = self.sock.get_view(self.last_toplevel_focused_view)

            # if the lib from plugin hide-view is not found then use old close view method
            if not self.utils.find_wayfire_lib("libhide-view.so"):
                self.sock.close_view(self.last_toplevel_focused_view)
                return
            self.hide_view_instead_closing(view)

    def on_hidden_view(self, widget, view):
        id = view["id"]
        if id in self.wf_utils.list_ids():
            self.sock.unhide_view(id)
            # ***Warning*** this was freezing the panel
            # set focus will return an Exception in case the view is not toplevel
            GLib.idle_add(lambda *_: self.utils.focus_view_when_ready(view))
            if self.utils.widget_exists(widget):
                self.top_panel_box_center.remove(widget)

    def close_fullscreen_buttons(self):
        # Creating close and full screen buttons for the top bar
        self.cf_box = Gtk.Box()
        self.maximize_button = self.utils.create_button(
            "window-maximize-symbolic",
            None,
            "maximize-button",
            None,
            use_function=self.maximize_last_focused_view,
        )
        self.close_button = self.utils.create_button(
            "window-close-symbolic",
            None,
            "close-button",
            None,
            use_function=self.close_last_focused_view,
        )
        self.minimize_button = self.utils.create_button(
            "window-minimize-symbolic",
            None,
            "minimize-button",
            None,
            use_function=self.minimize_view,
        )
        self.cf_box.append(self.minimize_button)
        self.cf_box.append(self.maximize_button)
        self.cf_box.append(self.close_button)
        self.top_panel_box_for_buttons.append(self.cf_box)
        self.cf_box.add_css_class("cf_box")

    def minimize_view(self, *_):
        if not self.last_toplevel_focused_view:
            return
        self.sock.set_view_minimized(self.last_toplevel_focused_view, True)

    def right_position_launcher_topbar(self):
        return

    def get_soundcard_list(self):
        return sc.all_speakers()

    def get_default_soundcard_id(self):
        return sc.default_speaker().id

    def get_default_soundcard_name(self):
        return sc.default_speaker().name

    def set_default_soundcard(self, id):
        cmd = "pactl set-default-sink {0}".format(id).split()
        Popen(cmd)

    def on_css_file_changed(self, monitor, file, other_file, event_type):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            # Reload CSS when changes are done
            self.load_css_from_file()

    def load_css_from_file(self):
        # you need to append the widgets to their parent containers first and then add_css_class
        css_provider = Gtk.CssProvider()
        css_provider.load_from_file(Gio.File.new_for_path(self.style_css_config))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def setup_panels(self):
        self.panel_on_top = "TOP"
        self.exclusive = True
        self.all_panels_enabled = True

        self.top_panel_box_right.set_halign(Gtk.Align.FILL)

        if "--custom" in self.args:
            self.default_panel = False

        if "--background" in self.args:
            self.exclusive = False

        self.default_panel = True
        panel_toml = self.panel_config_loaded["panel"]
        for p in panel_toml:
            if "bottom" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False

                position = panel_toml[p]["position"]
                size = panel_toml[p]["size"]
                self.bottom_panel = CreatePanel(
                    self.panel_instance,
                    "BOTTOM",
                    position,
                    self.exclusive,
                    width=size,
                    height=0,
                    class_style="BottomBar",
                )

            if "right" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                self.right_panel = CreatePanel(
                    self.panel_instance,
                    "RIGHT",
                    position,
                    self.exclusive,
                    0,
                    32,
                    "RightBar",
                )
            if "left" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                size = panel_toml[p]["size"]
                self.left_panel = CreatePanel(
                    self.panel_instance,
                    "LEFT",
                    position,
                    self.exclusive,
                    0,
                    size,
                    "LeftBar",
                )

            if "top" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                size = panel_toml[p]["size"]
                self.top_panel = CreatePanel(
                    self.panel_instance,
                    "TOP",
                    position,
                    self.exclusive,
                    self.monitor_width,
                    size,
                    "TopBar",
                )
            if "top_background" == p:
                self.exclusive = True
                if panel_toml[p]["Exclusive"] == "False":
                    self.exclusive = False
                position = panel_toml[p]["position"]
                self.top_panel_background = CreatePanel(
                    self.panel_instance,
                    "TOP",
                    position,
                    self.exclusive,
                    self.monitor_width,
                    24,
                    "TopBarBackground",
                )

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
            self.waypanel_cfg, orientation, class_style
        )
        return dockbar

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
            self.stipc.run_cmd("pactl -- set-sink-volume @DEFAULT_SINK@  -8%")
        else:
            self.stipc.run_cmd("pactl -- set-sink-volume @DEFAULT_SINK@  +8%")

        # Show the floating volume widget
        if hasattr(self, "floating_volume_plugin"):
            self.floating_volume_plugin.show_widget()

        with pulsectl.Pulse("volume-increaser") as pulse:
            # Iterate through all the audio sinks
            for sink in pulse.sink_list():
                # Check if the sink is currently running (active)
                if "running" in str(sink.state):
                    # Calculate the volume percentage and round it to the nearest whole number
                    volume = round(sink.volume.values[0] * 100)
                    self.floating_volume_plugin.set_volume(volume)

    def top_panel_left_gesture_lclick(self, *_):
        cmd = self.panel_cfg["left_side_gestures"]["left_click"]
        self.utils.run_app(cmd, True)

    def top_panel_left_gesture_rclick(self, *_):
        self.wf_utils.go_next_workspace_with_views()

    def top_panel_left_gesture_mclick(self, *_):
        self.sock.toggle_expo()

    def top_panel_center_gesture_lclick(self, *_):
        self.sock.toggle_expo()

    def top_panel_center_gesture_mclick(self, *_):
        self.sock.toggle_expo()

    def top_panel_center_gesture_rclick(self, *_):
        self.wf_utils.go_next_workspace_with_views()

    def top_panel_right_gesture_lclick(self, *_):
        cmd = self.panel_cfg["right_side_gestures"]["left_click"]
        self.utils.run_app(cmd, True)

    def top_panel_right_gesture_rclick(self, *_):
        self.sock.toggle_expo()

    def top_panel_right_gesture_mclick(self, *_):
        self.sock.toggle_expo()

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
        if self.panel_instance is not None:
            self.panel_instance.add_action(action)

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
        menu_toml = self.panel_config_loaded["menu"]

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
                self.logger.error(e)
                btn.set_label(label=m)

            btn.set_menu_model(menu)
            submenu = None
            dsubmenu = {}
            menu_buttons[m] = btn
            self.create_simple_action()
            for item in menu_toml[m].values():
                if isinstance(item, dict):
                    item = [item]
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

    def menu_run_action(self, _, param):
        self.stipc.run_cmd(param.get_string())

    def load_topbar_config(self):
        with open(self.waypanel_cfg, "r") as f:
            return toml.load(f)["panel"]

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
        return True

    def toggle_mute_from_sink(self, *_):
        title = self.focused_view_title()
        if not title:
            return
        info = self.sink_input_info()
        sinklist = info["sinklist"]
        for sink in sinklist:
            if title.lower() in sink.lower():
                sink = sink.split("\n")[0]
                self.utils.run_app("pactl set-sink-input-mute {0} toggle".format(sink))

    def _exec_once(self, output, label):
        """
        Executes the output command once and updates the label.

        Args:
            output (str): The command whose output will be displayed in the label.
            label (Gtk.Label): The label widget to update with the command output.

        Returns:
            bool: False to ensure the callback runs only once.
        """
        self.output_loop(output, label)
        return False  # Ensure the callback runs only once

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

        # Return True to indicate successful update
        return True

    def create_cmd_label(self, output, position, css_class, refresh):
        """
        Create and configure a label widget to display command output.

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

        # Add the label to the box container
        box.append(label)

        # Determine the position to add the box container and label
        if position == "left":
            self.top_panel_box_left.append(box)
        elif position == "right":
            self.top_panel_box_systray.append(box)
        elif position == "center":
            self.top_panel_box_center.append(box)

        box.add_css_class(css_class)
        label.add_css_class(css_class)

        # Schedule the command to run once after 10 seconds
        GLib.timeout_add(10 * 1000, lambda: self._exec_once(output, label))

        # Schedule periodic updates of the label content
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
        cmd_settings = self.panel_config_loaded["cmd"]

        # Iterate through each command setting and create/configure the corresponding command label
        for label_key in cmd_settings:
            output = cmd_settings[label_key]["cmd"]
            position = cmd_settings[label_key]["position"]
            refresh = cmd_settings[label_key]["refresh"]
            css_class = cmd_settings[label_key]["css_class"]

            # Create and configure the command label with the specified settings
            self.create_cmd_label(output, position, css_class, refresh)
