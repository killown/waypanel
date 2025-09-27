from gi.repository import Gtk, GLib  # pyright: ignore
import time
from concurrent.futures import Future

# NOTE: BasePlugin provides all core tools, including the command runner,
# logger, IPC, and all helper methods aliased as properties (like notify_send).
from src.plugins.core._base import BasePlugin

# Set dependencies for this plugin (top_panel is required for placement)
DEPS = ["top_panel", "event_manager"]


# --- Plugin Metadata and Placement ---


def get_plugin_placement(panel_instance):
    """
    Define where the plugin should be placed in the panel and its order/priority.
    Uses the instance's inherited get_config for dynamic placement.

    Returns:
        tuple: (position, order, priority) for UI plugins
        str: "background" for non-UI/background plugins

    Valid Positions:
        - Top Panel: "top-panel-left", "top-panel-center", "top-panel-right",
                     "top-panel-systray", "top-panel-after-systray"
        - Bottom Panel: "bottom-panel-left", "bottom-panel-center",
                        "bottom-panel-right"
        - Left Panel: "left-panel-top", "left-panel-center", "left-panel-bottom"
        - Right Panel: "right-panel-top", "right-panel-center",
                       "right-panel-bottom"
        - Background: "background" (for non-UI plugins)
    """
    # 1. Configuration Access: Use the safe, inherited method to get config.
    position = panel_instance.get_config(
        ["example_base_plugin", "placement", "position"], "top-panel-right"
    )
    order = panel_instance.get_config(["example_base_plugin", "placement", "order"], 1)
    priority = panel_instance.get_config(
        ["example_base_plugin", "placement", "priority"], 1
    )

    return position, order, priority


def initialize_plugin(panel_instance):
    """
    Initialize the plugin class instance.
    """
    plugin_instance = ComprehensiveBaseExample(panel_instance)
    plugin_instance.setup_ui()

    # Returning the instance allows other plugins to access it via self.plugins["comprehensive_base_example"]
    return plugin_instance


# --- Main Plugin Class ---


class ComprehensiveBaseExample(BasePlugin):
    """
    A definitive example demonstrating the use of all core BasePlugin APIs,
    prioritizing direct method aliases for clean code.
    """

    # Class dependency list
    DEPS = DEPS

    def __init__(self, panel_instance):
        # WARNING: MUST call super() to inject all core resources and tools.
        super().__init__(panel_instance)

        self.popover = None

        # UI Initialization
        self.main_button = Gtk.Button(label="API Demo")

        # Use the gtk_helper property to set the icon
        icon_name = self.gtk_helper.set_widget_icon_name(
            "example-base", ["system-run-symbolic"]
        )
        self.main_button.set_icon_name(icon_name)

        # 2. Main Widget Definition: Required metadata for the plugin loader.
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

        # === Demo 1: Threading (Blocking Task) & Safe UI Update ===
        btn_thread = Gtk.Button(label="Run Blocking Task (3s delay)")
        btn_thread.connect("clicked", self._demo_run_thread)
        vbox.append(btn_thread)
        vbox.append(self.thread_label)

        # === Demo 2: Async/Await (Non-Blocking IPC) ===
        btn_async = Gtk.Button(label="Run Async IPC Query")
        btn_async.connect("clicked", self._demo_run_async)
        vbox.append(btn_async)

        # === Demo 3: Config Update & Notifier (Direct Alias) ===
        btn_config = Gtk.Button(label="Toggle & Save Config Setting")
        btn_config.connect("clicked", self._demo_update_config)
        vbox.append(btn_config)

        # === Demo 4: Command Runner, Path, and Data Helpers ===
        btn_cmd = Gtk.Button(label="Run Shell Command & Use Path Helper")
        btn_cmd.connect("clicked", self._demo_cmd_and_helpers)
        vbox.append(btn_cmd)

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

    def _demo_run_thread(self, button):
        """Initiates the blocking task in a separate thread."""
        self.popover.popdown()  # pyright: ignore
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
        self.popover.popdown()  # pyright: ignore

    def _demo_run_async(self, button):
        """Initiates the asynchronous IPC task."""
        # 8. Concurrency: Use run_in_async_task for awaitable operations.
        self.run_in_async_task(self._async_ipc_query(), self._async_finished_callback)

    def _demo_update_config(self, button):
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

        self.popover.popdown()  # pyright: ignore

    def _demo_cmd_and_helpers(self, button):
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
        self.popover.popdown()  # pyright: ignore

    # --- Plugin Lifecycle Hooks ---

    def on_start(self):
        """Hook called when the plugin is fully loaded and ready."""
        self.logger.info("Lifecycle: ComprehensiveBaseExample is fully started.")
        # Example of recurring task using GLib timeout
        self.timeout_id = GLib.timeout_add_seconds(
            30,
            lambda: self.schedule_in_gtk_thread(self._demo_timeout_check),  # pyright: ignore
        )

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
        """A full-featured plugin demonstrating safe, non-blocking usage of all core Waypanel BasePlugin APIs: concurrency, IPC, configuration management, and helper tools, prioritizing direct method aliases."""
        return self.about.__doc__

    def code_explanation(self):
        """
        The definitive guide to the BasePlugin API, demonstrating best practices:

        1.  **Direct Aliases**: Uses methods like `self.notify_send` and
            `self.get_cache_path` directly, avoiding explicit helper access.
        2.  **Concurrency**: Utilizes `self.run_in_thread` (for blocking I/O) and
            `self.run_in_async_task` (for IPC queries), ensuring a responsive panel.
        3.  **GTK Safety**: Leverages `self.schedule_in_gtk_thread` and
            `self.update_widget_safely` to ensure all UI updates from background
            tasks are executed safely on the main GTK thread.
        4.  **Core Tools**: Demonstrates configuration (`self.get_config`,
            `self.update_config`), shell execution (`self.cmd.run`), and
            Wayfire IPC communication (`self.ipc`).
        """
        return self.code_explanation.__doc__
