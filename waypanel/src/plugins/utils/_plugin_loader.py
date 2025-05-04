import os
import importlib
import toml
from src.core.utils import Utils
from gi.repository import GLib, Gtk
import sys
import shutil
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
        self.cache_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../custom/cache")
        )
        self.user_plugins_dir = os.path.expanduser("~/.config/waypanel/plugins")
        # Clear the cache and copy plugins before loading
        self._clear_and_copy_plugins()

    def _clear_and_copy_plugins(self):
        """Clear the cache directory and copy plugins from the user's custom directory."""
        try:
            # Ensure the cache directory exists
            os.makedirs(self.cache_dir, exist_ok=True)

            # Clear the cache directory
            for item in os.listdir(self.cache_dir):
                item_path = os.path.join(self.cache_dir, item)
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)

            self.logger.info("Cleared plugin cache directory.")

            # Check if the user's custom plugin directory exists
            if not os.path.exists(self.user_plugins_dir):
                self.logger.warning(
                    f"User plugin directory not found: {self.user_plugins_dir}"
                )
                return

            # Copy plugins from the user's directory to the cache
            for item in os.listdir(self.user_plugins_dir):
                print(item)
                source_path = os.path.join(self.user_plugins_dir, item)
                destination_path = os.path.join(self.cache_dir, item)

                if os.path.isfile(source_path):
                    shutil.copy2(source_path, destination_path)
                elif os.path.isdir(source_path):
                    shutil.copytree(source_path, destination_path)

            self.logger.info(
                f"Copied plugins from {self.user_plugins_dir} to {self.cache_dir}."
            )

        except Exception as e:
            self.logger.error(f"Error during plugin cache update: {e}", exc_info=True)

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

        # Update the [plugins] section in the TOML configuration
        self._update_plugin_configuration(config, valid_plugins, disabled_plugins)

        # Initialize sorted plugins
        self._initialize_sorted_plugins(plugin_metadata)

    def plugins_base_path(self):
        try:
            # Try to locate the installed 'waypanel' module
            waypanel_module_spec = importlib.util.find_spec("waypanel")  # pyright: ignore
            if waypanel_module_spec is None:
                raise ImportError("The 'waypanel' module could not be found.")
            waypanel_module_path = os.path.dirname(waypanel_module_spec.origin)
        except ImportError:
            # Fallback to the script's directory for development environments
            waypanel_module_path = os.path.dirname(os.path.abspath(__file__))
            self.logger.warning("Falling back to script directory for plugin loading.")

        return os.path.join(waypanel_module_path, "src", "plugins")

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
            module_full_path = f"src.plugins.{module_path}"
            module = importlib.import_module(module_full_path)

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
            self.plugins_import[module_name] = module_full_path
            self.logger.debug(f"Registered plugin: {module_name} -> {module_full_path}")

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
            position: A string (e.g., 'top-panel-left') or None/'background'
            plugin_name: Name of the plugin for logging

        Returns:
            str: Target box name, or 'background' if plugin has no UI.
        """
        self.position_mapping = {
            "top-panel-left": "top_panel_box_left",
            "top-panel-right": "top_panel_box_right",
            "top-panel-center": "top_panel_box_center",
            "top-panel-systray": "top_panel_box_systray",
            "top-panel-after-systray": "top_panel_box_for_buttons",
            "left-panel": "left_panel",
            "right-panel": "right_panel",
            "bottom-panel": "bottom_panel",
            "top-panel": "top_panel",
            "background": "background",  # Special case for background plugins
        }

        target_attr = self.position_mapping.get(position)
        if target_attr is None:
            self.logger.error(
                f"Invalid position '{position}' for plugin {plugin_name}."
            )
            return None

        # Handle special case for "background"
        if target_attr == "background":
            self.logger.debug(f"Plugin {plugin_name} is a background plugin.")
            return "background"

        # Validate that the target attribute exists on the panel instance
        if not hasattr(self.panel_instance, target_attr):
            self.logger.warning(
                f"Panel box '{target_attr}' is not yet initialized for plugin {plugin_name}."
            )
            return None

        return getattr(self.panel_instance, target_attr)
