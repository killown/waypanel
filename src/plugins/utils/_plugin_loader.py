import os
import importlib
import toml
from src.core.utils import Utils
from gi.repository import GLib, Gtk
import sys
import traceback
from pathlib import Path
from src.shared.data_helpers import DataHelpers
from src.shared.config_handler import ConfigHandler


class PluginLoader:
    """
    Manages the lifecycle of plugins for Waypanel, from discovery and validation
    to dynamic loading and initialization.

    This class serves as the core engine for Waypanel's modularity. It systematically
    scans for plugins, validates their structure, and orchestrates their loading
    to ensure a stable and consistent panel environment.

    ### Key Responsibilities
    - **Plugin Discovery**: Automatically finds all plugin modules in both the main
      `src` directory and any user-defined paths.
    - **Configuration Handling**: Reads `config.toml` to determine the status of each
      plugin (enabled or disabled), allowing for a user-customizable setup.
    - **Structural Validation**: Verifies that each plugin adheres to the required
      interface, ensuring the presence of essential functions like
      `get_plugin_placement` and `initialize_plugin` before loading.
    - **Dependency Management**: Checks for and validates any specified plugin
      dependencies to prevent loading issues.
    - **Initialization**: Initializes valid plugins in a non-blocking manner,
      collecting critical metadata (position, order, priority) to prepare them
      for seamless integration into the panel.

    ### Usage Example
    ```python
    plugin_loader = PluginLoader(panel_instance, logger, config_path)
    plugin_loader.load_plugins()
    ```
    """

    def __init__(self, panel_instance):
        """
        Initialize the PluginLoader with core components.

        Args:
            panel_instance: Main Panel object (used for plugin access and event management).
            logger: Logger instance for structured logging.
            config_path: Path to `config.toml` for plugin enable/disable settings.
        """
        self.panel_instance = panel_instance
        self.logger = self.panel_instance.logger
        self.utils = Utils(panel_instance)
        self.plugins = {}
        self.plugins_path = {}
        self.plugins_import = {}
        self.plugin_containers = {}
        self.plugins_dir = self.plugins_base_path()
        self.position_mapping = {}
        self.data_helper = DataHelpers()
        self.config_handler = ConfigHandler("waypanel", panel_instance)
        self.config_path = self.config_handler.config_path
        self.user_plugins_dir = os.path.join(
            self.get_real_user_home(), ".local", "share", "waypanel", "plugins"
        )

    def get_real_user_home(self):
        """Determine the real user's home directory, even when running with elevated privileges.

        This function identifies the original user's home path by checking environment variables
        commonly set when using privilege escalation tools like sudo or pkexec. It ensures correct
        behavior whether running as root or a regular user.

        Returns:
            str: The absolute path to the real user's home directory.
        """
        # Try SUDO_USER first
        if "SUDO_USER" in os.environ:
            return os.path.expanduser(f"~{os.environ['SUDO_USER']}")
        # Fallback to PKEXEC_UID (used by pkexec)
        elif "PKEXEC_UID" in os.environ:
            return os.path.expanduser(f"~{os.environ['PKEXEC_UID']}")
        # Default case (non-root or not running via sudo/pkexec)
        return os.path.expanduser("~")

    def disable_plugin(self, plugin_name):
        """Disable a plugin by name.

        Safely stops and disables a plugin instance, ensuring proper cleanup
        by calling available lifecycle methods. Handles both plugins that
        support custom disable logic and those that don't.

        Args:
            plugin_name (str): The name of the plugin to disable.
        """
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
        """Enable a plugin by name.

        Initializes and activates a plugin using the provided metadata,
        ensuring proper error handling during the process.

        Args:
            plugin_name (str): The name of the plugin to enable.
            plugin_metadata (list or None): Metadata required for initializing the plugin.
        """
        if plugin_name not in self.plugins_path:
            self.logger.error(
                f"Plugin '{plugin_name}' not found in plugins_path. Skipping enable."
            )
            return

        try:
            # Initialize the plugin using _initialize_sorted_plugins
            if plugin_metadata:
                GLib.idle_add(self._initialize_sorted_plugins, plugin_metadata)
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

    def _find_plugins_in_dir(
        self, directory_path, disabled_plugins, valid_plugins, plugin_metadata
    ):
        """
        Recursively walks a specified directory to find and process plugin files.

        This method serves as a modular helper for the `load_plugins` method. It searches
        for Python files (`.py`) within a given `directory_path`, excluding the
        `__init__.py` and any `examples` folder. For each valid plugin file found, it
        extracts essential metadata (module name, file path) and delegates the
        processing to `_process_plugin`.

        Args:
            directory_path (str): The absolute path of the directory to search for plugins.
            disabled_plugins (list): A list of plugin names that should be skipped.
            valid_plugins (list): A list that will be populated with the names of all
                                  valid plugins found.
            plugin_metadata (list): A list of tuples that will be populated with plugin
                                    metadata for later initialization.
        """
        sys.path.append(directory_path)
        for root, dirs, files in os.walk(directory_path):
            if "examples" in dirs:
                dirs.remove("examples")

            for file_name in files:
                if file_name.endswith(".py") and file_name != "__init__.py":
                    module_name = file_name[:-3]
                    module_path = (
                        os.path.relpath(os.path.join(root, file_name), directory_path)
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

    def load_plugins(self):
        """
        Loads and prepares all plugins from built-in and custom directories.

        This method orchestrates the entire plugin discovery and preparation process. It
        first loads the application's configuration to identify disabled plugins. It then
        calls the `_find_plugins_in_dir` helper to search both the core and user-defined
        plugin directories, collecting metadata for all valid plugins. After discovery,
        it updates the configuration file with any new plugins found. Finally, it
        initiates the non-blocking initialization process by calling
        `_initialize_sorted_plugins`.

        This separation of concerns ensures that the application's startup is not
        blocked by file system operations or plugin initialization, resulting in a
        responsive user experience.
        """
        config, disabled_plugins = self._load_plugin_configuration()
        if config is None:
            return

        valid_plugins = []
        plugin_metadata = []

        # Find and process plugins from the main directory
        self._find_plugins_in_dir(
            self.plugins_dir, disabled_plugins, valid_plugins, plugin_metadata
        )

        # Find and process plugins from the user's custom directory
        self._find_plugins_in_dir(
            self.user_plugins_dir, disabled_plugins, valid_plugins, plugin_metadata
        )

        # Update the [plugins] section in the TOML configuration
        self._update_plugin_configuration(config, valid_plugins, disabled_plugins)

        # Initialize sorted plugins asynchronously using GLib.idle_add
        self._initialize_sorted_plugins(plugin_metadata)

    def plugins_base_path(self):
        """
        Determines the base path where plugins are located.
        """
        try:
            waypanel_module_spec = importlib.util.find_spec("waypanel")

            # CRITICAL FIX: Check if the origin is None before proceeding.
            # If a module is not from a file (e.g., built-in), its origin will be None.
            if waypanel_module_spec and waypanel_module_spec.origin:
                waypanel_module_path = waypanel_module_spec.origin
                while os.path.basename(waypanel_module_path) != "waypanel":
                    waypanel_module_path = os.path.dirname(waypanel_module_path)

                plugin_path = os.path.join(waypanel_module_path, "plugins")
                if os.path.exists(plugin_path):
                    return plugin_path

        except ImportError:
            self.logger.debug(
                "No installed 'waypanel' module found. Trying dev paths..."
            )

        # Fallback paths for a development environment
        fallback_paths = [
            os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "plugins")
            ),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugins")),
            os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "plugins")
            ),
        ]

        for path in fallback_paths:
            if os.path.exists(path):
                self.logger.warning(f"Falling back to dev plugin path: {path}")
                return path

        self.logger.error("Could not find plugins directory in any known location.")
        raise FileNotFoundError(
            "Plugins directory not found. Please ensure you are running from a valid development or install directory."
        )

    def reload_plugin(self, plugin_name):
        """
        Initiates a dynamic, non-disruptive reload of a single plugin, effectively
        reincarnating it with the latest code and configuration from disk.

        This method is the heart of Waypanel's hot-reloading capability,
        performing a surgical removal and a graceful re-initialization of a plugin
        without requiring a full application restart. It ensures that changes made
        to a plugin's source code are instantly reflected in the running application,
        facilitating rapid development and debugging.

        The reload process is a precise, multi-stage ritual:

        1.  **Decommissioning**: The existing plugin instance is meticulously
            deactivated and purged from the system's active memory to prevent
            resource leaks or conflicts.

        2.  **Amnesic Reload**: The plugin's module is reloaded from its source file,
            effectively wiping any lingering state and ensuring the most recent
            implementation is loaded into Python's module cache.

        3.  **Metabolic Re-processing**: The reloaded plugin is re-validated and its
            metadata is re-analyzed by `_process_plugin`, confirming its integrity
            and gathering its essential parameters (position, order, priority).

        4.  **Resurrection**: The plugin is re-initialized, its widgets are
            re-instantiated, and it is seamlessly reintegrated into the panel's
            layout, ready to resume its function with its updated logic.

        Args:
            plugin_name (str): The symbolic name of the plugin to be resurrected.
        """
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

            # Retrieve the correct import path
            module_path = self.plugins_import.get(plugin_name)
            if not module_path:
                self.logger.error(
                    f"Module path for plugin '{plugin_name}' not found. Cannot reload."
                )
                return

            # Reload the module
            if module_path in sys.modules:
                module = sys.modules[module_path]
                importlib.reload(module)
            else:
                module = importlib.import_module(module_path)

            # Process the plugin metadata for the reloaded plugin
            valid_plugins = []
            plugin_metadata = []
            self._process_plugin(
                plugin_name,
                module_path,
                self.disabled_plugins,
                valid_plugins,
                plugin_metadata,
            )

            # Initialize the plugin if metadata was successfully processed
            if plugin_metadata:
                for module, position, order, priority in plugin_metadata:
                    plugin_instance = module.initialize_plugin(self.panel_instance)
                    self.plugins[plugin_name] = {
                        "instance": plugin_instance,
                        "module": module,
                        "position": position,
                        "order": order,
                        "priority": priority,
                    }
                self.logger.info(f"Reloaded and initialized plugin: {plugin_name}")
            else:
                self.logger.error(
                    f"Failed to process metadata for plugin: {plugin_name}"
                )

        except Exception as e:
            self.logger.error(f"Error reloading plugin '{plugin_name}': {e}")
            print(f" {e}:\n{traceback.format_exc()}")

    def _load_plugin_configuration(self):
        """
        Load plugin-specific settings from `config.toml`.

        Parses the `[plugins]` section to:
            - Determine which plugins are enabled/disabled
            - Allow individual plugins to read their own config blocks

        Returns:
            Tuple[Dict, List]: (config_dict, disabled_plugins_list)
        """
        try:
            if not os.path.exists(self.config_handler.config_path):
                self.logger.error(
                    f"Configuration file not found at '{self.config_handler.config_path}'."
                )
                return None, None

            with open(self.config_handler.config_file, "r") as f:
                config = toml.load(f)

            # Ensure the [plugins] section exists
            if "plugins" not in config:
                config["plugins"] = {"list": "", "disabled": ""}

            # Parse the disabled plugins list
            self.disabled_plugins = config["plugins"]["disabled"].split()
            return config, self.disabled_plugins
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
        """Process and validate a single plugin.

        Validates the plugin's structure, checks for required functions,
        verifies dependencies, and prepares it for initialization if valid.

        Args:
            module_name (str): Name of the plugin module.
            module_path (str): Path to the plugin module.
            disabled_plugins (list): List of plugins that are currently disabled.
            valid_plugins (list): List of plugins that have passed validation so far.
            plugin_metadata (list): List to store collected metadata for valid plugins.
        """

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
                    if self.data_helper.validate_tuple(
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
        """
        Persists the plugin configuration to the `config.toml` file.

        This method is responsible for saving the current state of discovered and
        disabled plugins back to the application's configuration file. It takes the
        in-memory configuration object, updates the plugin lists, and then
        atomically writes the changes to disk.

        Args:
            config (dict): The in-memory TOML configuration object.
            valid_plugins (list): A list of strings containing the names of
                                  all plugins that were successfully loaded.
            disabled_plugins (list): A list of strings containing the names of
                                     all plugins explicitly disabled in the config.

        Workflow:
            1. **Path Resolution**: Constructs the absolute path to the `config.toml` file.
            2. **Data Update**: Updates the `list` and `disabled` keys within the `[plugins]`
               section of the `config` dictionary. Plugin names are joined into a
               space-separated string for persistence.
            3. **File Dump**: Uses the `toml` library to write the entire `config`
               dictionary to the specified file, overwriting the previous content.
        """
        waypanel_config_path = os.path.join(
            self.config_handler.config_path, "config.toml"
        )

        # Update the in-memory config object
        config["plugins"]["list"] = " ".join(valid_plugins)
        config["plugins"]["disabled"] = " ".join(disabled_plugins)

        # Dump the updated config to the file
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
        if not self.data_helper.validate_list(deps_list, "deps_list"):
            return False

        for index, dep in enumerate(deps_list):
            if not self.data_helper.validate_string(
                dep, "[dep] item from enumerate(deps_list)"
            ):
                return False
            if not self.data_helper.validate_string(dep):
                return False

        return True

    def handle_set_widget(self, widget_action, widget_to_append, target, module_name):
        """
        Handles the placement of a plugin's widget on the panel.

        This method orchestrates the visual integration of a plugin's widget into the panel's layout. It supports
        two primary actions: appending a widget to a container and setting a widget as a container's content.
        For plugins that return multiple widgets, it ensures they are organized within a dedicated `Gtk.FlowBox`.

        Args:
            widget_action (str): The action to perform. Must be either "append" or "set_content".
            widget_to_append (Gtk.Widget or list): The widget instance(s) to be placed on the panel.
                                                    If a list, the widgets will be appended to a dedicated container.
            target (Gtk.Container): The target panel container (e.g., `self.left_panel`, `self.top_panel`).
            module_name (str): The name of the plugin module, used to create a unique identifier for its container.
        """
        if widget_action == "append":
            # Consolidate widget_to_append into a list for consistent handling
            widgets = (
                widget_to_append
                if isinstance(widget_to_append, list)
                else [widget_to_append]
            )

            # Ensure a dedicated FlowBox exists for the plugin
            box_name = f"{module_name}_box"
            if box_name not in self.plugin_containers:
                flow_box = Gtk.FlowBox()
                flow_box.set_valign(Gtk.Align.START)
                flow_box.set_halign(Gtk.Align.FILL)
                flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
                flow_box.add_css_class("box-widgets")
                self.plugin_containers[box_name] = flow_box

                # Append the newly created FlowBox to the target container
                GLib.idle_add(target.append, flow_box)
            else:
                flow_box = self.plugin_containers[box_name]

            # Clean up the FlowBox before appending new widgets
            GLib.idle_add(flow_box.remove_all)

            # Append the widget(s) to the plugin's dedicated FlowBox
            for widget in widgets:
                GLib.idle_add(flow_box.append, widget)

        elif widget_action == "set_content":
            # Set the widget as the content of the target container
            widgets = (
                widget_to_append
                if isinstance(widget_to_append, list)
                else [widget_to_append]
            )
            for widget in widgets:
                GLib.idle_add(target.set_content, widget)

    def _initialize_sorted_plugins(self, plugin_metadata):
        """
        Sorts and schedules plugins for non-blocking initialization.

        This method prepares plugin data for a responsive startup. It sorts plugins based on a defined order
        and then schedules each for initialization using `GLib.idle_add`. This ensures that long-running
        tasks do not block the main UI thread.

        Args:
            plugin_metadata (list): A list of tuples, where each tuple contains
                                    the module, position, order, and priority
                                    of a discovered plugin.

        Workflow:
            1. **Sorting**: Sorts plugins by priority (descending) and then by order (ascending).
            2. **Special Cases**: Handles the special cases of `event_manager` and `event_handler_decorator`,
               ensuring they are loaded first and last, respectively.
            3. **Scheduling**: Iterates through the sorted list and queues each plugin's
               initialization using `GLib.idle_add`, passing the necessary metadata to the
               `_initialize_plugin_with_deps` method.
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
        if event_handler_decorator_metadata:
            plugin_metadata.append(event_handler_decorator_metadata)

        # Schedule plugin initialization
        for module, position, order, priority in plugin_metadata:
            # The lambda function captures the arguments correctly
            GLib.idle_add(
                lambda m=module,
                p=position,
                o=order,
                pr=priority: self._initialize_plugin_with_deps(m, p, o, pr)
            )

    def _initialize_plugin_with_deps(self, module, position, order, priority):
        """
        Initializes a single plugin and its dependencies as a GLib idle callback.

        This method is designed to be called by `GLib.idle_add` to prevent a single
        plugin's initialization from blocking the main UI thread. It is a key part of
        the non-blocking startup process, ensuring the application remains responsive
        even with many or complex plugins.

        Args:
            module (module): The imported Python module of the plugin to be initialized.
            position (str): The panel position where the plugin's widget will be placed.
            order (int): The order of the plugin within its panel position.
            priority (int): The priority of the plugin, used for initial sorting.

        Workflow:
            1. **Dependency Check**: It first checks if the plugin has any dependencies defined
               in its `DEPS` attribute.
            2. **Non-Blocking Wait**: If dependencies are missing, the function returns `True`,
               which tells `GLib.idle_add` to re-queue this function for a later time. This
               ensures the event loop can continue running without waiting.
            3. **Initialization**: Once all dependencies are satisfied, it calls the plugin's
               `initialize_plugin` function to create an instance of the plugin.
            4. **Lifecycle Method**: If the plugin instance has an `on_start` method, it is
               called to perform any initial setup.
            5. **Widget Handling**: The function then retrieves the plugin's widget and its
               action (e.g., "append", "prepend") and handles adding it to the appropriate
               panel based on the `position` argument.

        Returns:
            bool: `True` if the plugin is re-queued for later due to missing dependencies;
                  `False` if initialization is complete or an error occurred.
        """
        module_name = module.__name__.split(".")[-1]
        plugin_name = module.__name__.split(".src.plugins.")[-1]

        # Check for dependencies
        has_plugin_deps = getattr(module, "DEPS", [])

        # Re-queue initialization if dependencies are not met
        if has_plugin_deps and not all(dep in self.plugins for dep in has_plugin_deps):
            self.logger.debug(
                f"Delaying initialization of {plugin_name} due to missing dependencies."
            )
            # Return True to reschedule this callback
            return True

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
                return False  # Stop the callback

            # Background plugins have no widgets to append
            if position == "background":
                self.logger.info(
                    f"Plugin [{plugin_name}] initialized as a background plugin."
                )
                return False  # Stop the callback

            # Check if the plugin has an set_widget method
            if not hasattr(plugin_instance, "set_widget"):
                return False  # Stop the callback

            widget_to_append = plugin_instance.set_widget()[0]
            widget_action = plugin_instance.set_widget()[1]

            self.handle_set_widget(
                widget_action, widget_to_append, target_box, module_name
            )

        except Exception as e:
            self.logger.error(f"Failed to initialize plugin '{plugin_name}': {e}")
            print(traceback.format_exc())

        return False  # Return False to stop the callback after it's done

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
            "top-panel-box-widgets-left": "top_panel_box_widgets_left",
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
