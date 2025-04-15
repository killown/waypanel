import os
import sys
import time
from subprocess import Popen
import importlib
import toml
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils

from waypanel.src.core.create_panel import (
    CreatePanel,
)
from waypanel.src.core.utils import Utils
from waypanel.src.core.utils import Utils as utils
from waypanel.src.plugins.core.dockbar import Dockbar


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
        self.plugins = {}

        # Initialize variables and configurations
        self.toggle_mute = {}
        self.volume = 0
        self.args = sys.argv
        self.source_id = None  # Store the source ID for the GLib.timeout

        # Initialize Wayfire components
        self.sock = WayfireSocket()
        self.wf_utils = WayfireUtils(self.sock)
        self.fd = None
        self.utils = utils()
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
        self.update_widget = self.utils.update_widget
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
        self.spacer = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        # will set position of new widgets Gtk.Align.END
        self.spacer.set_hexpand(True)
        self.spacer.add_css_class("right-box-spacer")
        self.top_panel_box_right.append(self.spacer)
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
        self.close_fullscreen_buttons()
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

        # ===========LOAD PLUGINS=============
        GLib.idle_add(self.load_plugins)

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
            self.update_widget(
                self.top_panel_box_left.add_css_class, "top_panel_box_left"
            )
            self.update_widget(
                self.top_panel_box_widgets_left.add_css_class,
                "top_panel_box_widgets_left",
            )
            self.update_widget(
                self.top_panel_box_right.add_css_class, "top_panel_box_right"
            )
            self.update_widget(
                self.top_panel_box_systray.add_css_class, "top_panel_box_systray"
            )
            self.update_widget(
                self.top_panel_box_center.add_css_class, "top_panel_box_center"
            )
            self.update_widget(
                self.top_panel_box_full.add_css_class, "top_panel_box_full"
            )

            return False
        else:
            # Retry after a delay
            GLib.timeout_add(1, self.check_widgets_ready)
            return True

    def do_activate(self):
        # activate auto start apps
        self.load_css_from_file()
        # Start monitoring CSS file for changes
        self.monitor = Gio.File.new_for_path(self.style_css_config).monitor(
            Gio.FileMonitorFlags.NONE, None
        )
        self.monitor.connect("changed", self.on_css_file_changed)
        self.check_widgets_ready()
        self.show_panels()

    def load_plugins(self):
        """
        Dynamically load all plugins from the src.plugins package, including subdirectories.
        Plugins in the 'examples' folder are excluded.
        Plugins that return False for their position or are disabled via ENABLE_PLUGIN
        or listed in the `disabled` field in waypanel.toml will be skipped.
        Additionally, update the [plugins] section in waypanel.toml to reflect the valid plugins.
        """
        # Load configuration and initialize plugin lists
        config, disabled_plugins = self._load_plugin_configuration()
        if config is None:
            return

        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        valid_plugins = []
        plugin_metadata = []

        # Walk through the plugin directory recursively
        for root, dirs, files in os.walk(plugin_dir):
            # Exclude the 'examples' folder
            if "examples" in dirs:
                dirs.remove("examples")  # Skip the 'examples' folder

            for file_name in files:
                if file_name.endswith(".py") and file_name != "__init__.py":
                    module_name = file_name[:-3]  # Remove the .py extension
                    module_path = os.path.relpath(
                        os.path.join(root, file_name), plugin_dir
                    ).replace(os.sep, ".")[:-3]

                    start_time = time.time()  # Start timing
                    try:
                        self._process_plugin(
                            module_name,
                            module_path,
                            disabled_plugins,
                            valid_plugins,
                            plugin_metadata,
                        )
                    except Exception as e:
                        elapsed_time = time.time() - start_time
                        self.logger.error(
                            f"Failed to process plugin {module_name}: {e} (processed in {elapsed_time:.4f} seconds)"
                        )

        # Sort and initialize plugins
        self._initialize_sorted_plugins(plugin_metadata)

        # Update the TOML configuration with valid plugins
        self._update_plugin_configuration(config, valid_plugins, disabled_plugins)

    def _load_plugin_configuration(self):
        """
        Load the TOML configuration file and parse the disabled plugins list.
        Returns the configuration and the set of disabled plugins.
        """
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")

        try:
            if not os.path.exists(waypanel_config_path):
                self.logger.error(
                    f"Configuration file not found at '{waypanel_config_path}'."
                )
                return None, None

            with open(waypanel_config_path, "r") as f:
                config = toml.load(f)

            # Ensure the [plugins] section exists
            if "plugins" not in config:
                config["plugins"] = {"list": "", "disabled": ""}

            # Parse the disabled plugins list
            disabled_plugins = set(config["plugins"].get("disabled", "").split())
            return config, disabled_plugins

        except Exception as e:
            self.logger.error(f"Failed to load configuration file: {e}")
            return None, None

    def _process_plugin(
        self, module_name, module_path, disabled_plugins, valid_plugins, plugin_metadata
    ):
        """
        Process a single plugin module.
        Handles loading, validation, and categorization of the plugin.
        """
        if module_name in disabled_plugins:
            self.logger.info(f"Skipping plugin listed in 'disabled': {module_name}")
            return

        try:
            # Import the plugin module dynamically
            module_full_path = f"waypanel.src.plugins.{module_path}"
            module = importlib.import_module(module_full_path)

            # Check if the plugin has required functions
            if not hasattr(module, "position") or not hasattr(
                module, "initialize_plugin"
            ):
                self.logger.error(
                    f"Module {module_name} is missing required functions. Skipping."
                )
                return

            # Check if the plugin is enabled via ENABLE_PLUGIN
            is_plugin_enabled = getattr(module, "ENABLE_PLUGIN", True)
            if not is_plugin_enabled:
                self.logger.info(f"Skipping disabled plugin: {module_name}")
                return

            position_result = module.position()

            # Handle background-only plugins
            if position_result is False:
                self.logger.info(f"Initializing background-only plugin: {module_name}")
                module.initialize_plugin(self, self)
                valid_plugins.append(module_name)
                elapsed_time = time.time() - start_time
                self.logger.info(
                    f"Background plugin '{module_name}' loaded in {elapsed_time:.4f} seconds"
                )
                return

            # Validate position for regular plugins
            try:
                position, order = position_result
            except (TypeError, ValueError):
                self.logger.error(
                    f"Module {module_name} returned an invalid position. Skipping."
                )
                return

            if position not in ("left", "right", "center"):
                self.logger.error(
                    f"Invalid position '{position}' returned by module {module_name}. Skipping."
                )
                return

            # Add plugin metadata for sorting and initialization
            plugin_metadata.append((module, position, order))
            valid_plugins.append(module_name)

        except Exception as e:
            self.logger.error(f"Error processing plugin {module_name}: {e}")

    def _initialize_sorted_plugins(self, plugin_metadata):
        """
        Sort plugins by their `order` value and initialize them in sorted order.
        """
        plugin_metadata.sort(key=lambda x: x[2])  # Sort by the third element (order)

        for module, position, _ in plugin_metadata:
            start_time = time.time()  # Start timing
            try:
                target_box = self._get_target_panel_box(position)
                if target_box is None:
                    continue

                plugin_instance = module.initialize_plugin(self, self)
                self.plugins[module.__name__] = plugin_instance

                elapsed_time = time.time() - start_time
                self.logger.info(
                    f"Plugin '{module.__name__}' initialized in {elapsed_time:.4f} seconds"
                )

            except Exception as e:
                elapsed_time = time.time() - start_time
                self.logger.error(
                    f"Failed to initialize plugin {module.__name__}: {e} (processed in {elapsed_time:.4f} seconds)"
                )

    def _get_target_panel_box(self, position):
        """
        Determine the target panel box based on the plugin's position.
        """
        if position == "left":
            return self.top_panel_box_left
        elif position == "right":
            return self.top_panel_box_right
        elif position == "center":
            return self.top_panel_box_center
        else:
            self.logger.error(f"Invalid position '{position}'. Skipping.")
            return None

    def _update_plugin_configuration(self, config, valid_plugins, disabled_plugins):
        """
        Update the [plugins] section in the TOML configuration with valid plugins.
        Save the updated configuration back to the file.
        """
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
        config["plugins"]["list"] = " ".join(valid_plugins)
        config["plugins"]["disabled"] = " ".join(disabled_plugins)

        try:
            with open(waypanel_config_path, "w") as f:
                toml.dump(config, f)
        except Exception as e:
            self.logger.error(f"Failed to save updated configuration: {e}")

    def monitor_width_height(self):
        focused_view = self.sock.get_focused_view()
        if focused_view:
            output = self.utils.get_monitor_info()
            output = output[self.monitor_name]
            self.monitor_width = output[0]
            self.monitor_height = output[1]

    def show_panels(self):
        if self.all_panels_enabled:
            self.top_panel.present()
            self.dock.do_start()

    def setup_panel_buttons(self):
        if self.default_panel:
            self.top_panel.set_content(self.top_panel_box_full)
        if [i for i in self.args if "topbar" in i]:
            self.all_panels_enabled = False
            self.top_panel.present()

    def maximize_last_focused_view(self, *_):
        pass

    def hide_view_instead_closing(self, view, ignore_toplevel=None):
        if view:
            if view["role"] != "toplevel" and ignore_toplevel is None:
                return
            button = Gtk.Button()
            button.connect("clicked", lambda widget: self.on_hidden_view(widget, view))
            self.update_widget(self.top_panel_box_center.append, button)
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
                self.update_widget(self.top_panel_box_center.remove, widget)

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
        self.update_widget(self.cf_box.append, self.minimize_button)
        self.update_widget(self.cf_box.append, self.maximize_button)
        self.update_widget(self.cf_box.append, self.close_button)
        self.update_widget(self.top_panel_box_for_buttons.append, self.cf_box)
        self.update_widget(self.cf_box.add_css_class, "cf_box")

    def minimize_view(self, *_):
        if not self.last_toplevel_focused_view:
            return
        self.sock.set_view_minimized(self.last_toplevel_focused_view, True)

    def set_default_soundcard(self, id):
        cmd = "pactl set-default-sink {0}".format(id).split()
        Popen(cmd)

    def on_css_file_changed(self, monitor, file, other_file, event_type):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            # Reload CSS when changes are done
            def run_once():
                self.load_css_from_file()
                return False

            GLib.idle_add(run_once)

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
