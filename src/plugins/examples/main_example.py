def get_plugin_metadata(panel_instance):
    position = panel_instance.get_config(
        ["example_base_plugin", "placement", "position"], "top-panel-center"
    )
    order = panel_instance.get_config(["example_base_plugin", "placement", "order"], 1)
    priority = panel_instance.get_config(
        ["example_base_plugin", "placement", "priority"], 1
    )

    return {
        "enabled": True,
        "container": position,
        "index": order,
        "priority": priority,
        "deps": ["top_panel", "event_manager"],
    }


def get_plugin_class():
    import time
    from concurrent.futures import Future
    from typing import Any, Optional
    from src.plugins.core._base import BasePlugin

    class ComprehensiveBaseExample(BasePlugin):
        def __init__(self, panel_instance: Any):
            super().__init__(panel_instance)

            self.popover: Optional[self.gtk.Popover] = None

            self.main_button = self.gtk.Button(label="API Demo")

            icon_name = self.gtk_helper.icon_exist(
                "system-run-symbolic", ["fallback_icon_name_1", "fallback_icon_name_2"]
            )
            button = self.gtk.Button()
            icon_name = self.gtk_helper.icon_exist(
                "data-information", ["fallback_icon_name_1", "fallback_icon_name_2"]
            )
            button.set_icon_name(icon_name)

            self.main_button.set_child(button)
            self.main_button.set_tooltip_text("BasePlugin Comprehensive Demo")

            self.main_widget = (self.main_button, "append")

            self.thread_label = self.gtk.Label(label="Thread Status: Ready")

            self.logger.info("ComprehensiveBaseExample initialized successfully.")

        async def on_start(self):
            self.logger.info("Lifecycle: ComprehensiveBaseExample is fully started.")
            self.setup_ui()
            self.timeout_id = self.glib.timeout_add_seconds(
                30, self._demo_timeout_check
            )

        def setup_ui(self):
            self.popover = self.gtk.Popover.new()
            self.popover.set_parent(self.main_button)
            vbox = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL,
                spacing=10,
                margin_start=15,
                margin_end=15,
                margin_top=15,
                margin_bottom=15,
            )

            title = self.gtk.Label(label="<b>BasePlugin API Demos</b>", use_markup=True)
            vbox.append(title)
            vbox.append(self.gtk.Separator())

            btn_thread = self.gtk.Button(label="Run Blocking Task (3s delay)")
            btn_thread.connect("clicked", self._demo_run_thread)
            vbox.append(btn_thread)
            vbox.append(self.thread_label)

            btn_async = self.gtk.Button(label="Run Async IPC Query")
            btn_async.connect("clicked", self._demo_run_async)
            vbox.append(btn_async)

            vbox.append(self.gtk.Separator())

            btn_config = self.gtk.Button(label="Toggle & Save Config Setting")
            btn_config.connect("clicked", self._demo_update_config)
            vbox.append(btn_config)

            btn_cmd = self.gtk.Button(label="Run Shell Command & Use Path Helper")
            btn_cmd.connect("clicked", self._demo_cmd_and_helpers)
            vbox.append(btn_cmd)

            btn_panel_access = self.gtk.Button(label="Access Panel/Plugin Properties")
            btn_panel_access.connect("clicked", self._demo_panel_access)
            vbox.append(btn_panel_access)

            btn_layer_shell = self.gtk.Button(label="Layer Shell Helper Demo")
            btn_layer_shell.connect("clicked", self._demo_layer_shell_helpers)
            vbox.append(btn_layer_shell)

            self.popover.set_child(vbox)
            self.main_button.connect("clicked", lambda w: self.popover.popup())

            self.add_cursor_effect(self.main_button)

        def _blocking_task(self, delay: int) -> str:
            self.logger.info(f"Thread: Starting blocking task for {delay} seconds...")
            time.sleep(delay)
            return f"Task finished after {delay} seconds."

        def _thread_finished_callback(self, future: Future):
            if future.exception():
                self.update_widget_safely(
                    self.thread_label,
                    "set_label",
                    f"Thread Status: Error! {future.exception()}",
                )
                self.logger.exception("Error in background thread.")
                return

            result_message = future.result()
            self.update_widget_safely(
                self.thread_label,
                "set_label",
                f"Thread Status: {result_message}",
            )
            self.logger.info(f"Thread: Task completed with result: {result_message}")

        def _demo_run_thread(self, button: self.gtk.Button):
            if self.popover:
                self.popover.popdown()
            self.update_widget_safely(
                self.thread_label,
                "set_label",
                "Thread Status: Running...",
            )

            future = self.run_in_thread(self._blocking_task, 3)
            future.add_done_callback(
                lambda f: self.schedule_in_gtk_thread(self._thread_finished_callback, f)
            )

        async def _async_ipc_query(self):
            self.logger.info("Async: Querying Wayfire outputs...")

            outputs = await self.ipc.get_outputs()

            if outputs:
                first_output_valid = self.is_view_valid(outputs[0])
                return (
                    f"IPC Success: Found {len(outputs)} outputs. "
                    f"First view valid: {first_output_valid}"
                )
            else:
                return "IPC Failure: No outputs found."

        def _async_finished_callback(self, result: str):
            self.notify_send("Async IPC Done", result, "dialog-information-symbolic")
            if self.popover:
                self.popover.popdown()

        def _demo_run_async(self, button: self.gtk.Button):
            if self.popover:
                self.popover.popdown()
            self.run_in_async_task(
                self._async_ipc_query(), self._async_finished_callback
            )

        def _demo_update_config(self, button: self.gtk.Button):
            current_value = self.get_config(
                ["example_base_plugin", "demo_setting"], True
            )
            new_value = not current_value

            success = self.update_config(
                ["example_base_plugin", "demo_setting"], new_value
            )

            if success:
                self.notify_send(
                    "Config Saved",
                    f"demo_setting toggled to: {new_value}. Config file updated.",
                    "preferences-system-symbolic",
                )
                self.logger.info(
                    f"Config updated successfully: demo_setting = {new_value}"
                )
            else:
                self.logger.error("Failed to update config.")

            if self.popover:
                self.popover.popdown()

        def _demo_cmd_and_helpers(self, button: self.gtk.Button):
            self.cmd.run(
                "play -v 0.5 --no-show-progress "
                "/usr/share/sounds/freedesktop/stereo/complete.oga || true"
            )

            cache_path = self.get_cache_path()

            is_path_string = self.validate_string(cache_path)

            self.notify_send(
                "Helper Tools Demo",
                f"Cache Path: {cache_path}. Validated as string: {is_path_string}",
                "folder-symbolic",
            )
            self.logger.info(f"Cache Path: {cache_path}. Command run successfully.")
            if self.popover:
                self.popover.popdown()

        def _demo_panel_access(self, button: self.gtk.Button):
            if self.popover:
                self.popover.popdown()

            top_panel_present = self.top_panel is not None
            num_plugins = len(self.plugins)
            plugin_names = ", ".join(self.plugins.keys())

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

        def _demo_layer_shell_helpers(self, button: self.gtk.Button):
            if self.popover:
                self.popover.popdown()

            self.notify_send(
                "Layer Shell Helper References",
                f"LayerShell reference: {self.layer_shell.__name__}\n"
                f"Exclusive setter reference: {self.set_layer_pos_exclusive.__name__}\n"
                f"Exclusive unset reference: {self.unset_layer_pos_exclusive.__name__}",
                "input-tablet-symbolic",
            )
            self.logger.info("Successfully accessed Layer Shell helper properties.")

        def _demo_timeout_check(self) -> bool:
            self.logger.debug("GLib Timeout: Running recurring check.")
            self.notify_send(
                "Recurring Task",
                "GLib Timeout check ran in GTK thread.",
                "system-run-symbolic",
            )
            return True

        def on_stop(self):
            if hasattr(self, "timeout_id") and self.timeout_id:
                self.glib.source_remove(self.timeout_id)

            self.logger.info(
                "Lifecycle: ComprehensiveBaseExample is stopping and cleaning up."
            )

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

    return ComprehensiveBaseExample
