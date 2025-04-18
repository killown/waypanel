import os
import importlib
import time
import toml
from gi.repository import GLib


class PluginLoader:
    def __init__(self, panel_instance, logger, config_path):
        """
        Initialize the PluginLoader.

        Args:
            panel_instance: The main panel object from panel.py.
            logger: Logger instance for logging messages.
            config_path: Path to the configuration directory.
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
            self.logger.error(f"Failed to load configuration file: {e}")
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
                self.logger.error(
                    f"Module {module_name} is missing required functions. Skipping."
                )
                return

            # Check if the plugin is enabled via ENABLE_PLUGIN
            if not is_plugin_enabled:
                self.logger.info(f"Skipping disabled plugin: {module_name}")
                return

            # Get position, order, and optional priority
            position_result = module.get_plugin_placement(self.panel_instance)

            if isinstance(position_result, tuple):
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
            self.logger.error(
                f"Failed to initialize plugin {module_name}: {e} ",
                exc_info=True,
            )

    def _update_plugin_configuration(self, config, valid_plugins, disabled_plugins):
        """Update the [plugins] section in the TOML configuration."""
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
        config["plugins"]["list"] = " ".join(valid_plugins)
        config["plugins"]["disabled"] = " ".join(disabled_plugins)

        with open(waypanel_config_path, "w") as f:
            toml.dump(config, f)

    def _initialize_sorted_plugins(self, plugin_metadata):
        """Sort plugins by their priority and order, then initialize them."""
        # Sort by priority (descending), then by order (ascending)
        plugin_metadata.sort(key=lambda x: (-x[3], x[2]))

        for module, position, order, priority in plugin_metadata:
            start_time = time.time()  # Start timing
            try:
                target_box = self._get_target_panel_box(position)
                if target_box is None:
                    continue

                # Initialize the plugin
                module_name = module.__name__.split(".")[-1]
                plugin_instance = module.initialize_plugin(self.panel_instance)
                self.plugins[module_name] = plugin_instance

                # Check if plugin has append_widget method and use it
                if hasattr(plugin_instance, "append_widget"):
                    # change this later from append_widget to append_to_instance or better name
                    widget_to_append = plugin_instance.append_widget()
                    # widget_to_append could be a list of widgets to append or a single widget
                    if widget_to_append:
                        if isinstance(widget_to_append, list):
                            for widget in widget_to_append:
                                GLib.idle_add(target_box.append, widget)
                        else:
                            GLib.idle_add(target_box.append, widget_to_append)

                if hasattr(plugin_instance, "panel_set_content"):
                    panel_to_set_content = plugin_instance.panel_set_content()
                    if panel_to_set_content:
                        if isinstance(panel_to_set_content, list):
                            for widget in panel_to_set_content:
                                GLib.idle_add(target_box.append, widget)
                        else:
                            GLib.idle_add(target_box.set_content, panel_to_set_content)

                elapsed_time = time.time() - start_time
                plugin_name = module.__name__.split(".src.plugins.")[-1]
                self.logger.info(
                    f"Plugin [{plugin_name}] initialized in {elapsed_time:.4f} seconds "
                    f"(Position: {position}, Order: {order}, Priority: {priority})"
                )
            except Exception as e:
                elapsed_time = time.time() - start_time
                self.logger.error(
                    f"Failed to initialize plugin {module.__name__}: {e} "
                    f"(processed in {elapsed_time:.4f} seconds)",
                    exc_info=True,
                )

    def _get_target_panel_box(self, position):
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
        else:
            self.logger.error(f"Invalid position '{position}'. Skipping.")
            return None
