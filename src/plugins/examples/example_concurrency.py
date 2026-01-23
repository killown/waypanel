def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.concurrency_example"
    default_container = "top-panel-right"
    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Concurrency Master",
        "version": "1.0.0",
        "enabled": True,
        "container": container,
        # CRITICAL: Always define dependencies if the current plugin requires certain plugin to be loaded first
        # WARNING: Missing dependencies can cause plugins to fail loading.
        "deps": ["top_panel"],
        "description": "Master guide for run_in_thread, run_in_async_task, and run_cmd.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class ConcurrencyMaster(BasePlugin):
        def __init__(self, panel_instance):
            """
            CONSTRUCTOR: Always initialize the main_widget here.
            """
            super().__init__(panel_instance)
            self.button = self.gtk.Button(label="Launch Tasks")
            self.main_widget = (self.button, "append")

        def on_enable(self):
            """
            LIFECYCLE: Logic entry.
            """
            self.button.connect("clicked", self._on_launch_clicked)
            self.add_cursor_effect(self.button)
            self.logger.info("Concurrency Master ready.")

        def _on_launch_clicked(self, widget):
            # self.run_cmd: Execute shell commands in a background thread.
            # Verified in BasePlugin to use CommandRunner.
            self.run_cmd("notify-send 'Waypanel' 'Starting background operations...'")

            # self.run_in_thread: Execute a blocking function in a separate thread.
            # Signature: (function, *args)
            self.run_in_thread(self._heavy_computation, "Background Thread Data")

            # self.run_in_async_task: Execute an asynchronous coroutine.
            # This is tracked by the ConcurrencyHelper for safe cleanup on disable.
            self.run_in_async_task(self._async_operation())

        def _heavy_computation(self, data):
            """
            This runs in a background thread. Never update UI directly here.
            """
            self.logger.info(f"Computing: {data}")
            self.time.sleep(2)

            # self.schedule_in_gtk_thread: Safe UI updates from a background thread.
            # Signature: (callback, *args)
            self.schedule_in_gtk_thread(self._update_ui_label, "Computation Finished")

        async def _async_operation(self):
            """
            This runs in the global asyncio event loop.
            """
            self.logger.info("Async task started.")
            await self.asyncio.sleep(1)
            self.logger.info("Async task completed.")

            # Using notify_send to signal completion
            self.notify_send(
                title="Async Success",
                message="Background coroutine finished execution.",
                icon="org.gnome.Settings-system-symbolic",
            )

        def _update_ui_label(self, text):
            """
            This callback is safely executed on the main GTK thread.
            """
            self.button.set_label(text)
            self.glib.timeout_add_seconds(
                3, lambda: self.button.set_label("Launch Tasks")
            )

        def on_disable(self):
            """
            LIFECYCLE: Automatic cleanup is handled by BasePlugin.disable().
            Active threads and async tasks are cancelled before this hook is called.
            """
            self.logger.info("Concurrency Master disabled and tasks cleaned up.")

    return ConcurrencyMaster
