import sys
import importlib
import os
from gi.repository import GLib  # pyright: ignore
from src.shared.notify_send import Notifier

try:
    SOURCE_REMOVE = GLib.SOURCE_REMOVE
except AttributeError:
    SOURCE_REMOVE = False


class PluginLoaderHelpers:
    def __init__(self, panel_instance, loader_instance) -> None:
        self.panel_instance = panel_instance
        self.loader_instance = loader_instance
        self.logger = self.panel_instance.logger
        self.overflow_container = None
        self.loader = loader_instance

    def reload_plugin(self, plugin_name: str) -> None:
        """
        Initiates a dynamic, non-disruptive reload of a single plugin.
        It safely removes the old widget, disables the old instance, reloads
        the module from disk, extracts its new placement metadata, and
        delegates re-initialization to the robust `enable_plugin` method.
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
                        if isinstance(main_widget, tuple)
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
            metadata_dict = getattr(module, "get_plugin_metadata")(self.panel_instance)
            position = metadata_dict.get("container", "background")
            order = metadata_dict.get("index", 0)
            priority = metadata_dict.get("priority", 0)
            plugin_metadata = (module, position, order, priority)
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
        A robust, exception-safe wrapper for plugin initialization.
        This function is executed by the GLib main loop and is responsible
        for calling the actual plugin initializer, logging the true result,
        and catching any exceptions that occur during initialization.
        Args:
            plugin_name: The name of the plugin being initialized.
            plugin_metadata: The 4-tuple (module, position, order, priority).
        Returns:
            bool: GLib.SOURCE_REMOVE (or False) to ensure this idle task
                  is removed from the main loop after execution.
        """
        try:
            if not (plugin_metadata and len(plugin_metadata) == 4):
                self.logger.error(
                    f"Invalid metadata for '{plugin_name}' passed to wrapper. "
                    "Skipping initialization."
                )
                return SOURCE_REMOVE
            module, position, order, priority = plugin_metadata
            self.loader._initialize_single_plugin(module, position, order, priority)
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
        """Enable a plugin by name.
        Schedules a plugin to be initialized safely on the GLib main loop
        using a robust wrapper.
        Args:
            plugin_name: The name of the plugin to enable.
            plugin_metadata: A 4-tuple containing the required data:
                             (module, position, order, priority).
        """
        if plugin_name not in self.loader.plugins_path:
            self.logger.error(
                f"Plugin '{plugin_name}' not found in plugins_path. Skipping enable."
            )
            return
        if not (plugin_metadata and len(plugin_metadata) == 4):
            self.logger.error(
                f"Invalid or missing metadata for enabling plugin: {plugin_name}. "
                "Expected 4-tuple (module, position, order, priority)."
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
                f"Error scheduling plugin '{plugin_name}' for enabling: {e}",
                level="error",
            )

    def disable_plugin(self, plugin_name):
        """Disable a plugin by name.
        Safely stops and disables a plugin instance, ensuring proper cleanup
        by calling available lifecycle methods. Handles both plugins that
        support custom disable logic and those that don't.
        Args:
            plugin_name (str): The name of the plugin to disable.
        """
        if plugin_name not in self.loader.plugins:
            self.logger.warning(f"Plugin '{plugin_name}' not found.")
            return
        plugin_instance = self.loader.plugins[plugin_name]
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

    def get_real_user_home(self):
        """Determine the real user's home directory.
        This function handles privilege escalation scenarios (like sudo/pkexec) to ensure
        paths point to the original user's home directory for configuration and data access.
        It respects the $HOME environment variable for maximum compatibility in various desktop
        environments.
        Returns:
            str: The absolute path to the real user's home directory.
        """
        if "SUDO_USER" in os.environ:
            return os.path.expanduser(f"~{os.environ['SUDO_USER']}")
        elif "PKEXEC_UID" in os.environ:
            return os.path.expanduser(f"~{os.environ['PKEXEC_UID']}")
        return os.environ.get("HOME") or os.path.expanduser("~")

    def _get_target_panel_box(self, position, plugin_name=None):
        """
        Determines where to place the plugin's widget in the paneleturns:
            object: Target box/widget if found, or 'background' if no UI is needed.
            None: If invalid position or missing target.
        """
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
        target_attr = self.position_mapping.get(position)
        if target_attr is None:
            self.logger.error(
                f"Invalid position '{position}' for plugin {plugin_name}."
            )
            return None
        if target_attr == "background":
            self.logger.debug(f"Plugin {plugin_name} is a background plugin.")
            return "background"
        if not hasattr(self.panel_instance, target_attr):
            self.logger.warning(
                f"Panel box '{target_attr}' is not yet initialized for plugin {plugin_name}."
            )
            return None
        return getattr(self.panel_instance, target_attr)

    def register_overflow_container(self, plugin_instance):
        """Stores the instance of the overflow container plugin."""
        self.loader_instance.overflow_container = plugin_instance
        self.logger.info("Overflow indicator container registered.")

    def ensure_proportional_layout(self):
        """
        Checks if the actual allocated width of the Left, Center, or Right panel containers
        exceeds their theoretical limits (output_width / 3). If any side
        exceeds its limit, the 'last_plugin' added plugin is disabled.
        """
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
            self.logger.warning(
                "Proportional layout check reached max attempts. Stopping source."
            )
            return False
        self.loader.ensure_proportional_layout_attempts["current"] += 1
        if not self.panel_instance.plugins_startup_finished:
            return True
        try:
            width = self.loader.config_handler.get_root_setting(
                ["org.waypanel.panel", "top", "width"]
            )
            if width is None or width <= 0:
                self.logger.warning(
                    "Panel width not configured or invalid. Skipping proportional space check."
                )
                return True
            limit_exceeded = False
            violating_side = "Unknown"
            for section, side_name in sections_to_check:
                container = getattr(self.panel_instance, section)
                max_width_size = width / 3
                allocated_width = container.get_allocated_width()
                if allocated_width > max_width_size:
                    self.logger.warning(
                        f"Space violation detected in {side_name}. "
                        f"Allocated: {allocated_width:.2f}px, Max: {max_width_size:.2f}px."
                    )
                    limit_exceeded = True
                    violating_side = side_name
                    break
            if limit_exceeded:
                self.disable_plugin(self.loader.last_widget_plugin_added)
                icon_name = "plugins-symbolic"
                self.nofitier = Notifier()
                self.notify_send = self.nofitier.notify_send
                self.notify_send(
                    "Plugin Loader",
                    f"{self.loader.last_widget_plugin_added} disabled due to violation in {violating_side}. Removed element for layout stability.",
                    icon_name,
                )
                return False
            return True
        except Exception as e:
            self.logger.error(f"Error during proportional space check: {e}")
            return True
