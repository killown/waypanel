import sys
import importlib
import os
from gi.repository import GLib
from typing import Any, Dict

try:
    SOURCE_REMOVE = GLib.SOURCE_REMOVE
except AttributeError:
    SOURCE_REMOVE = False


class PluginResolver(dict):
    """
    A dictionary proxy that resolves plugin instances using full identifiers,
    short names, or module names.
    """

    def __init__(
        self, *args, id_map: Dict[str, str], full_id_map: Dict[str, str], **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.short_name_to_id = id_map
        self.module_name_to_id = full_id_map

    def __getitem__(self, key: str) -> Any:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)

        resolved_id = self.short_name_to_id.get(key) or self.module_name_to_id.get(key)
        if resolved_id and dict.__contains__(self, resolved_id):
            return dict.__getitem__(self, resolved_id)

        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        if dict.__contains__(self, key):
            return True
        resolved_id = self.short_name_to_id.get(key) or self.module_name_to_id.get(key)
        return resolved_id is not None and dict.__contains__(self, resolved_id)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class PluginLoaderHelpers:
    """
    Utility methods for the PluginLoader to manage plugin lifecycle and layout.
    """

    def __init__(self, panel_instance, loader_instance) -> None:
        self.panel_instance = panel_instance
        self.loader_instance = loader_instance
        self.logger = self.panel_instance.logger
        self.overflow_container = None
        self.loader = loader_instance
        self.position_mapping = {
            "top-panel": "top_panel",
            "top-panel-left": "top_panel_box_left",
            "top-panel-box-widgets-left": "top_panel_box_widgets_left",
            "top-panel-center": "top_panel_box_center",
            "top-panel-right": "top_panel_box_right",
            "top-panel-systray": "top_panel_box_systray",
            "top-panel-after-systray": "top_panel_box_for_buttons",
            "bottom-panel": "bottom_panel",
            "bottom-panel-left": "bottom_panel_box_left",
            "bottom-panel-center": "bottom_panel_box_center",
            "bottom-panel-right": "bottom_panel_box_right",
            "bottom-panel-box-widgets-left": "bottom_panel_box_widgets_left",
            "bottom-panel-box-systray": "bottom_panel_box_systray",
            "bottom-panel-box-for-buttons": "bottom_panel_box_for_buttons",
            "left-panel": "left_panel",
            "left-panel-top": "left_panel_box_top",
            "left-panel-center": "left_panel_box_center",
            "left-panel-bottom": "left_panel_box_bottom",
            "right-panel": "right_panel",
            "right-panel-top": "right_panel_box_top",
            "right-panel-center": "right_panel_box_center",
            "right-panel-bottom": "right_panel_box_bottom",
            "background": "background",
        }

    def reload_plugin(self, plugin_name: str) -> None:
        """
        Dynamically reloads a plugin by clearing its widgets and re-importing its module.
        """
        p_id = self.loader.short_name_to_id.get(plugin_name) or plugin_name

        if p_id not in self.loader.plugins_path:
            return

        try:
            old_instance = self.loader.plugins.get(p_id)
            if old_instance:
                main_widget = getattr(old_instance, "main_widget", None)
                if main_widget:
                    widgets = (
                        main_widget
                        if isinstance(main_widget, (list, tuple))
                        else [main_widget]
                    )
                    for w in widgets:
                        parent = w.get_parent()
                        if parent:
                            parent.remove(w)

            self.disable_plugin(p_id)

            module_path = self.loader.plugins_import.get(p_id)
            if not module_path:
                return

            if module_path in sys.modules:
                module = importlib.reload(sys.modules[module_path])
            else:
                module = importlib.import_module(module_path)

            metadata = module.get_plugin_metadata(self.panel_instance)
            plugin_tuple = (
                module,
                metadata.get("container", "background"),
                metadata.get("priority", 0),
                metadata.get("index", 0),
                metadata.get("id", p_id),
            )

            self.enable_plugin(p_id, plugin_tuple)
        except Exception as e:
            self.logger.error(f"Reload failed for '{p_id}': {e}", exc_info=True)

    def _safe_initialize_wrapper(
        self, plugin_name: str, plugin_metadata: tuple
    ) -> bool:
        """
        Wrapper to invoke the internal initialization logic via the GLib idle loop.
        """
        try:
            if not (plugin_metadata and len(plugin_metadata) == 5):
                return SOURCE_REMOVE

            module, position, priority, order, p_id = plugin_metadata
            self.loader._initialize_single_plugin(
                module, position, order, priority, p_id
            )
        except Exception:
            pass
        return SOURCE_REMOVE

    def enable_plugin(self, plugin_name: str, plugin_metadata: tuple) -> None:
        """
        Queues a plugin for safe initialization on the main thread.
        """
        GLib.idle_add(self._safe_initialize_wrapper, plugin_name, plugin_metadata)

    def disable_plugin(self, plugin_name: str):
        """
        Triggers plugin cleanup hooks and removes the instance from the resolver.
        """
        p_id = self.loader.short_name_to_id.get(plugin_name) or plugin_name
        if p_id not in self.loader.plugins:
            return

        plugin_instance = self.loader.plugins[p_id]
        for callback in ["on_disable", "on_stop", "disable"]:
            if hasattr(plugin_instance, callback):
                try:
                    getattr(plugin_instance, callback)()
                except Exception:
                    pass

        if p_id in self.loader.plugins:
            del self.loader.plugins[p_id]

    def get_real_user_home(self):
        """
        Determines the actual home directory of the user, accounting for privilege escalation.
        """
        for env_var in ["SUDO_USER", "PKEXEC_UID"]:
            user = os.environ.get(env_var)
            if user:
                return os.path.expanduser(f"~{user}")
        return os.environ.get("HOME") or os.path.expanduser("~")

    def _resolve_dynamic_deps(self, metadata: dict) -> list:
        """
        Injects necessary core panel dependencies based on the designated plugin container.
        """
        p_id = metadata.get("id", "")
        container = metadata.get("container", "background")

        core_panels = {
            "org.waypanel.plugin.top_panel",
            "org.waypanel.plugin.bottom_panel",
            "org.waypanel.plugin.left_panel",
            "org.waypanel.plugin.right_panel",
        }
        if p_id in core_panels:
            return metadata.get("deps", [])

        deps = metadata.get("deps", [])
        if not isinstance(deps, list):
            deps = [deps]

        direction = container.split("-")[0]
        dep_map = {
            "top": "top_panel",
            "bottom": "bottom_panel",
            "left": "left_panel",
            "right": "right_panel",
        }

        required_dep = dep_map.get(direction)
        if required_dep and required_dep not in deps:
            deps.append(required_dep)

        return deps

    def _get_target_panel_box(self, position, plugin_name=None):
        """
        Retrieves the panel's GTK container corresponding to a logical position string.
        """
        target_attr = self.position_mapping.get(position)
        if target_attr is None:
            return None
        if target_attr == "background":
            return "background"
        if not hasattr(self.panel_instance, target_attr):
            self.logger.warning(
                f"Panel box '{target_attr}' not yet initialized for {plugin_name}."
            )
            return None
        return getattr(self.panel_instance, target_attr)

    def register_overflow_container(self, plugin_instance):
        """
        Designates a plugin instance as the global overflow widget handler.
        """
        self.loader_instance.overflow_container = plugin_instance

    def ensure_proportional_layout(self):
        """
        Monitors panel layout allocation to ensure side containers do not exceed width limits.
        """
        max_attempts = self.loader.ensure_proportional_layout_attempts["max"]
        current_attempts = self.loader.ensure_proportional_layout_attempts["current"]
        sections_to_check = [
            ("top_panel_box_right", "Right"),
            ("top_panel_box_center", "Center"),
            ("top_panel_box_left", "Left"),
        ]

        for section, _ in sections_to_check:
            if not hasattr(self.panel_instance, section):
                return True

        if current_attempts >= max_attempts:
            return False

        self.loader.ensure_proportional_layout_attempts["current"] += 1
        if not self.panel_instance.plugins_startup_finished:
            return True

        try:
            width = self.loader.config_handler.get_root_setting(
                ["org.waypanel.panel", "top", "width"]
            )
            if not width or width <= 0:
                return True

            for section, side_name in sections_to_check:
                container = getattr(self.panel_instance, section)
                if container.get_allocated_width() > (width / 3):
                    violating_plugin = self.loader.last_widget_plugin_added
                    self.disable_plugin(violating_plugin)
                    return False
            return True
        except Exception:
            return True
