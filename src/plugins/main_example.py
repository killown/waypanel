from gi.repository import Gtk, GLib  # pyright: ignore
import time
from concurrent.futures import Future
from typing import Any, Optional

# NOTE: BasePlugin provides all core tools, including the command runner,
# logger, IPC, and all helper methods aliased as properties (like notify_send).
from src.plugins.core._base import BasePlugin

# Set dependencies for this plugin (top_panel is required for placement)
DEPS = ["top_panel", "event_manager"]


# --- Plugin Metadata and Placement ---


def get_plugin_placement(panel_instance: Any):
    """
    Define where the plugin should be placed in the panel and its order/priority.
    Uses the instance's inherited get_config for dynamic placement.
    """
    position = panel_instance.get_config(
        ["example_base_plugin", "placement", "position"], "top-panel-right"
    )
    order = panel_instance.get_config(["example_base_plugin", "placement", "order"], 1)
    priority = panel_instance.get_config(
        ["example_base_plugin", "placement", "priority"], 1
    )

    return position, order, priority


def initialize_plugin(panel_instance: Any):
    """
    Initialize the plugin class instance.
    """
    plugin_instance = ComprehensiveBaseExample(panel_instance)
    plugin_instance.setup_ui()
    return plugin_instance


# --- Main Plugin Class ---


