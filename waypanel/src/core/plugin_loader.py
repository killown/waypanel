import os
import importlib
import time
import toml
from gi.repository import GLib


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
        self.plugins = {}

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
                    module_name = file_name[:-2]  # Remove the .py extension
                    module_path = (
                        os.path.relpath(os.path.join(root, file_name), plugin_dir)
                        .replace("/", ".")
                        .replace(".py", "")
                    )
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

    def _load_plugin_configuration(self):
        """Load the TOML configuration file and parse the disabled plugins list."""
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
            self.logger.error_handler.handle(
                error=e,
                message="Failed to load configuration file: {e}",
                level="error",
                user_notification=lambda msg: print(f"USER NOTIFICATION: {msg}"),
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
                if isinstance(position_result, tuple):
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
        if not isinstance(deps_list, list):
            self.logger.error_handler.handle(
                error=TypeError(
                    f"Invalid DEPS type: {type(deps_list).__name__}. Expected a list."
                ),
                message=f"Plugin '{module_name}' has an invalid DEPS list. DEPS must be a list.",
                level="error",
            )
            return False

        for index, dep in enumerate(deps_list):
            if not isinstance(dep, str):
                self.logger.error_handler.handle(
                    error=TypeError(
                        f"Invalid dependency type at index {index}: {type(dep).__name__}. Expected a string."
                    ),
                    message=f"Plugin '{module_name}' has an invalid dependency at index {index} in DEPS. Dependencies must be strings.",
                    level="error",
                )
                return False
            if not dep.strip():
                self.logger.error_handler.handle(
                    error=ValueError(
                        f"Empty dependency found at index {index} in DEPS."
                    ),
                    message=f"Plugin '{module_name}' has an empty dependency at index {index} in DEPS. Dependencies must be non-empty strings.",
                    level="error",
                )
                return False

        return True

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
                if hasattr(plugin_instance, "append_widget"):
                    widget_to_append = plugin_instance.append_widget()
                    if widget_to_append is None:
                        self.logger.error(
                            f"append_widget returned None for plugin {plugin_name}."
                        )
                        return

                    # Append the widget(s) to the target box
                    if isinstance(widget_to_append, list):
                        for widget in widget_to_append:
                            GLib.idle_add(target_box.append, widget)
                    else:
                        GLib.idle_add(target_box.append, widget_to_append)
                elif hasattr(plugin_instance, "panel_set_content"):
                    # Handle plugins that use panel_set_content instead of append_widget
                    panel_content = plugin_instance.panel_set_content()
                    if panel_content is None:
                        self.logger.error(
                            f"panel_set_content returned None for plugin {plugin_name}."
                        )
                        return

                    if isinstance(panel_content, list):
                        for widget in panel_content:
                            GLib.idle_add(target_box.set_content, widget)
                    else:
                        GLib.idle_add(target_box.set_content, panel_content)
                else:
                    # Log background plugins without warnings
                    self.logger.info(
                        f"Plugin [{plugin_name}] initialized without UI interaction."
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
