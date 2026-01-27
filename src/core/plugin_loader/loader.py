import os
import importlib
import importlib.util
from gi.repository import GLib, Gtk  # pyright: ignore
import sys
from src.core.plugin_loader.helper import PluginLoaderHelpers, PluginResolver
from typing import Any, Dict, Tuple, Set

PluginMetadataTuple = Tuple[Any, str, int, int, str]


class PluginLoader:
    """
    Manages the entire lifecycle of plugins for Waypanel, ensuring non-blocking,
    dependency-aware startup and correct placement on the GTK panel.
    """

    def __init__(self, panel_instance):
        self.panel_instance = panel_instance
        self.logger = self.panel_instance.logger
        self._plugins_instance_map = {}
        self.plugins = self._plugins_instance_map
        self.plugin_id_to_short_name: Dict[str, str] = {}
        self.short_name_to_id: Dict[str, str] = {}
        self.module_name_to_id: Dict[str, str] = {}

        # Fast-lookup metadata cache to eliminate redundant function calls
        self._meta_cache: Dict[str, dict] = {}

        self.plugins_path = {}
        self.plugins_import = {}
        self.plugin_containers = {}
        self.plugins_dir = self.plugins_base_path()
        self.plugin_loader_helper = PluginLoaderHelpers(panel_instance, self)

        # Helper Method Mapping
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
        self._resolve_dynamic_deps = self.plugin_loader_helper._resolve_dynamic_deps

        self.overflow_container = self.plugin_loader_helper.overflow_container
        self.position_mapping = {}
        self.valid_plugins = []
        self.plugin_metadata = []
        self.plugin_metadata_map = {}
        self.plugins_to_process = []
        self.plugins_to_process_index = 0
        self.plugins_to_initialize = []
        self.plugins_to_initialize_index = 0
        self.data_helper = self.panel_instance.data_helper
        self.config_handler = self.panel_instance.config_handler
        self.config_path = self.config_handler.config_path
        self.gtk_helpers = self.panel_instance.gtk_helpers
        self.update_widget_safely = self.gtk_helpers.update_widget_safely
        self.panel_instance.plugins_startup_finished = False

        self.user_plugins_dir = os.path.join(
            self.plugin_loader_helper.get_real_user_home(),
            ".local",
            "share",
            "waypanel",
            "plugins",
        )

        # PERFORMANCE: Use a Set for O(1) lookup speed
        disabled = self.config_handler.get_root_setting(["plugins", "disabled"]) or []
        self.disabled_plugins: Set[str] = set(disabled)
        self.plugin_icons = {}

    def _find_plugins_in_dir(self, directory_path):
        """Recursively searches a directory for Python plugin modules with optimized skipping."""
        if directory_path not in sys.path:
            sys.path.append(directory_path)

        for root, dirs, files in os.walk(directory_path):
            if ".ignore_plugins" in files:
                self.logger.info(f"Ignoring plugins in: {root}")
                dirs[:] = []
                continue

            # PERFORMANCE: Fast in-place filtering of directories
            dirs[:] = [
                d
                for d in dirs
                if d not in ("examples", ".git", "__pycache__")
                and not d.startswith(".")
            ]

            for file_name in files:
                if file_name.endswith(".py") and not file_name.startswith(("_", ".")):
                    module_name = file_name[:-3]
                    # Faster relpath logic for module strings
                    rel = os.path.relpath(root, directory_path)
                    module_path = (
                        module_name
                        if rel == "."
                        else f"{rel.replace(os.sep, '.')}.{module_name}"
                    )

                    self.plugins_path[module_name] = os.path.join(root, file_name)
                    if module_name not in self.plugins_to_process:
                        self.plugins_to_process.append((module_name, module_path))

    def _scan_all_plugin_dirs(self):
        """Executes the plugin scans sequentially in the GTK thread."""
        try:
            self._find_plugins_in_dir(self.plugins_dir)
            if os.path.exists(self.user_plugins_dir):
                self._find_plugins_in_dir(self.user_plugins_dir)
        except Exception as e:
            self.logger.error(f"Error during plugin scanning: {e}")

        if self.plugins_to_process:
            GLib.idle_add(self._batch_import_and_validate)
        return False

    def load_plugins(self):
        """Loads and prepares all plugins from built-in and custom directories."""
        GLib.idle_add(self._scan_all_plugin_dirs)

    def plugins_base_path(self):
        """Determines the base path where plugins are located with cached resolution."""
        try:
            spec = importlib.util.find_spec("waypanel")
            if spec and spec.origin:
                origin = spec.origin
                # Optimization: rsplit is faster than multiple dirname calls
                base = origin.rsplit("waypanel", 1)[0]
                plugin_path = os.path.join(base, "waypanel", "plugins")
                if os.path.exists(plugin_path):
                    return plugin_path
        except (ImportError, AttributeError):
            pass

        fallbacks = [
            os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "plugins")
            ),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugins")),
        ]
        return next((p for p in fallbacks if os.path.exists(p)), "")

    def _batch_import_and_validate(self):
        """SYNCHRONOUSLY imports and validates a chunk of discovered plugins."""
        CHUNK_SIZE = 8  # Balanced for modern CPUs to reduce GLib loop overhead
        start = self.plugins_to_process_index
        end = min(start + CHUNK_SIZE, len(self.plugins_to_process))
        chunk = self.plugins_to_process[start:end]

        try:
            if not chunk and start >= len(self.plugins_to_process):
                self.plugins = PluginResolver(
                    self._plugins_instance_map,
                    id_map=self.short_name_to_id,
                    full_id_map=self.module_name_to_id,
                )
                GLib.idle_add(self._initialize_sorted_plugins)
                GLib.idle_add(self._update_plugin_configuration, self.valid_plugins)
                return False

            for module_name, module_path in chunk:
                # PERFORMANCE: Set lookup is O(1)
                if module_name in self.disabled_plugins:
                    continue
                try:
                    module = importlib.import_module(module_path)

                    get_meta = getattr(module, "get_plugin_metadata", None)
                    get_class = hasattr(module, "get_plugin_class")

                    if not get_meta or not get_class:
                        if module_path in sys.modules:
                            del sys.modules[module_path]
                        continue

                    metadata = get_meta(self.panel_instance)
                    metadata["deps"] = self._resolve_dynamic_deps(metadata)
                    print(metadata)
                    if not isinstance(metadata, dict) or not metadata.get(
                        "enabled", True
                    ):
                        if module_path in sys.modules:
                            del sys.modules[module_path]
                        continue

                    p_id = metadata["id"]

                    # PERFORMANCE: Pre-populate maps during import to avoid later processing
                    s_name = p_id.rsplit(".", 1)[-1]
                    self.plugin_id_to_short_name[p_id] = s_name
                    self.short_name_to_id[s_name] = p_id
                    self.module_name_to_id[module_name] = p_id

                    # Populate meta cache for the Sorter
                    self._meta_cache[p_id] = metadata
                    self.plugin_metadata_map[p_id] = metadata
                    self.plugins_import[p_id] = module_path
                    self.valid_plugins.append(p_id)

                    self.plugin_metadata.append(
                        (
                            module,
                            metadata.get("container", "background"),
                            metadata.get("priority", 0),
                            metadata.get("index", 0),
                            p_id,
                        )
                    )
                except Exception as e:
                    self.logger.error(f"Failed to load plugin {module_name}: {e}")
                    if module_path in sys.modules:
                        del sys.modules[module_path]

            self.plugins_to_process_index = end
            return True
        except Exception as e:
            self.logger.critical(f"FATAL: Unhandled exception during batch import: {e}")
            return False

    def handle_set_widget(self, action, widgets, target, plugin_id, hide=False):
        """Handles the placement of a plugin's widget on the panel with optimized lookups."""
        if not widgets:
            return
        widgets = widgets if isinstance(widgets, (list, tuple)) else [widgets]

        # Optimization: cache the icon setting lookup
        icon = self.config_handler.get_root_setting([plugin_id, "main_icon"])
        if icon and widgets[0]:
            self.gtk_helpers.set_plugin_main_icon(widgets[0], plugin_id, icon)

        if hide or self.config_handler.get_root_setting([plugin_id, "hide_in_systray"]):
            if self.overflow_container:
                if len(widgets) > 1:
                    box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
                    box.set_name(f"{plugin_id}_overflow_box")
                    for w in widgets:
                        self.update_widget_safely(box.append, w)
                    self.update_widget_safely(
                        self.overflow_container.add_hidden_widget, box
                    )
                else:
                    self.update_widget_safely(
                        self.overflow_container.add_hidden_widget, widgets[0]
                    )
                return

        if action == "append":
            box_name = f"{plugin_id}_box"
            flow = self.plugin_containers.get(box_name)
            if not flow:
                flow = Gtk.FlowBox(
                    valign=Gtk.Align.START,
                    halign=Gtk.Align.FILL,
                    selection_mode=Gtk.SelectionMode.NONE,
                )
                flow.add_css_class("box-widgets")
                self.plugin_containers[box_name] = flow
                self.update_widget_safely(target.append, flow)

            self.update_widget_safely(flow.remove_all)
            for w in widgets:
                if hasattr(w, "get_icon_name"):
                    self.plugin_icons[plugin_id] = w.get_icon_name()
                self.update_widget_safely(flow.append, w)
        elif action == "set_child":
            for w in widgets:
                self.update_widget_safely(target.set_child, w)

    def _initialize_sorted_plugins(self):
        """Topological Sort using pre-cached metadata (Zero function call overhead)."""
        if not self.plugin_metadata:
            return False

        all_plugins = {m[4]: m for m in self.plugin_metadata}
        in_degree = {n: 0 for n in all_plugins}
        adj = {n: [] for n in all_plugins}

        # Optimized resolution lookup
        def fast_resolve(d):
            return (
                self.short_name_to_id.get(d)
                or self.module_name_to_id.get(d)
                or (d if d in all_plugins else None)
            )

        for name in all_plugins:
            # PERFORMANCE: Direct dictionary access instead of module function call
            deps = self._meta_cache.get(name, {}).get("deps", [])
            for d in deps:
                d_id = fast_resolve(d)
                if d_id:
                    adj[d_id].append(name)
                    in_degree[name] += 1

        ready = [
            (n, all_plugins[n][2], all_plugins[n][3])
            for n, deg in in_degree.items()
            if deg == 0
        ]
        ready.sort(key=lambda x: (-x[1], x[2]))

        sorted_names = []
        while ready:
            curr, _, _ = ready.pop(0)
            sorted_names.append(curr)
            for d in adj.get(curr, []):
                in_degree[d] -= 1
                if in_degree[d] == 0:
                    meta = all_plugins[d]
                    ready.append((d, meta[2], meta[3]))
                    ready.sort(key=lambda x: (-x[1], x[2]))

        self.plugins_to_initialize = [all_plugins[n] for n in sorted_names]
        self.plugins_to_initialize_index = 0
        GLib.idle_add(self._chunked_initialize_plugins)
        return False

    def _chunked_initialize_plugins(self):
        if self.plugins_to_initialize_index >= len(self.plugins_to_initialize):
            GLib.timeout_add(
                300,
                lambda: setattr(self.panel_instance, "plugins_startup_finished", True),
            )
            return False

        m, c, p, o, pid = self.plugins_to_initialize[self.plugins_to_initialize_index]
        self._initialize_single_plugin(m, c, o, p, pid)
        self.plugins_to_initialize_index += 1
        return True

    def _initialize_single_plugin(self, module, container, order, priority, plugin_id):
        """Initializes instance and manages lifecycle with pre-resolved metadata."""
        # Performance: Use cache instead of dict.get() repeatedly
        meta = self._meta_cache.get(plugin_id, {})
        try:
            instance = module.get_plugin_class()(self.panel_instance)

            # Sequence hooks via fast getattr checks
            getattr(instance, "on_start", lambda: None)()
            getattr(instance, "on_enable", lambda: None)()

            self.plugins[plugin_id] = instance
            target = self._get_target_panel_box(container, plugin_id)

            if target and container != "background" and hasattr(instance, "set_widget"):
                widgets, action = instance.set_widget()
                self.handle_set_widget(
                    action, widgets, target, plugin_id, meta.get("hidden", False)
                )
        except Exception as e:
            self.logger.error(f"Failed init {plugin_id}: {e}")
        return False

    def _update_plugin_configuration(self, valid_plugins):
        self.config_handler.update_config(["plugins", "enabled"], valid_plugins)
        self.config_handler.update_config(
            ["plugins", "disabled"], list(self.disabled_plugins)
        )
        return False

    def validate_deps_list(self, d):
        return isinstance(d, list) and all(isinstance(i, str) for i in d)