class ComprehensiveBaseExample(BasePlugin):
    """
    A definitive example demonstrating the use of all core BasePlugin APIs,
    prioritizing direct method aliases for clean code.
    """

    # Class dependency list
    DEPS = DEPS

    def __init__(self, panel_instance: Any):
        # WARNING: MUST call super() to inject all core resources and tools.
        super().__init__(panel_instance)

        self.popover: Optional[Gtk.Popover] = None

        # UI Initialization
        self.main_button = Gtk.Button(label="API Demo")

        # 1. IMPROVEMENT: Use the direct get_icon alias instead of self.gtk_helper.set_widget_icon_name
        icon_name = self.gtk_helper.icon_exist(
            "system-run-symbolic", ["fallback_icon_name_1", "fallback_icon_name_2"]
        )
        button = Gtk.Button()
        icon_name = self.gtk_helper.icon_exist(
            "data-information", ["fallback_icon_name_1", "fallback_icon_name_2"]
        )
        button.set_icon_name(icon_name)

        self.main_button.set_child(button)
        # Fallback for set_widget, though set_child is preferred for modern GTK
        self.main_button.set_tooltip_text("BasePlugin Comprehensive Demo")

        # 2. Main Widget Definition: Required metadata for the plugin loader.
        # Using the Gtk.Button widget as the main widget
        self.main_widget = (self.main_button, "append")

        # UI state for dynamic updates
        self.thread_label = Gtk.Label(label="Thread Status: Ready")

        # 3. Logger Usage: Use the direct logger property.
        self.logger.info("ComprehensiveBaseExample initialized successfully.")

    def setup_ui(self):
        """Creates the popover menu with buttons to trigger all demo functionalities."""

        self.popover = Gtk.Popover.new()
        self.popover.set_parent(self.main_button)
        vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_start=15,
            margin_end=15,
            margin_top=15,
            margin_bottom=15,
        )

        title = Gtk.Label(label="<b>BasePlugin API Demos</b>", use_markup=True)
        vbox.append(title)
        vbox.append(Gtk.Separator())

        # Concurrency Demos
        btn_thread = Gtk.Button(label="Run Blocking Task (3s delay)")
        btn_thread.connect("clicked", self._demo_run_thread)
        vbox.append(btn_thread)
        vbox.append(self.thread_label)

        btn_async = Gtk.Button(label="Run Async IPC Query")
        btn_async.connect("clicked", self._demo_run_async)
        vbox.append(btn_async)

        vbox.append(Gtk.Separator())

        # Core Feature Demos
        btn_config = Gtk.Button(label="Toggle & Save Config Setting")
        btn_config.connect("clicked", self._demo_update_config)
        vbox.append(btn_config)

        btn_cmd = Gtk.Button(label="Run Shell Command & Use Path Helper")
        btn_cmd.connect("clicked", self._demo_cmd_and_helpers)
        vbox.append(btn_cmd)

        # 2. IMPROVEMENT: Panel and Plugin Access Demo
        btn_panel_access = Gtk.Button(label="Access Panel/Plugin Properties")
        btn_panel_access.connect("clicked", self._demo_panel_access)
        vbox.append(btn_panel_access)

        # 3. IMPROVEMENT: Layer Shell Helper Demo
        btn_layer_shell = Gtk.Button(label="Layer Shell Helper Demo")
        btn_layer_shell.connect("clicked", self._demo_layer_shell_helpers)
        vbox.append(btn_layer_shell)

        self.popover.set_child(vbox)
        self.main_button.connect("clicked", lambda w: self.popover.popup())  # pyright: ignore

        # 4. GTK Helper Alias: Use the direct property for convenience
        self.add_cursor_effect(self.main_button)

    # --- Demo Methods ---

    def _blocking_task(self, delay: int) -> str:
        """A placeholder for a potentially long-running, CPU-bound task."""
        self.logger.info(f"Thread: Starting blocking task for {delay} seconds...")
        time.sleep(delay)
        return f"Task finished after {delay} seconds."

    def _thread_finished_callback(self, future: Future):
        """Callback executed in the GTK thread after the blocking task completes."""
        if future.exception():
            # Use the direct GTK helper alias for safe UI updates
            self.update_widget_safely(
                self.thread_label,  # pyright: ignore
                "set_label",
                f"Thread Status: Error! {future.exception()}",
            )
            self.logger.exception("Error in background thread.")
            return

        result_message = future.result()
        # Use the direct GTK helper alias for safe UI updates
        self.update_widget_safely(
            self.thread_label,  # pyright: ignore
            "set_label",
            f"Thread Status: {result_message}",  # pyright: ignore
        )
        self.logger.info(f"Thread: Task completed with result: {result_message}")

    def _demo_run_thread(self, button: Gtk.Button):
        """Initiates the blocking task in a separate thread."""
        if self.popover:
            self.popover.popdown()
        self.update_widget_safely(
            self.thread_label,  # pyright: ignore
            "set_label",
            "Thread Status: Running...",  # pyright: ignore
        )

        # 5. Concurrency: Use run_in_thread for blocking/heavy tasks.
        future = self.run_in_thread(self._blocking_task, 3)
        # Schedule the callback to run in the safe GTK thread
        future.add_done_callback(
            lambda f: self.schedule_in_gtk_thread(self._thread_finished_callback, f)
        )

    async def _async_ipc_query(self):
        """An awaitable coroutine to query the Wayfire compositor."""
        self.logger.info("Async: Querying Wayfire outputs...")

        # 6. IPC Access: Use self.ipc for async Wayland communication.
        outputs = await self.ipc.get_outputs()

        if outputs:
            # Check a view property using the Wayfire helper alias
            first_output_valid = self.is_view_valid(outputs[0])
            return (
                f"IPC Success: Found {len(outputs)} outputs. "
                f"First view valid: {first_output_valid}"
            )
        else:
            return "IPC Failure: No outputs found."

    def _async_finished_callback(self, result: str):
        """Callback to run in the GTK thread after the async task is done."""
        # 7. Notifier Alias: Use the direct notify_send property.
        self.notify_send("Async IPC Done", result, "dialog-information-symbolic")
        if self.popover:
            self.popover.popdown()

    def _demo_run_async(self, button: Gtk.Button):
        """Initiates the asynchronous IPC task."""
        if self.popover:
            self.popover.popdown()
        # 8. Concurrency: Use run_in_async_task for awaitable operations.
        self.run_in_async_task(self._async_ipc_query(), self._async_finished_callback)

    def _demo_update_config(self, button: Gtk.Button):
        """Toggles a config setting, saves it, and notifies the user."""
        current_value = self.get_config(["example_base_plugin", "demo_setting"], True)
        new_value = not current_value

        # 9. Config Update: Use update_config to safely modify and save the TOML file.
        success = self.update_config(["example_base_plugin", "demo_setting"], new_value)

        if success:
            # 10. Notifier Alias: Use the direct notify_send property.
            self.notify_send(
                "Config Saved",
                f"demo_setting toggled to: {new_value}. Config file updated.",
                "preferences-system-symbolic",
            )
            self.logger.info(f"Config updated successfully: demo_setting = {new_value}")
        else:
            self.logger.error("Failed to update config.")

        if self.popover:
            self.popover.popdown()

    def _demo_cmd_and_helpers(self, button: Gtk.Button):
        """Demonstrates the command runner and path helper."""

        # 11. Command Runner: Execute a non-blocking shell command.
        self.cmd.run(
            "play -v 0.5 --no-show-progress "
            "/usr/share/sounds/freedesktop/stereo/complete.oga || true"
        )

        # 12. Path Helper Alias: Use the direct get_cache_path property.
        cache_path = self.get_cache_path()

        # 13. Data Validation Helper Alias: Use a direct validation method.
        is_path_string = self.validate_string(cache_path)

        # 14. Notifier Alias: Use the direct notify_send property.
        self.notify_send(
            "Helper Tools Demo",
            f"Cache Path: {cache_path}. Validated as string: {is_path_string}",
            "folder-symbolic",
        )
        self.logger.info(f"Cache Path: {cache_path}. Command run successfully.")
        if self.popover:
            self.popover.popdown()

    def _demo_panel_access(self, button: Gtk.Button):
        """Demonstrates access to other panels and plugins."""
        if self.popover:
            self.popover.popdown()

        # Use the direct panel properties
        top_panel_present = self.top_panel is not None
        num_plugins = len(self.plugins)
        plugin_names = ", ".join(self.plugins.keys())

        # Attempt to access the 'event_manager' dependency
        event_manager = self.plugins.get("event_manager")
        em_exists = event_manager is not None

        details = (
            f"Top Panel Exists: {top_panel_present}\n"
            f"Total Plugins Loaded: {num_plugins}\n"
            f"Event Manager Plugin Found: {em_exists}"
        )
        self.notify_send(
            "Panel & Plugin Properties", details, "applications-system-symbolic"
        )
        self.logger.debug(f"Loaded Plugins: {plugin_names}")

    def _demo_layer_shell_helpers(self, button: Gtk.Button):
        """Demonstrates use of the Layer Shell properties for Wayland window creation."""
        if self.popover:
            self.popover.popdown()

        # NOTE: These are references to the core layer-shell functions.
        # To actually open a window, you'd call them with a new Gtk.Window().

        self.notify_send(
            "Layer Shell Helper References",
            f"LayerShell reference: {self.layer_shell.__name__}\n"
            f"Exclusive setter reference: {self.set_layer_pos_exclusive.__name__}\n"
            f"Exclusive unset reference: {self.unset_layer_pos_exclusive.__name__}",
            "input-tablet-symbolic",
        )
        self.logger.info("Successfully accessed Layer Shell helper properties.")

    # --- Plugin Lifecycle Hooks ---

    def _demo_timeout_check(self) -> bool:
        """Called by the GLib timeout in the main thread."""
        self.logger.debug("GLib Timeout: Running recurring check.")
        self.notify_send(
            "Recurring Task",
            "GLib Timeout check ran in GTK thread.",
            "system-run-symbolic",
        )
        return True  # Return True to keep the timeout active

    def on_start(self):
        """Hook called when the plugin is fully loaded and ready."""
        self.logger.info("Lifecycle: ComprehensiveBaseExample is fully started.")
        # Example of recurring task using GLib timeout
        # NOTE: The lambda wrapping from the previous version is not needed if the function runs directly in the GTK loop.
        self.timeout_id = GLib.timeout_add_seconds(30, self._demo_timeout_check)

    def on_stop(self):
        """Hook called when the plugin is stopped or unloaded (e.g., Waypanel shutdown)."""
        # 15. Cleanup: Remove scheduled tasks.
        if hasattr(self, "timeout_id") and self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.logger.info("Lifecycle: Removed GLib timeout.")

        self.logger.info(
            "Lifecycle: ComprehensiveBaseExample is stopping and cleaning up."
        )

    # --- Documentation Methods (As required by Waypanel standard) ---

    def about(self):
        """A full-featured plugin demonstrating safe, non-blocking usage of all core Waypanel BasePlugin APIs: concurrency, IPC, configuration management, helper tools, and panel/plugin access, prioritizing direct method aliases."""
        return self.about.__doc__

    def code_explanation(self):
        """
        The definitive guide to the BasePlugin API, demonstrating best practices:

        1.  **Direct Aliases**: Uses methods like `self.notify_send`, `self.get_cache_path`, and `self.get_icon` directly.
        2.  **Concurrency**: Utilizes `self.run_in_thread` (for blocking I/O) and `self.run_in_async_task` (for IPC queries).
        3.  **GTK Safety**: Leverages `self.schedule_in_gtk_thread` and `self.update_widget_safely` for UI updates from background tasks.
        4.  **Core Tools**: Demonstrates config (`self.get_config`, `self.update_config`), shell execution (`self.cmd.run`), and Wayfire IPC (`self.ipc`).
        5.  **Panel Access**: Shows direct access to panel widgets (`self.top_panel`) and other loaded plugins (`self.plugins`).
        6.  **Layer Shell**: Exposes the helper functions for Wayland layer shell integration (`self.layer_shell`, `self.set_layer_pos_exclusive`).
        """
        return self.code_explanation.__doc__
