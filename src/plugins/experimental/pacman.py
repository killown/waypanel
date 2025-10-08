def get_plugin_metadata(_):
    import shutil

    ENABLE_PLUGIN = bool(shutil.which("pacman"))
    return {
        "id": "org.waypanel.plugin.pacman",
        "name": "Pacman Manager",
        "version": "1.0.0",
        "enabled": ENABLE_PLUGIN,
        "index": 3,
        "container": "top-panel-center",
        "deps": ["top_panel"],
    }


def get_plugin_class():
    import shutil
    from src.plugins.core._base import BasePlugin

    class UpdateCheckerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.button = self.gtk.Button(label="0")
            self.button.add_css_class("update-checker-button")
            self.popover = None
            self.popover_box = None
            self.menu_button = self.gtk.MenuButton()
            self.button.connect("clicked", self._on_button_click)
            self.menu_button.set_icon_name("software-update-available-symbolic")
            self.menu_button.add_css_class("update-checker-button")
            self.gtk_helper.add_cursor_effect(self.menu_button)
            self.main_widget = (self.menu_button, "append")
            self.update_count = 0
            self.is_checking = False
            self.terminal_pid = None
            self.count_label = None

        def on_start(self):
            """Hook called when the plugin is initialized. Starts the initial and periodic checks."""
            self.logger.info("Scheduling initial update check with BasePlugin helper.")
            self.run_in_thread(self._setup_popover)
            self.run_in_thread(self._update_ui, 0)
            self.run_in_async_task(self._manual_refresh())
            self.glib.timeout_add_seconds(3600, self._check_updates_periodically)

        def _setup_popover(self):
            """
            Creates and configures the popover and its contents, utilizing
            self.create_popover to handle instantiation and signal connections.
            """
            self.popover_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=6
            )
            self.popover = self.create_popover(
                parent_widget=self.menu_button,
                css_class="update-checker-popover",
                has_arrow=False,
                closed_handler=None,
                visible_handler=self._on_popover_visibility_changed,
            )
            self.popover.set_child(self.popover_box)
            self.menu_button.set_popover(self.popover)
            label = self.gtk.Label(label="System Updates")
            label.add_css_class("heading")
            self.popover_box.append(label)
            self.count_label = self.gtk.Label(label="No updates found")
            self.popover_box.append(self.count_label)
            refresh_btn = self.gtk.Button(label="Refresh")
            refresh_btn.connect(
                "clicked", lambda x: self.run_in_async_task(self._manual_refresh())
            )
            self.gtk_helper.add_cursor_effect(refresh_btn)
            self.popover_box.append(refresh_btn)
            update_btn = self.gtk.Button(label="Update Now")
            update_btn.connect("clicked", self._launch_terminal)
            self.popover_box.append(update_btn)
            self.gtk_helper.add_cursor_effect(update_btn)

        def _on_popover_visibility_changed(self, popover, param):
            if popover.get_property("visible"):
                self.run_in_async_task(self._manual_refresh())

        async def _manual_refresh(self, button=None):
            if self.is_checking:
                return
            self.is_checking = True
            self.schedule_in_gtk_thread(
                self.count_label.set_label,  # pyright: ignore
                "Checking for updates...",
            )
            await self._check_updates()
            self.is_checking = False

        def _check_updates_periodically(self):
            if not self.is_checking:
                self.run_in_async_task(self._manual_refresh())
            return True

        async def _check_updates(self):
            """
            Runs the 'checkupdates' command asynchronously.
            """
            proc = None
            try:
                proc = await self.asyncio.create_subprocess_exec(
                    "checkupdates",
                    stdout=self.subprocess.PIPE,
                    stderr=self.subprocess.DEVNULL,
                )
                stdout, _ = await self.asyncio.wait_for(proc.communicate(), timeout=10)
                lines = stdout.decode("utf-8").strip().splitlines()
                count = len(lines)
                self.update_count = count
                self.schedule_in_gtk_thread(self._update_ui, count)
            except self.asyncio.TimeoutError:
                self.logger.warning("Update check timed out - no internet connection?")
                self.schedule_in_gtk_thread(self._update_ui, -1)
            except FileNotFoundError:
                self.logger.warning("checkupdates command not found")
                self.schedule_in_gtk_thread(self._update_ui, -1)
            except Exception as e:
                self.logger.exception(f"Failed to check updates: {e}")
                self.schedule_in_gtk_thread(self._update_ui, -1)
            finally:
                if proc and proc.returncode is None:
                    proc.kill()

        def _update_ui(self, count):
            """Updates the UI based on the update count. Must run on the GTK thread."""
            if count == -1:
                self.count_label.set_label("Error checking updates")  # pyright: ignore
                self.button.set_label("!")
                self.menu_button.show()
            elif count == 0:
                self.count_label.set_label("System is up to date")  # pyright: ignore
                self.button.set_label("0")
                self.menu_button.hide()
            else:
                self.count_label.set_label(f"{count} updates available")  # pyright: ignore
                self.button.set_label(str(count))
                self.menu_button.show()

        def _on_button_click(self, button):
            self.schedule_in_gtk_thread(self.popover.popup)  # pyright: ignore

        def _launch_terminal(self, button):
            terminal = None
            if shutil.which("kitty"):
                terminal = "kitty"
            elif shutil.which("alacritty"):
                terminal = "alacritty"
            if not terminal:
                self.logger.warning(
                    "No supported terminal emulator found (kitty or alacritty)"
                )
                return
            try:
                proc = self.subprocess.Popen(
                    [terminal, "-e", "sudo", "pacman", "-Syu"],
                    stdout=self.subprocess.PIPE,
                    stderr=self.subprocess.PIPE,
                    stdin=self.subprocess.PIPE,
                )
                self.terminal_pid = proc.pid
                self.logger.info(f"Launched terminal with PID: {self.terminal_pid}")
                self.glib.timeout_add_seconds(2, self._monitor_terminal_process)
            except Exception as e:
                self.logger.exception(f"Failed to launch terminal: {e}")
                self.terminal_pid = None

        def _monitor_terminal_process(self):
            if not hasattr(self, "terminal_pid") or self.terminal_pid is None:
                return False
            try:
                proc = self.subprocess.run(
                    ["ps", "-p", str(self.terminal_pid)], capture_output=True
                )
                if proc.returncode != 0:
                    self.logger.info("Terminal process ended. Re-checking for updates.")
                    self.terminal_pid = None
                    self.run_in_async_task(self._manual_refresh())
                    return False
                return True
            except Exception as e:
                self.logger.exception(f"Error monitoring terminal: {e}")
                self.terminal_pid = None
                return False

        def on_stop(self):
            self.terminal_pid = None

        def about(self):
            """
            A plugin that checks for available system updates on Arch Linux-based
            systems using the `checkupdates` command and provides a quick way to
            refresh the count or launch a terminal to run the update.
            """
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin provides a user-friendly interface for managing system
            updates by integrating with Arch Linux's package management tools.
            Its core logic revolves around **asynchronous process management,
            UI integration, and dependency handling**:
            1. **self.gtk.Popover Refactoring**: The manual creation and signal connection
               for `self.popover` in `__init__` were moved to `_setup_popover` and
               replaced by a call to `self.create_popover`. The result is assigned
               to `self.popover`, and the manual `self.menu_button.set_popover()`
               call is maintained.
            2. **Concurrency Refactoring**: All usage of the old `global_loop.create_task()` has been replaced with the robust `self.run_in_async_task()`. The initial and periodic check scheduling is moved to the `on_start()` lifecycle hook.
            3. **GTK Thread Safety**: The `_update_ui` method, which manipulates GTK widgets, is now called exclusively using `self.schedule_in_gtk_thread()` from the asynchronous `_check_updates` method. This guarantees UI stability by ensuring GTK calls always happen on the main thread.
            4. **Asynchronous Update Check**: The `_check_updates` method continues to use ` self.asyncio.create_subprocess_exec` to run the `checkupdates` command non-blockingly.
            5. **Process and State Management**: When the "Update Now" button is clicked, it launches a terminal process (`sudo pacman -Syu`) and uses `self.glib.timeout_add_seconds` to synchronously monitor the terminal's PID. Once the process is finished, a new update check is automatically triggered via `self.run_in_async_task(self._manual_refresh())`.
            """
            return self.code_explanation.__doc__

    return UpdateCheckerPlugin
