import os
import sys
import orjson as json
import toml
from gi.repository import Gtk
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.ipc import WayfireSocket
from waypanel.src.ipc_server.ipc_client import WayfireClientIPC
from ..core.create_panel import (
    CreatePanel,
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)
from ..core.utils import Utils

sys.path.append("/usr/lib/waypanel/")


class Dockbar(Gtk.Application):
    """Main class responsible for managing the dockbar and its panels."""

    def __init__(self, logger, **kwargs):
        super().__init__(**kwargs)
        self.logger = logger
        self.utils = Utils()
        self.panel_cfg = self.utils.load_topbar_config()
        self.taskbar_list = [None]
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.all_pids = [i["id"] for i in self.sock.list_views()]
        self.buttons_id = {}
        self.left_panel = None
        self.bottom_panel = None
        self.has_taskbar_started = False
        self.stored_windows = []
        self.is_scale_active = {}
        self._setup_config_paths()
        self.ipc_client = WayfireClientIPC(self.handle_event)
        self.logger.info("Dockbar initialized.")
        # Initialize IPC events handling.
        self.ipc_client.wayfire_events_setup("/tmp/waypanel.sock")
        self.logger.info("IPC events setup completed.")

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.logger.debug("Setting up configuration paths.")
        config_paths = self.utils.setup_config_paths()
        self.home = config_paths["home"]
        self.waypanel_cfg = os.path.join(self.home, ".config/waypanel/waypanel.toml")
        self.webapps_applications = os.path.join(self.home, ".local/share/applications")
        self.scripts = config_paths["scripts"]
        self.config_path = config_paths["config_path"]
        self.cache_folder = config_paths["cache_folder"]
        self.logger.info(f"Configuration paths set: {config_paths}")

    def _load_config(self):
        """Load and cache the configuration from the TOML file."""
        self.logger.debug("Loading configuration from TOML file.")
        if not hasattr(self, "_cached_config"):
            with open(self.waypanel_cfg, "r") as f:
                self._cached_config = toml.load(f)
        self.logger.info("Configuration loaded successfully.")
        return self._cached_config

    def do_start(self):
        """Start the Dockbar application by setting up the stored windows and panels."""
        self.logger.info("Starting Dockbar application.")
        self.stored_windows = [i["id"] for i in self.sock.list_views()]
        panel_toml = self._load_config()["panel"]
        self._setup_panels(panel_toml)
        self.logger.info("Dockbar application started.")

    def _setup_panels(self, panel_toml):
        """Set up panels based on the provided configuration."""
        self.logger.debug("Setting up panels.")
        for p in panel_toml:
            if p == "left":
                self._setup_left_panel(panel_toml[p])
            elif p == "bottom":
                self._setup_bottom_panel(panel_toml[p])
        self.logger.info("Panels setup completed.")

    def _setup_left_panel(self, config):
        """Create and configure the left panel."""
        self.logger.debug("Setting up left panel.")
        exclusive = config["Exclusive"] == True
        position = config["position"]
        size = config["size"]
        enabled = config["enabled"]
        self.left_panel = CreatePanel(
            self, "LEFT", position, exclusive, size, 0, "left-panel"
        )
        self.dockbar = self.utils.CreateFromAppList(
            self.waypanel_cfg, "v", "dockbar-buttons"
        )
        self.left_panel.set_content(self.dockbar)
        if enabled:
            self.left_panel.present()
        self.logger.info("Left panel setup completed.")

    def _setup_bottom_panel(self, config):
        """Create and configure the bottom panel."""
        self.logger.debug("Setting up bottom panel.")
        exclusive = config["Exclusive"] == True
        position = config["position"]
        size = config["size"]
        enabled = config["enabled"]
        self.bottom_panel = CreatePanel(
            self, "BOTTOM", position, exclusive, 0, size, "BottomBar"
        )
        self.add_launcher = Gtk.Button()
        self.add_launcher.set_icon_name(self.utils.get_nearest_icon_name("tab-new"))
        self.scrolled_window = Gtk.ScrolledWindow()
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
        self.taskbar = Gtk.FlowBox()
        self.taskbar.set_halign(Gtk.Align.CENTER)  # Center horizontally
        self.taskbar.set_valign(Gtk.Align.CENTER)  # Center vertically
        self.scrolled_window.set_child(self.taskbar)
        self.taskbar.add_css_class("taskbar")
        # apps append button
        # self.taskbar.append(self.add_launcher)
        if enabled:
            self.bottom_panel.present()
        # Start the taskbar list for the bottom panel
        self.Taskbar("h", "taskbar")
        set_layer_position_exclusive(self.bottom_panel, size)
        self.logger.info("Bottom panel setup completed.")
        unset_layer_position_exclusive(self.left_panel)
        unset_layer_position_exclusive(self.bottom_panel)

    def handle_exceptions(self, func):
        """Decorator to handle exceptions within methods."""

        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.error(f"An error occurred in {func.__name__}: {e}")
                return None

        return wrapper

    def file_exists(self, full_path):
        """Check if a file exists at the given path."""
        exists = os.path.exists(full_path)
        self.logger.debug(f"Checking if file exists: {full_path} -> {exists}")
        return exists

    def handle_view_event(self, msg):
        """Handle view-related IPC events."""
        self.logger.debug(f"Handling dockbar view event: {msg}")

        view = msg.get("view")

        if "event" not in msg:
            return
        # This event match must be here because if not, role != toplevel will make it never match.
        if msg["event"] == "view-wset-changed":
            self.update_taskbar_for_hidden_views(view)
        # This must be here; an unmapped view is view None, must be above if view is None.
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
            pass
        if msg["event"] == "app-id-changed":
            self.on_app_id_changed(msg["view"])
        if msg["event"] == "view-focused":
            self.on_view_role_toplevel_focused(view)
            self.on_view_focused()
            self.last_focused_output = view["output-id"]
        if msg["event"] == "view-mapped":
            self.on_view_created(view)
        if msg["event"] == "view-unmapped":
            self.on_view_destroyed(view)
        return True

    def handle_plugin_event(self, msg):
        """Handle plugin-related IPC events."""
        self.logger.debug(f"Handling plugin event: {msg}")
        if "event" not in msg:
            return True
        if msg["event"] == "plugin-activation-state-changed":
            if msg["state"] is True:
                if msg["plugin"] == "expo":
                    self.on_expo_activated()
                if msg["plugin"] == "scale":
                    self.on_scale_activated()
                if msg["plugin"] == "move":
                    self.on_moving_view()
            if msg["state"] is False:
                if msg["plugin"] == "expo":
                    self.on_expo_desactivated()
                if msg["plugin"] == "scale":
                    self.on_scale_desactivated()
        return True

    def handle_event(self, msg):
        """Handle general IPC events."""
        self.logger.debug(f"Handling general IPC event: {msg}")
        view = None
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
            self.handle_view_event(msg)
            self.handle_plugin_event(msg)
        return True

    def on_view_role_toplevel_focused(self, view):
        """Handle when a toplevel view gains focus."""
        self.logger.debug(f"Toplevel view focused: {view}")
        return True

    def on_expo_activated(self):
        """Handle expo plugin activation."""
        self.logger.info("Expo plugin activated.")
        return True

    def on_moving_view(self):
        """Handle moving view event."""
        self.logger.info("Moving view event triggered.")
        return True

    def on_expo_desactivated(self):
        """Handle expo plugin deactivation."""
        self.logger.info("Expo plugin deactivated.")
        return True

    def on_view_focused(self):
        """Handle when any view gains focus."""
        self.logger.debug("View focused.")
        return True

    def on_app_id_changed(self, view):
        """Handle changes in app-id of a view."""
        self.logger.debug(f"App ID changed for view: {view}")
        self.update_taskbar_list(view)

    def panel_output_is_focused_output(self):
        """Check if the current panel's output is the focused output."""
        self.logger.debug("Checking if panel output is focused output.")
        output = os.getenv("waypanel")
        output_name = None
        focused_output_name = None
        focused_output = self.sock.get_focused_output()
        if focused_output:
            focused_output_name = focused_output["name"]
        if output:
            output_name = json.loads(output)
            output_name = output_name["output_name"]
            if focused_output_name:
                if focused_output_name == output_name:
                    return True

    def on_scale_activated(self):
        """Handle scale plugin activation."""
        self.logger.info("Scale plugin activated.")
        set_layer_position_exclusive(self.left_panel, 64)
        set_layer_position_exclusive(self.bottom_panel, 48)
        self.update_taskbar_on_scale()

    def on_scale_desactivated(self):
        """Handle scale plugin deactivation."""
        self.logger.info("Scale plugin deactivated.")
        unset_layer_position_exclusive(self.left_panel)
        unset_layer_position_exclusive(self.bottom_panel)

    def on_view_created(self, view):
        """Handle creation of new views."""
        self.logger.debug(f"View created: {view}")
        self.update_taskbar_list(view)

    def on_view_destroyed(self, view):
        """Handle destruction of views."""
        self.logger.debug(f"View destroyed: {view}")
        self.update_taskbar_list(view)

    def on_view_wset_changed(self, view):
        """Handle workspace changes for views."""
        self.logger.debug(f"Workspace changed for view: {view}")
        self.update_taskbar_button_label(view)

    def on_title_changed(self, view):
        """Handle title changes for views."""
        self.update_taskbar_button_label(view)

    def get_default_monitor_name(self):
        """Get the default monitor name from the configuration."""
        self.logger.debug("Fetching default monitor name.")
        try:
            with open(self.waypanel_cfg, "r") as file:
                config = toml.load(file)["panel"]
                if "monitor" in config:
                    return config["monitor"].get("name")
                else:
                    return None
        except FileNotFoundError:
            self.logger.error("Configuration file not found.")
            return None

    def update_taskbar_button_label(self, view):
        """Update the label and icon of a taskbar button."""
        self.logger.debug(f"Updating taskbar button label for view: {view}")
        title = self.utils.filter_utf_for_gtk(view["title"])
        title = title[:20]
        words = title.split()
        first_word_length = 0
        if words:
            first_word_length = len(words[0])
        if first_word_length > 10:
            title = title.split()[0]
        initial_title = title.split()
        if initial_title:
            initial_title = initial_title[0]
        else:
            return
        icon = self.utils.get_icon(view["app-id"], initial_title, title)
        id = view["id"]
        button = None
        if id in self.buttons_id:
            button = self.buttons_id[view["id"]]

        if not button:
            return

        if not self.utils.widget_exists(button[0]):
            return

        if button:
            taskbar_button = button[0]
            button_box = taskbar_button.get_first_child()
            button_icon = button_box.get_first_child()
            button_label = button_box.get_last_child()
            apps_using_audio = self.utils.get_audio_apps_with_titles()
            pid = str(view["pid"])
            if any(
                app for app in apps_using_audio if str(pid) in app and title in app[pid]
            ):
                title = title + " 🔊"
            button_label.set_name(title)
            if icon:
                button_icon.new_from_icon_name(self.utils.get_nearest_icon_name(icon))

    def update_taskbar_on_scale(self):
        """Update all taskbar buttons during scale plugin activation."""
        self.logger.debug("Updating taskbar buttons during scale plugin activation.")
        for view in self.sock.list_views():
            self.remove_button(view["id"])
            self.update_taskbar_list(view)

    def Taskbar(self, orientation, class_style, update_button=False, callback=None):
        """Initialize or update the taskbar."""
        self.logger.debug("Initializing or updating taskbar.")
        list_views = self.sock.list_views()
        if not list_views:
            return
        for i in list_views:
            self.new_taskbar_view(orientation, class_style, i["id"])
        # Return True to indicate successful execution of the Taskbar function
        return True

    def new_taskbar_view(
        self,
        orientation,
        class_style,
        view_id,
        callback=None,
    ):
        """Create a new taskbar button for a view."""
        self.logger.debug(f"Creating new taskbar view for ID: {view_id}")
        if not class_style:
            class_style = "taskbar"
        if not self.view_exist(view_id):
            return
        if view_id in self.taskbar_list:
            return
        if view_id not in self.wf_utils.list_ids():
            return
        view = self.sock.get_view(view_id)
        id = view["id"]
        title = view["title"]
        title = self.utils.filter_utf_for_gtk(title)
        wm_class = view["app-id"]
        initial_title = title.split(" ")[0].lower()
        button = self.utils.create_taskbar_launcher(
            wm_class, title, initial_title, orientation, class_style, id
        )
        if button:
            self.utils.append_widget_if_ready(self.taskbar, button)
            # Store button information in dictionaries for easy access
            self.buttons_id[id] = [button, initial_title, id]
            self.taskbar_list.append(id)
            button.add_css_class("taskbar-button")
            return True

    def pid_exist(self, id):
        """Check if a PID exists for a given view."""
        self.logger.debug(f"Checking if PID exists for view ID: {id}")
        pid = self.wf_utils.get_view_pid(id)
        if pid != -1:
            return True
        else:
            return False

    def view_exist(self, view_id):
        """Check if a view exists and meets criteria to be displayed in the taskbar."""
        self.logger.debug(f"Checking if view exists: {view_id}")
        try:
            view = self.sock.get_view(view_id)
            layer = view["layer"] != "workspace"
            role = view["role"] != "toplevel"
            mapped = view["mapped"] is False
            app_id = view["app-id"] == "nil"
            pid = view["pid"] == -1
            if layer or role or mapped or app_id or pid:
                return False
            return True
        except Exception:
            self.logger.info(f"View closed or does not exist - ID: {view_id}")
            return False

    def update_taskbar_for_hidden_views(self, view):
        """Handle cases where views are hidden but still need removal from the taskbar."""
        self.logger.debug(f"Updating taskbar for hidden views: {view}")
        # The goal of this function is to catch taskbar buttons which are not toplevel
        # and should be in the task list. Sometimes there aren't enough events to remove
        # the button on the fly. This is made for hide view plugins that hide a view but
        # lack events to trigger taskbar button removal.
        if view["role"] == "desktop-environment":
            self.remove_button(view["id"])
        # Also update the view when unhide
        for v in self.sock.list_views():
            if v["role"] == "toplevel":
                if v["id"] not in self.buttons_id:
                    self.update_taskbar_list(v)

    def update_taskbar_list(self, view):
        """Update the taskbar list based on the current views."""
        self.logger.debug(f"Updating taskbar list for view: {view}")
        if not self.view_exist(view["id"]):
            self.taskbar_remove(view["id"])
        self.Taskbar("h", "taskbar")
        ids = self.wf_utils.list_ids()
        button_ids = self.buttons_id.copy()
        for button_id in button_ids:
            if button_id not in ids:
                self.taskbar_remove(button_id)

    def remove_button(self, id):
        """Remove a taskbar button associated with a view."""
        self.logger.debug(f"Removing taskbar button for ID: {id}")
        if id in self.buttons_id:
            button = self.buttons_id[id][0]
            if not self.utils.widget_exists(button):
                return
            self.taskbar.remove(button)
            self.taskbar_list.remove(id)
            self.utils.remove_gesture(button)
            del self.buttons_id[id]

    def taskbar_remove(self, id=None):
        """Remove a taskbar entry if the view does not exist."""
        self.logger.debug(f"Attempting to remove taskbar entry for ID: {id}")
        if self.view_exist(id):
            return
        if id in self.buttons_id:
            button = self.buttons_id[id][0]
            if not self.utils.widget_exists(button):
                return
            self.remove_button(id)
