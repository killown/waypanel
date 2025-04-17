import os
import sys
import orjson as json
import toml
from gi.repository import Gtk
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.ipc import WayfireSocket
from waypanel.src.ipc_server.ipc_client import WayfireClientIPC
from ...core.create_panel import (
    CreatePanel,
    set_layer_position_exclusive,
    unset_layer_position_exclusive,
)
from ...core.utils import Utils

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
        self.update_widget = self.utils.update_widget
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

    def _setup_panels(self, panel_toml):
        """Set up panels based on the provided configuration."""
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

        # Extract configuration values
        exclusive = config["Exclusive"] == True
        position = config["position"]
        size = config["size"]
        enabled = config["enabled"]

        # Create the bottom panel
        self.bottom_panel = CreatePanel(
            self, "BOTTOM", position, exclusive, 0, size, "BottomBar"
        )

        # Add launcher button
        self.add_launcher = Gtk.Button()
        icon = self.utils.get_nearest_icon_name("tab-new")
        self.update_widget(self.add_launcher.set_icon_name, icon)

        # Scrolled window setup
        self.scrolled_window = Gtk.ScrolledWindow()
        output = os.getenv("waypanel")
        output_name = None
        geometry = None

        if output:
            output_name = json.loads(output).get("output_name")
        if output_name:
            output_id = self.wf_utils.get_output_id_by_name(output_name)
            if output_id:
                geometry = self.wf_utils.get_output_geometry(output_id)

        if geometry:
            monitor_width = geometry["width"]
            self.update_widget(
                self.scrolled_window.set_size_request, monitor_width / 1.2, 64
            )

        # Set content for the bottom panel
        self.update_widget(self.bottom_panel.set_content, self.scrolled_window)

        # Taskbar setup
        self.taskbar = Gtk.FlowBox()
        self.update_widget(
            self.taskbar.set_halign, Gtk.Align.CENTER
        )  # Center horizontally
        self.update_widget(
            self.taskbar.set_valign, Gtk.Align.CENTER
        )  # Center vertically
        self.update_widget(self.scrolled_window.set_child, self.taskbar)
        self.taskbar.add_css_class("taskbar")

        # Present the panel if enabled
        if enabled:
            self.update_widget(self.bottom_panel.present)

        # Start the taskbar list for the bottom panel
        self.Taskbar("h", "taskbar")

        # Set layer position exclusively
        self.update_widget(set_layer_position_exclusive, self.bottom_panel, size)

        self.logger.info("Bottom panel setup completed.")

        # Unset layer position for other panels
        self.update_widget(unset_layer_position_exclusive, self.left_panel)
        self.update_widget(unset_layer_position_exclusive, self.bottom_panel)

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
        if msg["event"] == "output-gain-focus":
            self.on_output_gain_focus()
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
        view = None
        if "view" in msg:
            view = msg["view"]
        if "event" in msg:
            if msg["event"] == "view-geometry-changed":
                if "view" in msg:
                    view = msg["view"]
                    if view["layer"] != "workspace":
                        self.taskbar_view_exists(view["id"])
            if msg["event"] == "output-gain-focus":
                pass
            self.handle_view_event(msg)
            self.handle_plugin_event(msg)
        return True

    def on_view_role_toplevel_focused(self, view):
        """Handle when a toplevel view gains focus."""
        return True

    def on_output_gain_focus(self):
        return True

    def on_expo_activated(self):
        """Handle expo plugin activation."""
        return True

    def on_moving_view(self):
        """Handle moving view event."""
        return True

    def on_expo_desactivated(self):
        """Handle expo plugin deactivation."""
        return True

    def on_view_focused(self):
        """Handle when any view gains focus."""
        return True

    def on_app_id_changed(self, view):
        """Handle changes in app-id of a view."""
        self.update_taskbar_list(view)

    def panel_output_is_focused_output(self):
        """Check if the current panel's output is the focused output."""
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
        """Handle scale wayfire plugin activation."""
        # set layer exclusive so the panels becomes clickable
        output_info = os.getenv("waypanel")
        layer_set_on_output_name = None
        if output_info:
            layer_set_on_output_name = json.loads(output_info).get("output_name")
        focused_output_name = self.sock.get_focused_output()["name"]
        # only set layer if the focused output is the same as the defined in panel creation
        if layer_set_on_output_name == focused_output_name:
            set_layer_position_exclusive(self.left_panel, 64)
            set_layer_position_exclusive(self.bottom_panel, 48)

        # also update taskbar buttons, sometimes the title/icon changed meanwhile
        self.update_taskbar_on_scale()

    def on_scale_desactivated(self):
        """Handle scale plugin deactivation."""
        # this will set panels on bottom, hidden it from views
        self.update_widget(unset_layer_position_exclusive, self.left_panel)
        self.update_widget(unset_layer_position_exclusive, self.bottom_panel)

    def on_view_created(self, view):
        """Handle creation of new views."""
        self.logger.debug(f"View created: {view}")

        # create a new button for the newly created view
        self.update_taskbar(view)
        self.update_taskbar_list(view)

    def on_view_destroyed(self, view):
        """Handle destruction of views."""
        self.logger.debug(f"View destroyed: {view}")

        # remove the button related to the view
        self.update_taskbar_list(view)

    def on_view_wset_changed(self, view):
        """Handle workspace changes for views."""
        self.logger.debug(f"Workspace changed for view: {view}")

        # wokspace changed so it may need an update
        self.update_taskbar(view)

    def on_title_changed(self, view):
        """Handle title changes for views."""
        # update the label for the given view when title changes
        self.update_taskbar_button(view)

    def get_default_monitor_name(self):
        """Get the default monitor name from the configuration."""
        self.logger.debug("Fetching default monitor name.")
        try:
            with open(self.waypanel_cfg, "r") as file:
                config = toml.load(file)["panel"]
                if "monitor" in config:
                    # for panel creation to determine which monitor it should stay on
                    return config["monitor"].get("name")
                else:
                    return None
        except FileNotFoundError:
            self.logger.error("Configuration file not found.")
            return None

    def _truncate_title(self, title: str, max_length: int = 20) -> str:
        """
        Truncate a title to fit within the maximum allowed length.

        Args:
            title (str): The original title.
            max_length (int): The maximum allowed length.

        Returns:
            str: The truncated title.
        """
        if len(title) <= max_length:
            return title
        words = title.split()
        if len(words[0]) > 10:
            return words[0][:max_length]
        return " ".join(words)[:max_length]

    def update_taskbar_button(self, view):
        """
        remove the old button from taskbar and add a new one updated
        this function is only intended to use along with event: title_changed
        """
        button = None
        id = view["id"]
        if id in self.buttons_id:
            button = self.buttons_id[id][0]

        if not button:
            return

        if not self.utils.widget_exists(button):
            return

        if button:
            self.remove_button(id)
            self.update_taskbar(view)

    def update_taskbar(self, view) -> None:
        """
        Update the label of a taskbar button based on the view's title.

        Args:
            view (dict): A dictionary containing view details, including 'title'.
        """
        self.logger.debug(f"Updating taskbar button label for view: {view}")
        raw_title = view.get("title", "")
        filtered_title = self.utils.filter_utf_for_gtk(raw_title)
        truncated_title = self._truncate_title(filtered_title)
        initial_title = truncated_title.split()[0]
        self.logger.debug(f"Truncated title: {truncated_title}")
        icon = self.utils.get_icon(view["app-id"], initial_title, truncated_title)
        self.update_taskbar_list(view)

    def update_taskbar_on_scale(self) -> None:
        """Update all taskbar buttons during scale plugin activation."""
        self.logger.debug("Updating taskbar buttons during scale plugin activation.")
        for view in self.sock.list_views():
            self.update_taskbar(view)
            self.update_taskbar_list(view)

    def Taskbar(self, orientation, class_style, update_button=False, callback=None):
        """Initialize or update the taskbar."""
        self.logger.debug("Initializing or updating taskbar.")
        list_views = self.sock.list_views()
        if not list_views:
            return
        for i in list_views:
            self.new_taskbar_view(orientation, class_style, i["id"])
        return True

    def validate_view_for_taskbar(self, view_id) -> dict:
        """
        Validate if a view exists and meets the criteria to be added to the taskbar.

        Args:
            view_id (int): The ID of the view to validate.

        Returns:
            dict or None: The view object if valid, otherwise None.
        """
        self.logger.debug(f"Validating view for taskbar: {view_id}")
        if not self.view_exist(view_id):
            self.logger.debug(f"View does not exist: {view_id}")
            return {}
        if view_id in self.taskbar_list:
            self.logger.debug(f"View already in taskbar list: {view_id}")
            return {}
        if view_id not in self.wf_utils.list_ids():
            self.logger.debug(f"View ID not in active IDs: {view_id}")
            return {}

        view = self.sock.get_view(view_id)
        if not view:
            self.logger.debug(f"Failed to fetch view details for ID: {view_id}")
            return {}

        return view

    def get_valid_button(self, button_id):
        if button_id in self.buttons_id:
            button = self.buttons_id[button_id][0]
            if self.utils.widget_exists(button):
                return button
        self.logger.debug(f"Invalid or missing button for ID: {button_id}")
        return None

    def create_taskbar_button(self, view, orientation, class_style):
        """
        Create a taskbar button for a given view.

        Args:
            view (dict): The view object containing details like ID, title, and app-id.
            orientation (str): The orientation of the taskbar ("h" or "v").
            class_style (str): The CSS class style for the button.

        Returns:
            bool: True if the button was successfully created, False otherwise.
        """
        self.logger.debug(f"Creating taskbar button for view: {view['id']}")
        id = view["id"]
        title = self.utils.filter_utf_for_gtk(view["title"])
        wm_class = view["app-id"]
        initial_title = title.split(" ")[0].lower()

        button = self.utils.create_taskbar_launcher(
            wm_class, title, initial_title, orientation, class_style, id
        )

        if not button:
            self.logger.error(f"Failed to create taskbar button for view ID: {id}")
            return False

        # Append the button to the taskbar
        self.utils.append_widget_if_ready(self.taskbar, button)

        # Store button information in dictionaries for easy access
        self.buttons_id[id] = [button, initial_title, id]
        self.taskbar_list.append(id)
        button.add_css_class("taskbar-button")
        return True

    def new_taskbar_view(self, orientation, class_style, view_id, callback=None):
        """
        Initialize or update the taskbar with a new view.

        Args:
            orientation (str): The orientation of the taskbar ("h" or "v").
            class_style (str): The CSS class style for the button.
            view_id (int): The ID of the view to add.
            callback (function, optional): A callback function to execute after creation.

        Returns:
            bool: True if the taskbar button was successfully created, False otherwise.
        """
        self.logger.debug(f"Initializing new taskbar view for ID: {view_id}")

        # Validate the view
        view = self.validate_view_for_taskbar(view_id)
        if not view:
            self.logger.debug(f"Validation failed for view ID: {view_id}")
            return False

        # Create the taskbar button
        success = self.create_taskbar_button(view, orientation, class_style)
        if not success:
            self.logger.error(f"Failed to create taskbar button for view ID: {view_id}")
            return False

        if callback:
            callback(view_id)

        return True

    def is_valid_view(self, view):
        """
        Check if a view meets the criteria to be displayed in the taskbar.

        Args:
            view (dict): The view object containing details like ID.

        Returns:
            bool: True if the view is valid, False otherwise.
        """
        return (
            view["layer"] == "workspace"
            and view["role"] == "toplevel"
            and view["mapped"] is True
            and view["app-id"] != "nil"
            and view["pid"] != -1
        )

    def view_exist(self, view_id):
        """Check if a view exists and meets criteria to be displayed in the taskbar."""
        try:
            view_id_list = [view["id"] for view in self.sock.list_views()]
            if view_id not in view_id_list:
                return
            view = self.sock.get_view(view_id)
            if not self.is_valid_view(view):
                return False
            return True
        except KeyError as e:
            self.logger.error(f"Missing key in view data: {e}")
        except TypeError as e:
            self.logger.error(f"Invalid type in view data: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error checking view existence: {e}")
        return False

    def update_taskbar_for_hidden_views(self, view):
        """Handle cases where views are hidden but still need removal from the taskbar."""
        # this function is specific for the wayfire plugin hide-view
        self.logger.debug(f"Updating taskbar for hidden views: {view}")
        if view["role"] == "desktop-environment":
            self.remove_button(view["id"])
        # Also update the view when unhide
        for v in self.sock.list_views():
            if v["role"] == "toplevel":
                if v["id"] not in self.buttons_id:
                    self.update_taskbar_list(v)

    def update_taskbar_list(self, view):
        """
        Update the taskbar list based on the current views.

        Args:
            view (dict): The view object containing details like ID.
        """
        self.logger.debug(f"Updating taskbar list for view: {view}")

        # Step 1: Validate the current view
        if not self._validate_and_update_view(view):
            return

        # Step 2: Update the taskbar layout
        self.Taskbar("h", "taskbar")

        # Step 3: Remove invalid buttons
        self._remove_invalid_buttons()

    def _validate_and_update_view(self, view) -> bool:
        """
        Validate the existence of a view and update the taskbar accordingly.

        Args:
            view (dict): The view object containing details like ID.

        Returns:
            bool: True if the view exists, False otherwise.
        """
        view_id = view["id"]
        if not self.view_exist(view_id):
            self.taskbar_view_exists(view_id)
            return False
        return True

    def _remove_invalid_buttons(self):
        """
        Remove taskbar buttons for views that no longer exist.
        """
        active_ids = set(
            self.wf_utils.list_ids()
        )  # Get the current list of valid view IDs
        for button_id in list(self.buttons_id.keys()):  # Iterate over a copy of keys
            if button_id not in active_ids:
                self.taskbar_view_exists(button_id)

    def remove_button(self, id):
        """
        Remove a taskbar button associated with a view.

        Args:
            id (int): The ID of the view whose button should be removed.
        """

        # Get the valid button using the helper function
        button = self.get_valid_button(id)
        if not button:
            self.logger.debug(f"No valid button found for ID: {id}")
            return

        # Remove the button from the taskbar and clean up
        self.update_widget(self.taskbar.remove, button)
        self.taskbar_list.remove(id)
        self.utils.remove_gesture(button)
        del self.buttons_id[id]

    def taskbar_view_exists(self, id=None):
        """
        Remove a taskbar entry if the view does not exist.

        Args:
            id (int): The ID of the view to check.

        Returns:
            bool: True if the taskbar entry was removed, False otherwise.
        """
        if self.view_exist(id):
            return False
        button = self.get_valid_button(id)
        if not button:
            return False
        self.remove_button(id)
        return True
