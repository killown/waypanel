import os
import importlib
import importlib.util
from gi.repository import GLib, Gtk  # pyright: ignore
import sys
import gc
from src.core.plugin_loader.helper import PluginLoaderHelpers, PluginResolver
from typing import Any, Dict, Tuple, Set

PluginMetadataTuple = Tuple[Any, str, int, int, str]


class PluginLoader:
    """
    Manages the discovery, loading, and lifecycle of Waypanel plugins.

    This loader implements a recursive directory scan that accommodates both standard
    Python packages and repository-style directories (e.g., those with hyphens).
    It prioritizes startup performance by batching imports and managing garbage
    collection during the loading phase.
    """

    def __init__(self, panel_instance):
        self.panel_instance = panel_instance
        self.logger = self.panel_instance.logger
        self._plugins_instance_map = {}
        self.plugins = self._plugins_instance_map

        self.plugin_id_to_short_name: Dict[str, str] = {}
        self.short_name_to_id: Dict[str, str] = {}
        self.module_name_to_id: Dict[str, str] = {}

        self._meta_cache: Dict[str, dict] = {}

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
        self._resolve_dynamic_deps = self.plugin_loader_helper._resolve_dynamic_deps
        self.overflow_container = self.plugin_loader_helper.overflow_container

        self.valid_plugins = []
        self.plugin_metadata = []
        self.plugin_metadata_map = {}
        self.plugins_to_process = []
        self.plugins_to_process_index = 0
        self.plugins_to_initialize = []
        self.plugins_to_initialize_index = 0

        self.data_helper = self.panel_instance.data_helper
        self.config_handler = self.panel_instance.config_handler
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

        disabled = self.config_handler.get_root_setting(["plugins", "disabled"]) or []
        self.disabled_plugins: Set[str] = set(disabled)
        self.plugin_icons = {}

        self._sys_path_cache: Set[str] = set(sys.path)

    def _smart_scan(self, current_dir, package_prefix=""):
        """
        Recursively scans the directory structure to identify plugin modules.

        This method handles standard Python packages as well as directories that do not
        conform to Python identifier rules (e.g., directories with hyphens). Non-compliant
        directories are treated as new import roots and added to sys.path to ensure
        relative imports within them function correctly.

        Args:
            current_dir (str): The directory path to scan.
            package_prefix (str): The accumulated dot-notation package path.
        """
        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    if (
                        entry.name.startswith((".", "_"))
                        and entry.name != "__init__.py"
                    ):
                        continue

                    if entry.is_file() and entry.name.endswith(".py"):
                        if entry.name == "__init__.py":
                            continue

                        module_name = entry.name[:-3]
                        full_module_path = (
                            f"{package_prefix}.{module_name}"
                            if package_prefix
                            else module_name
                        )

                        if module_name not in self.plugins_path:
                            self.plugins_path[module_name] = entry.path
                            self.plugins_to_process.append(
                                (module_name, full_module_path)
                            )

                    elif entry.is_dir() and entry.name not in (
                        "examples",
                        "__pycache__",
                        ".git",
                    ):
                        if not entry.name.isidentifier():
                            if entry.path not in self._sys_path_cache:
                                sys.path.append(entry.path)
                                self._sys_path_cache.add(entry.path)
                            self._smart_scan(entry.path, package_prefix="")
                        else:
                            new_prefix = (
                                f"{package_prefix}.{entry.name}"
                                if package_prefix
                                else entry.name
                            )
                            self._smart_scan(entry.path, new_prefix)

        except OSError as e:
            self.logger.warning(f"Scan error at {current_dir}: {e}")

    def _scan_all_plugin_dirs(self):
        """
        Initiates the scanning process for both system and user plugin directories.
        """
        try:
            if self.plugins_dir not in self._sys_path_cache:
                sys.path.append(self.plugins_dir)
                self._sys_path_cache.add(self.plugins_dir)
            self._smart_scan(self.plugins_dir, package_prefix="")

            if os.path.exists(self.user_plugins_dir):
                if self.user_plugins_dir not in self._sys_path_cache:
                    sys.path.append(self.user_plugins_dir)
                    self._sys_path_cache.add(self.user_plugins_dir)
                self._smart_scan(self.user_plugins_dir, package_prefix="")

        except Exception as e:
            self.logger.error(f"Error during plugin scanning: {e}")

        if self.plugins_to_process:
            GLib.idle_add(self._batch_import_and_validate)
        return False

    def load_plugins(self):
        """
        Schedules the plugin discovery and loading process on the main loop.
        """
        GLib.idle_add(self._scan_all_plugin_dirs)

    def plugins_base_path(self):
        """
        Resolves the absolute path to the core plugins directory.

        Returns:
            str: The resolved path to the 'waypanel/plugins' directory.
        """
        try:
            spec = importlib.util.find_spec("waypanel")
            if spec and spec.origin:
                origin = spec.origin
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
        """
        Imports and validates plugins in chunks to maintain UI responsiveness.

        Garbage collection is temporarily disabled during this process to reduce
        overhead while creating numerous module and class objects.
        """
        gc.disable()

        CHUNK_SIZE = 20
        start = self.plugins_to_process_index
        end = min(start + CHUNK_SIZE, len(self.plugins_to_process))
        chunk = self.plugins_to_process[start:end]

        try:
            if not chunk and start >= len(self.plugins_to_process):
                gc.enable()
                self.plugins = PluginResolver(
                    self._plugins_instance_map,
                    id_map=self.short_name_to_id,
                    full_id_map=self.module_name_to_id,
                )
                GLib.idle_add(self._initialize_sorted_plugins)
                GLib.idle_add(self._update_plugin_configuration, self.valid_plugins)
                return False

            for module_name, module_import_path in chunk:
                if module_name in self.disabled_plugins:
                    continue

                try:
                    module = importlib.import_module(module_import_path)

                    get_meta = getattr(module, "get_plugin_metadata", None)
                    if not get_meta or not hasattr(module, "get_plugin_class"):
                        if module_import_path in sys.modules:
                            del sys.modules[module_import_path]
                        continue

                    metadata = get_meta(self.panel_instance)

                    if "deps" not in metadata:
                        metadata["deps"] = []
                    elif metadata["deps"]:
                        metadata["deps"] = self._resolve_dynamic_deps(metadata)

                    if not metadata.get("enabled", True):
                        if module_import_path in sys.modules:
                            del sys.modules[module_import_path]
                        continue

                    p_id = metadata["id"]
                    s_name = p_id.split(".")[-1]

                    self.plugin_id_to_short_name[p_id] = s_name
                    self.short_name_to_id[s_name] = p_id
                    self.module_name_to_id[module_name] = p_id

                    self._meta_cache[p_id] = metadata
                    self.plugin_metadata_map[p_id] = metadata
                    self.plugins_import[p_id] = module_import_path
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

            self.plugins_to_process_index = end
            return True

        except Exception as e:
            gc.enable()
            self.logger.critical(f"FATAL: Unhandled exception during batch import: {e}")
            return False

    def handle_set_widget(self, action, widgets, target, plugin_id, hide=False):
        """
        Manages the placement of plugin widgets into the target panel container.

        Args:
            action (str): The placement action ('append' or 'set_child').
            widgets (list or Gtk.Widget): The widget(s) to add.
            target (Gtk.Widget): The container to add the widget to.
            plugin_id (str): The unique identifier of the plugin.
            hide (bool): Whether the widget should be initially hidden (e.g., in overflow).
        """
        if not widgets:
            return

        if not isinstance(widgets, (list, tuple)):
            widgets = [widgets]

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
        """
        Performs a topological sort on plugins based on dependencies and priority.
        """
        if not self.plugin_metadata:
            return False

        all_plugins = {m[4]: m for m in self.plugin_metadata}
        in_degree = {n: 0 for n in all_plugins}
        adj = {n: [] for n in all_plugins}

        short_map = self.short_name_to_id
        mod_map = self.module_name_to_id
        meta_cache = self._meta_cache

        for name in all_plugins:
            deps = meta_cache.get(name, {}).get("deps", [])
            for d in deps:
                d_id = (
                    short_map.get(d)
                    or mod_map.get(d)
                    or (d if d in all_plugins else None)
                )
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
        """
        Initializes plugin instances in small batches to prevent UI freezes.
        """
        CHUNK = 5
        for _ in range(CHUNK):
            if self.plugins_to_initialize_index >= len(self.plugins_to_initialize):
                GLib.idle_add(
                    lambda: setattr(
                        self.panel_instance, "plugins_startup_finished", True
                    )
                )
                return False

            m, c, p, o, pid = self.plugins_to_initialize[
                self.plugins_to_initialize_index
            ]
            self._initialize_single_plugin(m, c, o, p, pid)
            self.plugins_to_initialize_index += 1

        return True

    def _initialize_single_plugin(self, module, container, order, priority, plugin_id):
        """
        Instantiates a single plugin, executes lifecycle hooks, and places its widget.
        """
        meta = self._meta_cache.get(plugin_id, {})
        try:
            instance = module.get_plugin_class()(self.panel_instance)

            if hasattr(instance, "on_start"):
                instance.on_start()
            if hasattr(instance, "on_enable"):
                instance.on_enable()

            self.plugins[plugin_id] = instance
            target = self._get_target_panel_box(container, plugin_id)

            if target and container != "background" and hasattr(instance, "set_widget"):
                mw = getattr(instance, "main_widget", None)
                if mw:
                    w_check = mw[0] if isinstance(mw, (list, tuple)) else mw
                    if (
                        hasattr(w_check, "get_parent")
                        and w_check.get_parent() is not None
                    ):
                        return False

                res = instance.set_widget()
                if not res or len(res) != 2:
                    return False

                widgets, action = res
                widget_list = (
                    widgets if isinstance(widgets, (list, tuple)) else [widgets]
                )

                valid_widgets = [
                    w
                    for w in widget_list
                    if hasattr(w, "get_parent") and w.get_parent() is None
                ]

                if valid_widgets:
                    self.handle_set_widget(
                        action,
                        valid_widgets,
                        target,
                        plugin_id,
                        meta.get("hidden", False),
                    )
        except Exception as e:
            self.logger.error(f"Failed init {plugin_id}: {e}")
        return False

    def _update_plugin_configuration(self, valid_plugins):
        """
        Updates the global configuration file with the list of active plugins.
        """
        self.config_handler.update_config(["plugins", "enabled"], valid_plugins)
        self.config_handler.update_config(
            ["plugins", "disabled"], list(self.disabled_plugins)
        )
        return False

    def validate_deps_list(self, d):
        return isinstance(d, list) and all(isinstance(i, str) for i in d)
