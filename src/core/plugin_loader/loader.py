import os
import importlib
from gi.repository import GLib, Gtk  # pyright: ignore
import sys
import traceback
from src.shared.data_helpers import DataHelpers
from src.shared.config_handler import ConfigHandler
from src.shared.gtk_helpers import GtkHelpers
from src.core.plugin_loader.helper import PluginLoaderHelpers


class PluginLoader:
    """
    Manages the entire lifecycle of plugins for Waypanel, ensuring non-blocking,
    dependency-aware startup and correct placement on the GTK panel.
    The process is executed in non-blocking stages using GLib.idle_add to maintain
    UI responsiveness during the potentially slow tasks of I/O and module importing.
    The plugin loading sequence is structured into three main phases:
    1.  Discovery and Validation:
        - Scans built-in (`self.plugins_dir`) and user-defined directories (`self.user_plugins_dir`)
          for Python modules (`_scan_all_plugin_dirs`).
        - Uses `_batch_import_and_validate` to dynamically import plugin modules in small,
          yielded batches (chunks of 10).
        - Validates that each module defines the necessary entry points: `get_plugin_placement`
          and `initialize_plugin`.
        - Checks and collects essential metadata, including dependencies (`DEPS`) and
          UI placement (position, order, priority).
    2.  Dependency Sorting and Ordering:
        - Uses `_initialize_sorted_plugins` to build a dependency graph based on the `DEPS` attribute.
        - Applies **Topological Sort (Kahn's Algorithm)** to determine a safe, sequential
          loading order where all dependencies are initialized before their dependents.
        - Plugins are ordered by `priority` (highest first) and `order` (lowest first)
          as tie-breakers for UI layout.
        - Detects and logs fatal **circular dependencies**, skipping initialization for the affected plugins.
    3.  Initialization and Placement:
        - Uses `_chunked_initialize_plugins` to initialize the sorted plugins one-by-one,
          guaranteed to be in the correct dependency order.
        - Calls `module.initialize_plugin(self.panel_instance)` to instantiate the plugin.
        - The `handle_set_widget` method manages the final UI presentation:
            - It retrieves the plugin's GTK widget.
            - It places the widget in the correct panel box (Left, Center, or Right) as
              determined by `get_plugin_placement`.
            - It handles routing the widget to the overflow container if `hide_in_systray` is set.
        - Updates the persistent configuration file (`config.toml`) with the final list of
          enabled and disabled plugins.
    """

    def __init__(self, panel_instance):
        self.panel_instance = panel_instance
        self.logger = self.panel_instance.logger
        self.plugins = {}
        self.plugins_path = {}
        self.plugins_import = {}
        self.plugin_containers = {}
        self.plugins_dir = self.plugins_base_path()
        self.plugin_loader_helper = PluginLoaderHelpers(panel_instance, self)
        self._get_target_panel_box = self.plugin_loader_helper._get_target_panel_box
        self.enable_plugin = self.plugin_loader_helper.enable_plugin
        self.disable_plugin = self.plugin_loader_helper.disable_plugin
        self.reload_plugin = self.plugin_loader_helper.reload_plugin
        self.ensure_proportional_layout = (
            self.plugin_loader_helper.ensure_proportional_layout
        )
        self.register_overflow_container = (
            self.plugin_loader_helper.register_overflow_container
        )
        self.overflow_container = self.plugin_loader_helper.overflow_container
        self.position_mapping = {}
        self.valid_plugins = []
        self.plugin_metadata = []
        self.plugins_to_process = []
        self.plugins_to_process_index = 0
        self.plugins_to_initialize = []
        self.plugins_to_initialize_index = 0
        self.data_helper = DataHelpers()
        self.config_handler = ConfigHandler(panel_instance)
        self.config_path = self.config_handler.config_path
        self.gtk_helpers = GtkHelpers(panel_instance)
        self.update_widget_safely = self.gtk_helpers.update_widget_safely
        self.panel_instance.plugins_startup_finished = False
        self.user_plugins_dir = os.path.join(
            self.plugin_loader_helper.get_real_user_home(),
            ".local",
            "share",
            "waypanel",
            "plugins",
        )
        self.disabled_plugins = self.config_handler.check_and_get_config(
            ["plugins", "disabled"]
        )
        self.plugin_icons = {}
        self.last_widget_plugin_added = None
        self.ensure_proportional_layout_attempts = {"max": 30, "current": 0}
        GLib.timeout_add(100, self.ensure_proportional_layout)

    def _find_plugins_in_dir(self, directory_path):
        """
        Recursively searches a directory for Python plugin modules and collects
        their paths into self.plugins_to_process for later batch processing.
        """
        sys.path.append(directory_path)
        for root, dirs, files in os.walk(directory_path):
            if "examples" in dirs:
                dirs.remove("examples")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
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
                    if module_name not in self.plugins_to_process:
                        self.plugins_to_process.append((module_name, module_path))
            self.data_helper.get_current_time_with_ms(
                f"Plugin loader: searching for plugins in the specified location {root}"
            )

    def _scan_all_plugin_dirs(self):
        """
        Executes the two plugin scans sequentially in the GTK thread.
        """
        try:
            self.logger.info("Starting plugin scan.")
            self._find_plugins_in_dir(self.plugins_dir)
            self._find_plugins_in_dir(self.user_plugins_dir)
        except Exception as e:
            self.logger.error(f"Error during plugin scanning: {e}")
        num_plugins = len(self.plugins_to_process)
        self.logger.info(
            f"Plugin discovery complete. Found {num_plugins} plugins to import. Starting chunked import."
        )
        if num_plugins > 0:
            GLib.idle_add(self._batch_import_and_validate)
        return False

    def load_plugins(self):
        """
        Loads and prepares all plugins from built-in and custom directories.
        """
        GLib.idle_add(self._scan_all_plugin_dirs)

    def plugins_base_path(self):
        """
        Determines the base path where plugins are located.
        """
        try:
            waypanel_module_spec = importlib.util.find_spec("waypanel")  # pyright: ignore
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

    def _batch_import_and_validate(self):
        """
        SYNCHRONOUSLY imports and validates a chunk of discovered plugins.
        This runs as a GLib idle callback. Returning True reschedules it,
        which yields control and maintains responsiveness.
        """
        CHUNK_SIZE = 5
        start_index = self.plugins_to_process_index
        end_index = min(start_index + CHUNK_SIZE, len(self.plugins_to_process))
        plugins_chunk = self.plugins_to_process[start_index:end_index]
        if not plugins_chunk:
            self.logger.info(
                f"Plugin loader: Batch import and validation complete for all {len(self.plugins_to_process)} plugins."
            )
            GLib.idle_add(self._initialize_sorted_plugins)
            GLib.idle_add(self._update_plugin_configuration, self.valid_plugins)
            self.plugins_to_process = []
            self.plugins_to_process_index = 0
            return False
        plugins_imported_in_chunk = 0
        for module_name, module_path in plugins_chunk:
            if module_name.startswith("_") or module_name in self.disabled_plugins:
                continue
            try:
                module = importlib.import_module(module_path)
                plugins_imported_in_chunk += 1
                is_plugin_enabled = getattr(module, "ENABLE_PLUGIN", True)
                if not hasattr(module, "get_plugin_placement") or not hasattr(
                    module, "initialize_plugin"
                ):
                    self.logger.error(
                        f"Module {module_name} is missing required functions. Skipping."
                    )
                    continue
                if not is_plugin_enabled:
                    self.data_helper.get_current_time_with_ms(
                        f"Skipping disabled plugin: {module_name}"
                    )
                    continue
                self.plugins_import[module_name] = module_path
                self.logger.debug(f"Registered plugin: {module_name} -> {module_path}")
                has_plugin_deps = getattr(module, "DEPS", [])
                if not self.validate_deps_list(has_plugin_deps):
                    self.logger.error(
                        error=ValueError("Invalid DEPS list."),
                        message=f"Plugin '{module_name}' has an invalid DEPS list. Skipping.",
                        level="error",
                    )
                    continue
                position_result = module.get_plugin_placement(self.panel_instance)  # pyright: ignore
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
                            continue
                self.valid_plugins.append(module_name)
                self.plugin_metadata.append((module, position, order, priority))
            except Exception as e:
                self.logger.error(f"Failed to load or validate plugin {module_name}:")
                print(f" {e}:\n{traceback.format_exc()}")
        self.plugins_to_process_index = end_index
        remaining_plugins = len(self.plugins_to_process) - self.plugins_to_process_index
        if remaining_plugins > 0:
            self.data_helper.get_current_time_with_ms(
                f"Plugin loader: Chunk import complete. {plugins_imported_in_chunk} plugins imported. {remaining_plugins} remaining. Rescheduling..."
            )
            return True
        else:
            self.logger.info(
                f"Plugin loader: Batch import and validation complete for all {len(self.plugins_to_process)} plugins."
            )
            GLib.idle_add(self._initialize_sorted_plugins)
            GLib.idle_add(self._update_plugin_configuration, self.valid_plugins)
            return False

    def _update_plugin_configuration(self, valid_plugins):
        """
        Persists the plugin configuration to the `config.toml` file.
        """
        self.config_handler.update_config(["plugins", "enabled"], valid_plugins)
        self.config_handler.update_config(
            ["plugins", "disabled"], self.disabled_plugins
        )
        return False

    def validate_deps_list(self, deps_list):
        """
        Validates the DEPS list to ensure it contains only valid plugin names.
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

    def handle_set_widget(
        self,
        widget_action,
        widget_to_append,
        target,
        module_name,
        hide_in_systray=False,
    ):
        """
        Handles the placement of a plugin's widget on the panel.
        """
        icon_name = self.config_handler.check_and_get_config(
            ["plugins", module_name, "main_icon"]
        )
        if icon_name:
            self.gtk_helpers.set_plugin_main_icon(
                widget_to_append, module_name, icon_name
            )
        if not hide_in_systray:
            hide_in_systray = self.config_handler.check_and_get_config(
                ["plugins", module_name, "hide_in_systray"]
            )
        if hide_in_systray:
            if not hasattr(self, "overflow_container") or not self.overflow_container:
                self.logger.warning(
                    f"Plugin {module_name} is set to hide but overflow container is not registered. Placing normally."
                )
            else:
                widgets = (
                    widget_to_append
                    if isinstance(widget_to_append, list)
                    else [widget_to_append]
                )
                if len(widgets) > 1:
                    container_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
                    container_box.set_name(f"{module_name}_overflow_box")
                    for widget in widgets:
                        self.update_widget_safely(container_box.append, widget)
                    self.update_widget_safely(
                        self.overflow_container.add_hidden_widget, container_box
                    )
                elif len(widgets) == 1:
                    self.update_widget_safely(
                        self.overflow_container.add_hidden_widget, widgets[0]
                    )
                return
        if widget_action == "append":
            widgets = (
                widget_to_append
                if isinstance(widget_to_append, list)
                else [widget_to_append]
            )
            box_name = f"{module_name}_box"
            if box_name not in self.plugin_containers:
                flow_box = Gtk.FlowBox()
                flow_box.set_valign(Gtk.Align.START)
                flow_box.set_halign(Gtk.Align.FILL)
                flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
                flow_box.add_css_class("box-widgets")
                self.plugin_containers[box_name] = flow_box
                self.update_widget_safely(target.append, flow_box)
            else:
                flow_box = self.plugin_containers[box_name]
            self.update_widget_safely(flow_box.remove_all)
            for widget in widgets:
                if hasattr(widget, "get_icon_name"):
                    self.plugin_icons[module_name] = widget.get_icon_name()
                self.update_widget_safely(flow_box.append, widget)
        elif widget_action == "set_content":
            widgets = (
                widget_to_append
                if isinstance(widget_to_append, list)
                else [widget_to_append]
            )
            for widget in widgets:
                self.update_widget_safely(target.set_content, widget)

    def _initialize_sorted_plugins(self):
        """
        Sorts the fully collected plugin metadata using Topological Sort (Kahn's
        Algorithm) to satisfy DEPS, resolving UI ordering ties with priority and order.
        Sets up the final list for non-blocking initialization.
        """
        if not self.plugin_metadata:
            self.logger.info("No plugin metadata found. Skipping initialization.")
            return False
        all_plugins = {}
        for metadata in self.plugin_metadata:
            module_name = metadata[0].__name__.split(".")[-1]
            all_plugins[module_name] = metadata
        in_degree = {name: 0 for name in all_plugins}
        adj_list = {name: [] for name in all_plugins}
        for name, metadata in all_plugins.items():
            module = metadata[0]
            deps = getattr(module, "DEPS", [])
            if not isinstance(deps, list):
                self.logger.error(
                    f"Plugin '{name}' DEPS is not a list. Skipping dependency check."
                )
                deps = []
            for dep in deps:
                if dep in all_plugins:
                    adj_list[dep].append(name)
                    in_degree[name] += 1
                else:
                    self.logger.warning(
                        f"Plugin '{name}' declares dependency '{dep}' which was not found among loaded plugins. "
                        "This plugin may fail to initialize at runtime."
                    )
        ready_to_load = []
        for name, degree in in_degree.items():
            if degree == 0:
                metadata = all_plugins[name]
                ready_to_load.append((name, metadata[3], metadata[2]))
        ready_to_load.sort(key=lambda x: (-x[1], x[2]))
        sorted_plugin_names = []
        while ready_to_load:
            current_plugin_name, _, _ = ready_to_load.pop(0)
            sorted_plugin_names.append(current_plugin_name)
            for dependent_plugin_name in adj_list.get(current_plugin_name, []):
                in_degree[dependent_plugin_name] -= 1
                if in_degree[dependent_plugin_name] == 0:
                    dependent_metadata = all_plugins[dependent_plugin_name]
                    dependent_priority = dependent_metadata[3]
                    dependent_order = dependent_metadata[2]
                    ready_to_load.append(
                        (dependent_plugin_name, dependent_priority, dependent_order)
                    )
                    ready_to_load.sort(key=lambda x: (-x[1], x[2]))
        if len(sorted_plugin_names) != len(all_plugins):
            cyclical_plugins = [
                name for name, degree in in_degree.items() if degree > 0
            ]
            self.logger.error(
                f"FATAL: Circular dependency detected among plugins: {', '.join(cyclical_plugins)}. "
                "These plugins will NOT be initialized. Check their DEPS lists."
            )
        final_plugins_to_init = [all_plugins[name] for name in sorted_plugin_names]
        self.plugins_to_initialize = final_plugins_to_init
        self.plugin_metadata = []
        self.plugins_to_initialize_index = 0
        self.logger.info(
            f"Scheduling chunked initialization for {len(self.plugins_to_initialize)} plugins, "
            "guaranteed to be in dependency order."
        )
        GLib.idle_add(self._chunked_initialize_plugins)
        return False

    def _chunked_initialize_plugins(self):
        """
        Initializes plugins one by one using GLib.idle_add.
        The order is guaranteed by the preceding Topological Sort.
        Returns True to reschedule immediately (for the next plugin), or False to stop.
        """
        CHUNK_SIZE = 1
        start_index = self.plugins_to_initialize_index
        end_index = min(CHUNK_SIZE + start_index, len(self.plugins_to_initialize))
        plugins_chunk = self.plugins_to_initialize[start_index:end_index]
        if not plugins_chunk:
            self.plugins_to_initialize = []
            self.plugins_to_initialize_index = 0
            self.logger.info("Plugin initialization complete.")
            return False
        for module, position, order, priority in plugins_chunk:
            self._initialize_single_plugin(module, position, order, priority)
        self.plugins_to_initialize_index = end_index
        remaining_plugins = (
            len(self.plugins_to_initialize) - self.plugins_to_initialize_index
        )
        if remaining_plugins > 0:
            self.logger.debug(
                f"Plugin initialization: {remaining_plugins} remaining. Rescheduling next chunk immediately."
            )
            return True
        else:
            self.plugins_to_initialize = []
            self.plugins_to_initialize_index = 0
            self.logger.info("Plugin initialization complete.")
            self.panel_instance.plugins_startup_finished = True
            return False

    def _initialize_single_plugin(self, module, position, order, priority):
        """
        Initializes a single plugin. Since plugins are loaded in dependency order
        (Topological Sort), the complex retry logic is no longer necessary.
        """
        module_name = module.__name__.split(".")[-1]
        plugin_name = module.__name__.split(".src.plugins.")[-1]
        hide_in_systray = getattr(module, "HIDE_IN_SYSTRAY", False)
        try:
            plugin_instance = module.initialize_plugin(self.panel_instance)
            if hasattr(plugin_instance, "on_start"):
                plugin_instance.on_start()
            self.logger.info(f"Initialized plugin: {plugin_name}")
            self.plugins[module_name] = plugin_instance
            target_box = self._get_target_panel_box(position, plugin_name)
            if target_box is None:
                self.logger.error(
                    f"No target box found for plugin {plugin_name} with position {position}. Assuming background."
                )
            if position == "background" or target_box is None:
                self.logger.info(
                    f"Plugin [{plugin_name}] initialized as a background plugin. ✅"
                )
                return False
            if not hasattr(plugin_instance, "set_widget"):
                return False
            widget_to_append = plugin_instance.set_widget()[0]
            widget_action = plugin_instance.set_widget()[1]
            self.handle_set_widget(
                widget_action,
                widget_to_append,
                target_box,
                module_name,
                hide_in_systray,
            )
            self.last_widget_plugin_added = module_name
        except Exception as e:
            self.logger.error(f"Failed to initialize plugin '{plugin_name}': {e} ❌")
            print(traceback.format_exc())
        self.data_helper.get_current_time_with_ms(
            f"Plugin loader: {plugin_name} successfully loaded ✅"
        )
        return False
