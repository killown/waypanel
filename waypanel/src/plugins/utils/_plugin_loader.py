import os
import importlib
import toml
from src.core.utils import Utils
from gi.repository import GLib, Gtk
import sys
import traceback


class PluginLoader:
    """
    Manages dynamic discovery, loading, validation, and initialization of waypanel plugins.

    The PluginLoader scans both built-in and user-defined plugin directories,
    loads them dynamically, ensures required interfaces exist, respects dependencies,
    and initializes plugins in the correct order based on priority and position.

    ### Key Responsibilities
    - Discovers all available plugins in `src.plugins` and custom directories.
    - Validates that each plugin implements required functions: `get_plugin_placement`, `initialize_plugin`.
    - Loads configuration from `waypanel.toml` to determine which plugins are enabled/disabled.
    - Sorts plugins by priority and order for consistent layout and behavior.
    - Initializes plugins after resolving dependencies.

    ### Usage Example
    ```python
    plugin_loader = PluginLoader(panel_instance, logger, config_path)
    plugin_loader.load_plugins()
    ```
    """

    def __init__(self, panel_instance, logger, config_path):
        """
        Initialize the PluginLoader with core components.

        Args:
            panel_instance: Main Panel object (used for plugin access and event management).
            logger: Logger instance for structured logging.
            config_path: Path to `waypanel.toml` for plugin enable/disable settings.
        """
        self.panel_instance = panel_instance
        self.logger = logger
        self.config_path = config_path
        self.utils = Utils(panel_instance)
        self.plugins = {}
        self.plugins_path = {}
        self.plugins_import = {}
        self.plugin_containers = {}
        self.plugins_dir = self.plugins_base_path()
        self.position_mapping = {}
        self.user_plugins_dir = os.path.join(
            self.get_real_user_home(), ".config", "waypanel", "plugins"
        )

    def get_real_user_home(self):
        # Try SUDO_USER first
        if "SUDO_USER" in os.environ:
            return os.path.expanduser(f"~{os.environ['SUDO_USER']}")
        # Fallback to PKEXEC_UID (used by pkexec)
        elif "PKEXEC_UID" in os.environ:
            return os.path.expanduser(f"~{os.environ['PKEXEC_UID']}")
        # Default case (non-root or not running via sudo/pkexec)
        return os.path.expanduser("~")

    def disable_plugin(self, plugin_name):
        """Disable a plugin by name."""
        if plugin_name not in self.plugins:
            self.logger.warning(f"Plugin '{plugin_name}' not found.")
            return

        plugin_instance = self.plugins[plugin_name]

        # Call the on_stop method if it exists
        if hasattr(plugin_instance, "on_stop"):
            try:
                plugin_instance.on_stop()
                self.logger.info(f"Stopped plugin: {plugin_name}")
            except Exception as e:
                self.logger.error(f"Error stopping plugin {plugin_name}: {e}")

        if hasattr(plugin_instance, "disable"):
            plugin_instance.disable()
            self.logger.info(f"Disabled plugin: {plugin_name}")
        else:
            self.logger.warning(f"Plugin '{plugin_name}' does not support disabling.")

    def enable_plugin(self, plugin_name, plugin_metadata):
        """
        Enable a plugin by name.
        Args:
            plugin_name (str): The name of the plugin to enable.
        """
        if plugin_name not in self.plugins_path:
            self.logger.error(
                f"Plugin '{plugin_name}' not found in plugins_path. Skipping enable."
            )
            return

        try:
            # Initialize the plugin using _initialize_sorted_plugins
            if plugin_metadata:
                self._initialize_sorted_plugins(plugin_metadata)
                self.logger.info(f"Enabled and initialized plugin: {plugin_name}")
            else:
                self.logger.error(
                    f"Failed to process metadata for plugin: {plugin_name}"
                )

        except Exception as e:
            self.logger.error(
                error=e,
                message=f"Error enabling plugin '{plugin_name}': {e}",
                level="error",
            )

    def load_plugins(self):
        """
        Load and initialize all plugins from built-in and custom directories.

        ### Workflow:
        1. Load configuration from `waypanel.toml`
        2. Discover `.py` files in `src.plugins` and custom plugin directory
        3. Filter out invalid or disabled modules
        4. Sort plugins by priority and order
        5. Ensure dependencies are resolved before initializing plugins
        6. Initialize each plugin and store reference in `self.plugins`

        Plugins not implementing `initialize_plugin()` or marked as disabled are skipped.
        """
        # Load configuration and initialize plugin lists
        config, disabled_plugins = self._load_plugin_configuration()
        if config is None:
            return

        valid_plugins = []
        plugin_metadata = []

        # Walk through the plugin directory recursively
        sys.path.append(self.plugins_dir)
        for root, dirs, files in os.walk(self.plugins_dir):
            # Exclude the 'examples' folder
            if "examples" in dirs:
                dirs.remove("examples")  # Skip the 'examples' folder

            for file_name in files:
                if file_name.endswith(".py") and file_name != "__init__.py":
                    module_name = file_name[:-3]  # Remove the .py extension
                    module_path = (
                        os.path.relpath(os.path.join(root, file_name), self.plugins_dir)
                        .replace("/", ".")
                        .replace(".py", "")
                    )
                    file_path = os.path.join(root, file_name)
                    self.plugins_path[module_name] = file_path

                    self._process_plugin(
                        module_name,
                        module_path,
                        disabled_plugins,
                        valid_plugins,
                        plugin_metadata,
                    )

        # Walk through custom path plugin directory recursively
        # FIXME: create a function to reuse this logic
        sys.path.append(self.user_plugins_dir)
        for root, dirs, files in os.walk(self.user_plugins_dir):
            for file_name in files:
                if file_name.endswith(".py") and file_name != "__init__.py":
                    module_name = file_name[:-3]  # Remove the .py extension
                    root = root.split("config/waypanel/plugins")[-1]
                    module_path = (
                        os.path.relpath(os.path.join(root, file_name))
                        .replace("/", ".")
                        .replace(".py", "")
                    )
                    file_path = os.path.join(root, file_name)
                    self.plugins_path[module_name] = file_path

                    self._process_plugin(
                        module_name,
                        module_path,
                        disabled_plugins,
                        valid_plugins,
                        plugin_metadata,
                    )

        # Update the [plugins] section in the TOML configuration
        self._update_plugin_configuration(config, valid_plugins, disabled_plugins)

        # Initialize sorted plugins
        self._initialize_sorted_plugins(plugin_metadata)

    def plugins_base_path(self):
        try:
            # Try to locate the installed 'waypanel' module
            waypanel_module_spec = importlib.util.find_spec("waypanel")
            if waypanel_module_spec is None:
                raise ImportError("The 'waypanel' module could not be found.")

            # Get the root path of the module (e.g. site-packages/waypanel or dev dir)
            waypanel_module_path = waypanel_module_spec.origin  # points to __init__.py

            # Traverse up until we find the "waypanel" folder
            while os.path.basename(waypanel_module_path) != "waypanel":
                waypanel_module_path = os.path.dirname(waypanel_module_path)

            # At this point, waypanel_module_path points to the base package folder
            plugin_path = os.path.join(waypanel_module_path, "plugins")

            # If it exists in the installed layout, return it
            if os.path.exists(plugin_path):
                return plugin_path

        except ImportError:
            self.logger.debug(
                "No installed 'waypanel' module found. Trying dev paths..."
            )

        # Fallback 1: Check if we are running from source root (i.e. /path/to/waypanel/plugins/)
        dev_plugins_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "plugins")
        )
        if os.path.exists(dev_plugins_path):
            self.logger.warning(f"Falling back to dev plugin path: {dev_plugins_path}")
            return dev_plugins_path

        # Fallback 2: Check if we are inside the inner 'waypanel/' directory after git clone
        # e.g., waypanel/waypanel/plugins
        inner_plugins_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "plugins")
        )
        if os.path.exists(inner_plugins_path):
            self.logger.warning(
                f"Falling back to inner plugin path: {inner_plugins_path}"
            )
            return inner_plugins_path

        # Fallback 3: Check if we're one level above inner package (for direct execution)
        # i.e., waypanel/src/.. -> waypanel/plugins
        alt_plugins_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "plugins")
        )
        if os.path.exists(alt_plugins_path):
            self.logger.warning(
                f"Falling back to alternate dev plugin path: {alt_plugins_path}"
            )
            return alt_plugins_path

        # Final fallback: Warn user about missing plugin path
        self.logger.error("Could not find plugins directory in any known location.")
        raise FileNotFoundError(
            "Plugins directory not found. Please ensure you are running from a valid development or install directory."
        )

    def reload_plugin(self, plugin_name):
        """
        Reload a single plugin dynamically by its name.
        Args:
            plugin_name (str): The name of the plugin to reload.
        """
        # Ensure the plugin name has a trailing dot for comparison
        # Check if the plugin exists in the plugins_path dictionary
        if plugin_name not in self.plugins_path:
            self.logger.error(
                f"Plugin '{plugin_name}' not found in plugins_path. Skipping reload."
            )
            return

        try:
            # Disable and remove the existing plugin instance
            self.disable_plugin(plugin_name)
            if plugin_name in self.plugins:
                del self.plugins[plugin_name]

            # Get the file path from self.plugins_path
            file_path = self.plugins_path[plugin_name]
            relative_path = os.path.relpath(file_path, self.plugins_dir).replace(
                "/", "."
            )[:-3]  # Remove .py extension

            module_path = self.plugins_import[plugin_name]

            # Reload the module
            if module_path in sys.modules:
                module = sys.modules[module_path]
                importlib.reload(module)  # Reload the existing module
            else:
                module = importlib.import_module(module_path)  # Re-import the module

            # Process the plugin metadata for the reloaded plugin
            valid_plugins = []
            plugin_metadata = []
            self._process_plugin(
                plugin_name, relative_path, [], valid_plugins, plugin_metadata
            )

            # Initialize the plugin using _initialize_sorted_plugins
            if plugin_metadata:
                self.enable_plugin(plugin_name, plugin_metadata)
                self.logger.info(f"Reloaded and initialized plugin: {plugin_name}")
            else:
                self.logger.error(
                    f"Failed to process metadata for plugin: {plugin_name}"
                )

        except ModuleNotFoundError as e:
            self.logger.error(
                error=e,
                message=f"Failed to reload plugin '{plugin_name}': {e}",
                level="error",
            )
        except Exception as e:
            self.logger.error(
                error=e,
                message=f"Error reloading plugin '{plugin_name}': {e}",
                level="error",
            )

    def _load_plugin_configuration(self):
        """
        Load plugin-specific settings from `waypanel.toml`.

        Parses the `[plugins]` section to:
            - Determine which plugins are enabled/disabled
            - Allow individual plugins to read their own config blocks

        Returns:
            Tuple[Dict, List]: (config_dict, disabled_plugins_list)
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
            disabled_plugins = config["plugins"]["disabled"].split()
            return config, disabled_plugins
        except Exception as e:
            self.logger.error(
                error=e,
                message=f"Failed to load configuration file: {e}",
                level="error",
            )
            return None, None

    def _process_plugin(
        self, module_name, module_path, disabled_plugins, valid_plugins, plugin_metadata
    ):
        """Process and validate a single plugin."""

        # Skipping files with _name_conventions
        if module_name.startswith("_"):
            return

        if module_name in disabled_plugins:
            self.logger.info(f"Skipping plugin listed in 'disabled': {module_name}")
            return

        try:
            # Import the plugin module dynamically
            module = importlib.import_module(module_path)

            is_plugin_enabled = getattr(module, "ENABLE_PLUGIN", True)

            # Check if the plugin has required functions
            if not hasattr(module, "get_plugin_placement") or not hasattr(
                module, "initialize_plugin"
            ):
                self.logger.error(
                    f"Module {module_name} is missing required functions. Skipping."
                )
                return

            # Check if the plugin is enabled via ENABLE_PLUGIN
            if not is_plugin_enabled:
                self.logger.info(f"Skipping disabled plugin: {module_name}")
                return

            # Add the plugin to the plugins_import dictionary
            self.plugins_import[module_name] = module_path

            self.logger.debug(f"Registered plugin: {module_name} -> {module_path}")

            # Validate DEPS list
            has_plugin_deps = getattr(module, "DEPS", [])
            if not self.validate_deps_list(has_plugin_deps, module_name):
                self.logger.error(
                    error=ValueError("Invalid DEPS list."),
                    message=f"Plugin '{module_name}' has an invalid DEPS list. Skipping.",
                    level="error",
                )
                return

            # Get position, order, and optional priority
            position_result = module.get_plugin_placement(self.panel_instance)
            # don't append any widget except if a position is found
            position = "background"
            priority = 0
            order = 0
            if position_result != "background":
                if position_result:
                    if self.utils.validate_tuple(
                        position_result, name="position_result"
                    ):
                        if len(position_result) == 3:
                            position, order, priority = position_result
                        else:
                            position, order = position_result
                            priority = 0
                    else:
                        self.logger.error(
                            f"Invalid position result for plugin {module_name}. Skipping."
                        )
                        return

            # Add to valid plugins and metadata
            valid_plugins.append(module_name)
            plugin_metadata.append((module, position, order, priority))
        except Exception as e:
            self.logger.error("Failed to initialize the plugin:")
            print(f" {e}:\n{traceback.format_exc()}")

    def _update_plugin_configuration(self, config, valid_plugins, disabled_plugins):
        """Update the [plugins] section in the TOML configuration."""
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
        config["plugins"]["list"] = " ".join(valid_plugins)
        config["plugins"]["disabled"] = " ".join(disabled_plugins)

        with open(waypanel_config_path, "w") as f:
            toml.dump(config, f)

    def validate_deps_list(self, deps_list, module_name):
        """
        Validates the DEPS list to ensure it contains only valid plugin names.

        Args:
            deps_list (list): The list of dependencies to validate.
            module_name (str): The name of the plugin being processed.

        Returns:
            bool: True if the list is valid, False otherwise.
        """
        if not self.utils.validate_list(deps_list, "deps_list"):
            return False

        for index, dep in enumerate(deps_list):
            if not self.utils.validate_string(
                dep, "[dep] item from enumerate(deps_list)"
            ):
                return False
            if not self.utils.validate_string(dep):
                return False

        return True

    def handle_set_widget(self, widget_action, widget_to_append, target, module_name):
        """
        Handle appending or setting content for a plugin's widget.
        Args:
            widget_action (str): The action to perform ("append" or "set_content").
            widget_to_append (Gtk.Widget or list): The widget(s) to append or set.
            target (Gtk.Container): The target container (e.g., self.left_panelpanel, self.right_panel).
            module_name (str): The name of the plugin (used to create a dedicated FlowBox).
        """
        if widget_action == "append":
            # Append the widget(s) to the target box
            if isinstance(widget_to_append, list):
                for widget in widget_to_append:
                    # Create a dedicated FlowBox for the plugin if it doesn't exist
                    if f"{module_name}_box" not in self.plugin_containers:
                        self.plugin_containers[f"{module_name}_box"] = Gtk.FlowBox()
                        self.plugin_containers[f"{module_name}_box"].set_valign(
                            Gtk.Align.START
                        )
                        self.plugin_containers[f"{module_name}_box"].set_halign(
                            Gtk.Align.FILL
                        )
                        self.plugin_containers[f"{module_name}_box"].set_selection_mode(
                            Gtk.SelectionMode.NONE
                        )
                        self.plugin_containers[f"{module_name}_box"].add_css_class(
                            "box-widgets"
                        )  # Add CSS class

                        # Add the plugin's FlowBox to the target container if not already added
                        if (
                            self.plugin_containers[f"{module_name}_box"].get_parent()
                            is None
                        ):
                            GLib.idle_add(
                                target.append,
                                self.plugin_containers[f"{module_name}_box"],
                            )

                    # Clean up the FlowBox before appending new widgets
                    self.plugin_containers[f"{module_name}_box"].remove_all()

                    # Append the widget to the plugin's dedicated FlowBox
                    GLib.idle_add(
                        self.plugin_containers[f"{module_name}_box"].append, widget
                    )
            else:
                # Single widget case
                if f"{module_name}_box" not in self.plugin_containers:
                    self.plugin_containers[f"{module_name}_box"] = Gtk.FlowBox()
                    self.plugin_containers[f"{module_name}_box"].set_valign(
                        Gtk.Align.START
                    )
                    self.plugin_containers[f"{module_name}_box"].set_halign(
                        Gtk.Align.FILL
                    )
                    self.plugin_containers[f"{module_name}_box"].set_selection_mode(
                        Gtk.SelectionMode.NONE
                    )

                    self.plugin_containers[f"{module_name}_box"].add_css_class(
                        "box-widgets"
                    )  # Add CSS class

                    # Add the plugin's FlowBox to the target container if not already added
                    if (
                        self.plugin_containers[f"{module_name}_box"].get_parent()
                        is None
                    ):
                        GLib.idle_add(
                            target.append, self.plugin_containers[f"{module_name}_box"]
                        )

                # Clean up the FlowBox before appending new widgets
                self.plugin_containers[f"{module_name}_box"].remove_all()

                # Append the widget to the plugin's dedicated FlowBox
                GLib.idle_add(
                    self.plugin_containers[f"{module_name}_box"].append,
                    widget_to_append,
                )

        elif widget_action == "set_content":
            # Set the widget(s) as the content of the target container
            if isinstance(widget_to_append, list):
                for widget in widget_to_append:
                    GLib.idle_add(target.set_content, widget)
            else:
                GLib.idle_add(target.set_content, widget_to_append)

    def _initialize_sorted_plugins(self, plugin_metadata):
        """
        Sort plugins by priority (descending), then order (ascending),
        and initialize them in sequence.

        Ensures:
            - 'event_manager' is always loaded first
            - Plugins with dependencies are initialized after their deps

        Args:
            plugin_metadata: List of tuples containing module info and metadata
        """
        # Sort plugins by priority (descending), then by order (ascending)
        plugin_metadata.sort(key=lambda x: (-x[3], x[2]))

        # Check if 'event_manager' exists in plugin_metadata
        event_manager_metadata = None
        for metadata in plugin_metadata:
            if metadata[0].__name__.endswith("event_manager"):
                event_manager_metadata = metadata
                plugin_metadata.remove(metadata)
                break

        # If 'event_manager' was found, insert it at the beginning to load first
        if event_manager_metadata:
            plugin_metadata.insert(0, event_manager_metadata)

        # Remove 'event_handler_decorator' if exists, so we can append at end
        event_handler_decorator_metadata = None
        for i, metadata in enumerate(plugin_metadata):
            if metadata[0].__name__.endswith("event_handler_decorator"):
                event_handler_decorator_metadata = metadata
                del plugin_metadata[i]
                break

        # Append event_handler_decorator at the end
        # This plugin only works for plugins that load earlier
        if event_handler_decorator_metadata:
            plugin_metadata.append(event_handler_decorator_metadata)

        # Initialize plugins
        def initialize_plugin_with_deps(module, position, order, priority):
            module_name = module.__name__.split(".")[-1]
            plugin_name = module.__name__.split(".src.plugins.")[-1]

            # Check for dependencies
            has_plugin_deps = getattr(module, "DEPS", [])

            if has_plugin_deps:
                # Delay initialization until all dependencies are ready
                deps_satisfied = all(dep in self.plugins for dep in has_plugin_deps)
                if not deps_satisfied:
                    self.logger.debug(
                        f"Delaying initialization of {plugin_name} due to missing dependencies."
                    )
                    GLib.idle_add(
                        lambda: initialize_plugin_with_deps(
                            module, position, order, priority
                        ),
                    )
                    return

            # Initialize the plugin
            try:
                plugin_instance = module.initialize_plugin(self.panel_instance)

                # Call the on_start method if it exists
                if hasattr(plugin_instance, "on_start"):
                    plugin_instance.on_start()

                self.logger.info(f"Initialized plugin: {plugin_name}")
                self.plugins[module_name] = plugin_instance

                # Append widget to the panel if applicable
                target_box = self._get_target_panel_box(position, plugin_name)
                if target_box is None:
                    self.logger.error(
                        f"No target box found for plugin {plugin_name} with position {position}."
                    )
                    return

                # Background plugins have no widgets to append
                if position == "background":
                    self.logger.info(
                        f"Plugin [{plugin_name}] initialized as a background plugin."
                    )
                    return

                # Check if the plugin has an set_widget method
                if not hasattr(plugin_instance, "set_widget"):
                    return

                widget_to_append = plugin_instance.set_widget()[0]
                widget_action = plugin_instance.set_widget()[1]

                self.handle_set_widget(
                    widget_action, widget_to_append, target_box, module_name
                )

            except Exception as e:
                self.logger.error(f"Failed to initialize plugin '{plugin_name}': {e}")
                print(traceback.format_exc())

        # Process all plugins
        for module, position, order, priority in plugin_metadata:
            initialize_plugin_with_deps(module, position, order, priority)

    def _get_target_panel_box(self, position, plugin_name=None):
        """
        Determines where to place the plugin's widget in the panel.

        Args:
            position (str): A string like 'top-panel-left', 'left-panel-top', etc.
            plugin_name (str): Name of the plugin (for logging)

        Returns:
            object: Target box/widget if found, or 'background' if no UI is needed.
            None: If invalid position or missing target.
        """
        self.position_mapping = {
            # Top Panel
            "top-panel": "top_panel",
            "top-panel-left": "top_panel_box_left",
            "top-panel-center": "top_panel_box_center",
            "top-panel-right": "top_panel_box_right",
            "top-panel-systray": "top_panel_box_systray",
            "top-panel-after-systray": "top_panel_box_for_buttons",
            # Bottom Panel
            "bottom-panel": "bottom_panel",
            "bottom-panel-left": "bottom_panel_box_left",
            "bottom-panel-center": "bottom_panel_box_center",
            "bottom-panel-right": "bottom_panel_box_right",
            # Left Panel
            "left-panel": "left_panel",
            "left-panel-top": "left_panel_box_top",
            "left-panel-center": "left_panel_box_center",
            "left-panel-bottom": "left_panel_box_bottom",
            # Right Panel
            "right-panel": "right_panel",
            "right-panel-top": "right_panel_box_top",
            "right-panel-center": "right_panel_box_center",
            "right-panel-bottom": "right_panel_box_bottom",
            # Background (no UI)
            "background": "background",  # Special case
        }

        target_attr = self.position_mapping.get(position)

        if target_attr is None:
            self.logger.error(
                f"Invalid position '{position}' for plugin {plugin_name}."
            )
            return None

        # Handle background plugins
        if target_attr == "background":
            self.logger.debug(f"Plugin {plugin_name} is a background plugin.")
            return "background"

        # Check if the target attribute exists on the panel instance
        if not hasattr(self.panel_instance, target_attr):
            self.logger.warning(
                f"Panel box '{target_attr}' is not yet initialized for plugin {plugin_name}."
            )
            return None

        return getattr(self.panel_instance, target_attr)
