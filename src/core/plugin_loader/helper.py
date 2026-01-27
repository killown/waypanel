import sys
import importlib
import os
import traceback
from gi.repository import GLib
from gi.repository.Gio import proxy_resolver_get_default  # pyright: ignore
from src.shared.notify_send import Notifier
from typing import Any, Dict, Tuple, Union, Optional

# Updated to match the Loader's 5-element metadata structure
PluginMetadataTuple = Tuple[Any, str, int, int, str]

try:
    SOURCE_REMOVE = GLib.SOURCE_REMOVE
except AttributeError:
    SOURCE_REMOVE = False


class PluginResolver(dict):
    """
    Proxy that resolves short plugin names (e.g., 'clock') to full plugin IDs
    (e.g., 'org.waypanel.plugin.clock') upon lookup.
    """

    def __init__(
        self, *args, id_map: Dict[str, str], full_id_map: Dict[str, str], **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.short_name_to_id = id_map
        self.module_name_to_id = full_id_map

    def __getitem__(self, key: str) -> Any:
        if super().__contains__(key):
            return super().__getitem__(key)
        resolved_id_by_short = self.short_name_to_id.get(key)
        if resolved_id_by_short and super().__contains__(resolved_id_by_short):
            return super().__getitem__(resolved_id_by_short)
        resolved_id_by_module_name = self.module_name_to_id.get(key)
        if resolved_id_by_module_name and super().__contains__(
            resolved_id_by_module_name
        ):
            return super().__getitem__(resolved_id_by_module_name)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        if super().__contains__(key):
            return True
        if self.short_name_to_id.get(key) and super().__contains__(
            self.short_name_to_id.get(key)
        ):
            return True
        if self.module_name_to_id.get(key) and super().__contains__(
            self.module_name_to_id.get(key)
        ):
            return True
        return False


class PluginLoaderHelpers:
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
        Initiates a dynamic, non-disruptive reload of a single plugin.
        """
        if plugin_name not in self.loader.plugins_path:
            self.logger.error(
                f"Plugin '{plugin_name}' not found in plugins_path. Skipping reload."
            )
            return
        try:
            old_plugin_instance = self.loader.plugins.get(plugin_name)
            if old_plugin_instance:
                main_widget = getattr(old_plugin_instance, "main_widget", None)
                if main_widget:
                    widget_to_remove = (
                        main_widget[0]
                        if isinstance(main_widget, (tuple, list))
                        else main_widget
                    )
                    if widget_to_remove and widget_to_remove.get_parent():
                        widget_to_remove.get_parent().remove(widget_to_remove)
                        self.logger.info(
                            f"Removed old widget for plugin: {plugin_name}"
                        )
            self.disable_plugin(plugin_name)
            module_path = self.loader.plugins_import.get(plugin_name)
            if not module_path:
                self.logger.error(
                    f"Module path for plugin '{plugin_name}' not found. Cannot reload."
                )
                return
            if module_path in sys.modules:
                module = sys.modules[module_path]
                importlib.reload(module)
                self.logger.debug(f"Reloaded module from disk: {module_path}")
            else:
                module = importlib.import_module(module_path)
                self.logger.debug(f"Imported new module: {module_path}")

            if not hasattr(module, "get_plugin_metadata"):
                self.logger.error(
                    f"Reloaded plugin '{plugin_name}' is missing "
                    "get_plugin_metadata(). Skipping."
                )
                return

            metadata_dict = module.get_plugin_metadata(self.panel_instance)
            position = metadata_dict.get("container", "background")
            order = metadata_dict.get("index", 0)
            priority = metadata_dict.get("priority", 0)
            p_id = metadata_dict.get("id", plugin_name)

            # Use the 5-tuple expected by the loader
            plugin_metadata = (module, position, priority, order, p_id)
            self.enable_plugin(plugin_name, plugin_metadata)
            self.logger.info(f"Reload scheduled for plugin: {plugin_name}")
        except Exception as e:
            self.logger.error(
                f"Critical error during reload process for '{plugin_name}': {e}",
                exc_info=True,
            )

    def _safe_initialize_wrapper(
        self, plugin_name: str, plugin_metadata: tuple
    ) -> bool:
        """
        Robust, exception-safe wrapper for plugin initialization via GLib idle.
        """
        try:
            if not (plugin_metadata and len(plugin_metadata) == 5):
                self.logger.error(
                    f"Invalid metadata 5-tuple for '{plugin_name}'. Skipping."
                )
                return SOURCE_REMOVE

            module, position, priority, order, p_id = plugin_metadata
            self.loader._initialize_single_plugin(
                module, position, order, priority, p_id
            )
            self.logger.info(
                f"Successfully enabled and initialized plugin: {plugin_name}"
            )
        except Exception as e:
            self.logger.error(
                f"Failed to initialize plugin '{plugin_name}': {e}",
                exc_info=True,
            )
        return SOURCE_REMOVE

    def enable_plugin(self, plugin_name: str, plugin_metadata: tuple) -> None:
        """Schedules a plugin to be initialized safely on the GLib main loop."""
        if plugin_name not in self.loader.plugins_path:
            self.logger.error(
                f"Plugin '{plugin_name}' not found in plugins_path. Skipping enable."
            )
            return
        if not (plugin_metadata and len(plugin_metadata) == 5):
            self.logger.error(
                f"Invalid metadata for enabling plugin: {plugin_name}. Expected 5-tuple."
            )
            return
        try:
            GLib.idle_add(
                self._safe_initialize_wrapper,
                plugin_name,
                plugin_metadata,
            )
            self.logger.info(f"Scheduled plugin for enabling: {plugin_name}")
        except Exception as e:
            self.logger.error(
                f"Error scheduling plugin '{plugin_name}' for enabling: {e}"
            )

    def disable_plugin(self, plugin_name: str):
        """Safely stops and disables a plugin instance."""
        if plugin_name not in self.loader.plugins:
            self.logger.warning(f"Plugin '{plugin_name}' not found.")
            return
        plugin_instance = self.loader.plugins[plugin_name]

        # Lifecycle Sequence: on_disable -> on_stop -> disable
        for callback in ["on_disable", "on_stop", "disable"]:
            if hasattr(plugin_instance, callback):
                try:
                    getattr(plugin_instance, callback)()
                    self.logger.info(f"Executed {callback} for plugin: {plugin_name}")
                except Exception as e:
                    self.logger.error(f"Error during {callback} for {plugin_name}: {e}")

        # Cleanup instance from map to prevent leaks
        if plugin_name in self.loader.plugins:
            del self.loader.plugins[plugin_name]

    def get_real_user_home(self):
        """Handles privilege escalation to ensure paths point to the real user home."""
        if "SUDO_USER" in os.environ:
            return os.path.expanduser(f"~{os.environ['SUDO_USER']}")
        elif "PKEXEC_UID" in os.environ:
            return os.path.expanduser(f"~{os.environ['PKEXEC_UID']}")
        return os.environ.get("HOME") or os.path.expanduser("~")

    def _resolve_dynamic_deps(self, metadata: dict) -> list:
        """
        Dynamically injects core panel dependencies based on the target container.

        This ensures that any plugin attempting to attach to a panel (top, bottom, left, or right)
        is forced to wait for that specific panel's initialization. This prevents race
        conditions where a plugin tries to access GTK containers before they exist.

        Args:
            metadata (dict): The plugin's metadata containing 'id', 'container', and 'deps'.

        Returns:
            list: The updated list of dependencies including the required core panel.
        """
        container = metadata.get("container", "background")
        deps = metadata.get("deps", [])
        p_id = metadata.get("id", "")

        # CRITICAL: Prevent circular dependencies.
        # If the plugin IS one of the core panels, it must not depend on itself,
        # otherwise the topological sorter will lock into an infinite loop.
        if (
            p_id == "org.waypanel.plugin.top_panel"
            or p_id == "org.waypanel.plugin.bottom_panel"
            or p_id == "org.waypanel.plugin.left_panel"
            or p_id == "org.waypanel.plugin.right_panel"
        ):
            return deps

        if not isinstance(deps, list):
            deps = [deps]

        # Map logical position (e.g., 'top-panel-left') to internal panel attribute
        target_internal = self.position_mapping.get(container, "background")

        # Map internal direction prefix to the required dependency ID
        direction_to_dep = {
            "top": "top_panel",
            "bottom": "bottom_panel",
            "left": "left_panel",
            "right": "right_panel",
        }

        # Check all directions to determine which core panel must be initialized first.
        # This is necessary because Waypanel supports multi-panel layouts. A plugin
        # targeting 'top-panel-center' must wait for 'top_panel', while a plugin
        # targeting 'left-panel-bottom' must wait for 'left_panel'. Without checking
        # all directions, plugins would attempt to initialize against 'None' attributes
        for direction, dep in direction_to_dep.items():
            if target_internal.startswith(direction):
                if dep not in deps:
                    deps.append(dep)
                break

        return deps

    def _get_target_panel_box(self, position, plugin_name=None):
        """Maps logical position strings to panel GTK containers."""
        target_attr = self.position_mapping.get(position)
        if target_attr is None:
            self.logger.error(
                f"Invalid position '{position}' for plugin {plugin_name}."
            )
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
        """Registers the overflow container for hidden widgets."""
        self.loader_instance.overflow_container = plugin_instance
        self.logger.info("Overflow indicator container registered.")

    def ensure_proportional_layout(self):
        """Enforces width constraints to prevent UI breaking (limit = width/3)."""
        max_attempts = self.loader.ensure_proportional_layout_attempts["max"]
        current_attempts = self.loader.ensure_proportional_layout_attempts["current"]

        sections_to_check = [
            ("top_panel_box_right", "Top Panel: Right Space"),
            ("top_panel_box_center", "Top Panel: Center Space"),
            ("top_panel_box_left", "Top Panel: Left Space"),
        ]

        for section, _ in sections_to_check:
            if not hasattr(self.panel_instance, section):
                return True

        if current_attempts >= max_attempts:
            self.logger.warning("Proportional layout check reached max attempts.")
            return False

        self.loader.ensure_proportional_layout_attempts["current"] += 1
        if not self.panel_instance.plugins_startup_finished:
            return True

        try:
            width = self.loader.config_handler.get_root_setting(
                ["org.waypanel.panel", "top", "width"]
            )
            if width is None or width <= 0:
                return True

            limit_exceeded = False
            violating_side = "Unknown"
            for section, side_name in sections_to_check:
                container = getattr(self.panel_instance, section)
                max_width_size = width / 3
                allocated_width = container.get_allocated_width()
                if allocated_width > max_width_size:
                    self.logger.warning(
                        f"Violation in {side_name}: {allocated_width}px > {max_width_size}px"
                    )
                    limit_exceeded = True
                    violating_side = side_name
                    break

            if limit_exceeded:
                violating_plugin = self.loader.last_widget_plugin_added
                self.disable_plugin(violating_plugin)
                notifier = Notifier()
                notifier.notify_send(
                    "Plugin Loader",
                    f"{violating_plugin} disabled due to violation in {violating_side}.",
                    "plugins-symbolic",
                )
                return False
            return True
        except Exception as e:
            self.logger.error(f"Error during proportional space check: {e}")
            return True
