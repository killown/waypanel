import os
import importlib
import toml
from waypanel.src.core.utils import Utils
from gi.repository import GLib, Gtk
import sys


class PluginLoader:
    def __init__(self, panel_instance, logger, config_path):
        """
        The PluginLoader is responsible for discovering, validating, and initializing plugins
        from the `src.plugins` package. It ensures that plugins are loaded in the correct order,
        based on their priority and position, and integrates with the `waypanel.toml` configuration
        file to manage plugin settings.

        ### Design Philosophy
        The PluginLoader adheres to the principle of simplicity and modularity:
        - Plugins are designed to be self-contained and functional without requiring external dependencies.
        - Integration with `waypanel.toml` is optional, allowing plugin developers to decide whether
          their plugin needs configuration or can operate with default behavior.
        - This approach lowers the barrier for new plugin developers, as they can focus on core functionality
          without needing to understand or implement complex configuration management.

        ### Why Plugins Do Not Use Config by Default
        1. **Simplicity**: By not enforcing a centralized `Config` class, plugins remain lightweight and
           independent. Developers can create plugins with minimal boilerplate code.
        2. **Flexibility**: Plugins that do not require configuration can function immediately without
           additional setup. Only plugins that need user-defined settings (e.g., themes, intervals, or
           custom paths) should interact with `waypanel.toml`.
        3. **Separation of Concerns**: The PluginLoader itself does not impose configuration on plugins.
           Instead, it provides utilities (e.g., `_load_plugin_configuration`) to load and parse
           `waypanel.toml`, leaving it up to individual plugins to decide how to use this data.
        4. **Ease of Contribution**: New contributors can quickly create plugins without worrying about
           integrating with a centralized configuration system. They can later enhance their plugins to
           support configuration if needed.

        ### Responsibilities
        - **Dynamic Loading**: Discovers all available plugins in the `src.plugins` package.
        - **Validation**: Ensures that each plugin implements the required interface (e.g., `initialize_plugin`).
        - **Configuration Management**: Loads the `waypanel.toml` file to determine which plugins are enabled,
          disabled, or have custom settings.
        - **Sorting and Initialization**: Sorts plugins by priority and order, then initializes them in the
          correct sequence.

        ### Usage
        To use the PluginLoader:
        1. Instantiate the PluginLoader with the main panel object, logger, and configuration path.
        2. Call the `load_plugins` method to dynamically load and initialize all plugins.
        3. Access initialized plugins via the `plugins` dictionary.

        ### Example
        ```python
        plugin_loader = PluginLoader(panel_instance, logger, config_path)
        plugin_loader.load_plugins()
        dockbar_plugin = plugin_loader.plugins.get("dockbar")
        ```

        ### Notes
        - Plugins that require configuration should define their own logic for loading and using settings
          from `waypanel.toml`. A utility function like `load_config` can be provided to simplify this process.
        - Disabled plugins are skipped during initialization based on the `disabled` list in `waypanel.toml`.

        ### Methods
        - `_load_plugin_configuration`: Loads and parses the `waypanel.toml` file to determine plugin settings.
        - `_process_plugin`: Validates and processes a single plugin module.
        - `_update_plugin_configuration`: Updates the `waypanel.toml` file with the latest plugin list.
        - `_initialize_sorted_plugins`: Initializes plugins in the correct order based on priority and position.
        """
        self.panel_instance = panel_instance
        self.logger = logger
        self.config_path = config_path
        self.utils = Utils(panel_instance)
        self.plugins = {}
        self.plugins_path = {}
        self.plugin_containers = {}

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
            self.logger.error_handler.handle(
                error=e,
                message=f"Error enabling plugin '{plugin_name}': {e}",
                level="error",
            )

    def load_plugins(self):
        """Dynamically load all plugins from the src.plugins package."""
        # Load configuration and initialize plugin lists
        config, disabled_plugins = self._load_plugin_configuration()
        if config is None:
            return

        plugin_dir = os.path.join(os.path.dirname(__file__), "../plugins")
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
                    module_path = (
                        os.path.relpath(os.path.join(root, file_name), plugin_dir)
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
            plugin_dir = os.path.join(os.path.dirname(__file__), "../plugins")
            relative_path = os.path.relpath(file_path, plugin_dir).replace("/", ".")[
                :-3
            ]  # Remove .py extension
            module_path = f"waypanel.src.plugins.{relative_path}"

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
            self.logger.error_handler.handle(
                error=e,
                message=f"Failed to reload plugin '{plugin_name}': {e}",
                level="error",
            )
        except Exception as e:
            self.logger.error_handler.handle(
                error=e,
                message=f"Error reloading plugin '{plugin_name}': {e}",
                level="error",
            )

    def _load_plugin_configuration(self):
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
            self.logger.error_handler.handle(
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
            module_full_path = f"waypanel.src.plugins.{module_path}"
            module = importlib.import_module(module_full_path)

            is_plugin_enabled = getattr(module, "ENABLE_PLUGIN", True)
            # Check if the plugin has required functions
            if not hasattr(module, "get_plugin_placement") or not hasattr(
                module, "initialize_plugin"
            ):
                self.logger.error_handler(
                    f"Module {module_name} is missing required functions. Skipping."
                )
                return

            # Check if the plugin is enabled via ENABLE_PLUGIN
            if not is_plugin_enabled:
                self.logger.info(f"Skipping disabled plugin: {module_name}")
                return

            # Validate DEPS list
            has_plugin_deps = getattr(module, "DEPS", [])
            if not self.validate_deps_list(has_plugin_deps, module_name):
                self.logger.error_handler.handle(
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
            if position_result:
                if self.utils.validate_tuple(position_result, name="position_result"):
                    if len(position_result) == 3:
                        position, order, priority = position_result
                    else:
                        position, order = position_result
                        priority = 0
                else:
                    self.logger.error_handler.handle(
                        f"Invalid position result for plugin {module_name}. Skipping."
                    )
                    return

            # Add to valid plugins and metadata
            valid_plugins.append(module_name)
            plugin_metadata.append((module, position, order, priority))
        except Exception as e:
            self.logger.error_handler.handle(
                error=e,
                message=f"Failed to initialize plugin: {module_name}: {e} ",
                level="error",
                user_notification=lambda msg: print(f"USER NOTIFICATION: {msg}"),
            )

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
            target (Gtk.Container): The target container (e.g., left_box, right_box).
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
                        self.plugin_containers[f"{module_name}_box"].set_row_spacing(
                            0
                        )  # Minimal row spacing
                        self.plugin_containers[f"{module_name}_box"].set_column_spacing(
                            0
                        )  # Minimal column spacing
                        self.plugin_containers[f"{module_name}_box"].set_margin_top(
                            0
                        )  # No top margin
                        self.plugin_containers[f"{module_name}_box"].set_margin_bottom(
                            0
                        )  # No bottom margin
                        self.plugin_containers[f"{module_name}_box"].set_margin_start(
                            0
                        )  # No start margin
                        self.plugin_containers[f"{module_name}_box"].set_margin_end(
                            0
                        )  # No end margin
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
                    self.plugin_containers[f"{module_name}_box"].set_row_spacing(
                        0
                    )  # Minimal row spacing
                    self.plugin_containers[f"{module_name}_box"].set_column_spacing(
                        0
                    )  # Minimal column spacing
                    self.plugin_containers[f"{module_name}_box"].set_margin_top(
                        0
                    )  # No top margin
                    self.plugin_containers[f"{module_name}_box"].set_margin_bottom(
                        0
                    )  # No bottom margin
                    self.plugin_containers[f"{module_name}_box"].set_margin_start(
                        0
                    )  # No start margin
                    self.plugin_containers[f"{module_name}_box"].set_margin_end(
                        0
                    )  # No end margin
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
        """Initialize plugins in the correct order based on priority and position."""
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

                # Check if the plugin has an append_widget method
                if not hasattr(plugin_instance, "set_widget"):
                    return

                widget_to_append = plugin_instance.set_widget()[0]
                widget_action = plugin_instance.set_widget()[1]

                self.handle_set_widget(
                    widget_action, widget_to_append, target_box, module_name
                )

            except Exception as e:
                self.logger.error(f"Failed to initialize plugin {plugin_name}: {e}")

        # Process all plugins
        for module, position, order, priority in plugin_metadata:
            initialize_plugin_with_deps(module, position, order, priority)

    def _get_target_panel_box(self, position, plugin_name=None):
        """Determine the target panel box based on the plugin's position."""
        if position == "left":
            return self.panel_instance.top_panel_box_left
        elif position == "right":
            return self.panel_instance.top_panel_box_right
        elif position == "center":
            return self.panel_instance.top_panel_box_center
        elif position == "systray":
            return self.panel_instance.top_panel_box_systray
        elif position == "after-systray":
            return self.panel_instance.top_panel_box_for_buttons
        elif position == "left-panel":
            return self.panel_instance.left_panel
        elif position == "right-panel":
            return self.panel_instance.right_panel
        elif position == "bottom-panel":
            return self.panel_instance.bottom_panel
        elif position == "top-panel":
            return self.panel_instance.top_panel
        elif position == "background":
            return "background"
        else:
            self.logger.error_handler.handle(
                f"[{plugin_name}] has an invalid position in get_plugin_placement() '{position}'."
            )
            return None
