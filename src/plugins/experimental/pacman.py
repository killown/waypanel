def get_plugin_metadata(_):
    import shutil

    ENABLE_PLUGIN = bool(shutil.which("pacman"))
    about = (
        "A plugin that checks for available system updates on Arch Linux-based "
        "systems using the `checkupdates` command and provides a quick way to "
        "refresh the count or launch a terminal to run the update. "
    )
    return {
        "id": "org.waypanel.plugin.pacman",
        "name": "Pacman Manager",
        "version": "1.0.0",
        "enabled": ENABLE_PLUGIN,
        "index": 3,
        "container": "top-panel-center",
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    import shutil
    from src.plugins.core._base import BasePlugin

    class UpdateCheckerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.check_interval_seconds = self.get_plugin_setting_add_hint(
                ["timing", "check_interval_seconds"],
                3600,
                "The delay (in seconds) between automatic background checks for new updates. (Default: 1 hour)",
            )
            self.check_timeout_seconds = self.get_plugin_setting_add_hint(
                ["timing", "check_timeout_seconds"],
                10,
                "The timeout (in seconds) for the 'checkupdates' command to complete before assuming failure (e.g., no internet connection).",
            )
            self.terminal_monitor_interval_seconds = self.get_plugin_setting_add_hint(
                ["timing", "terminal_monitor_interval_seconds"],
                2,
                "The interval (in seconds) to check if the spawned terminal process (for updating) has finished.",
            )
            self.update_command = self.get_plugin_setting_add_hint(
                ["actions", "update_command"],
                "sudo pacman -Syu",
                "The full command string executed in the terminal when the 'Update Now' button is clicked.",
            )
            self.terminal_preference = self.get_plugin_setting_add_hint(
                ["actions", "terminal_preference"],
                ["kitty", "alacritty", "terminator", "xterm"],
                "A list of preferred terminal emulators to use for launching the update command, in order of preference. Waypanel will use the first one it finds.",
            )
            self.button = self.gtk.Button(label="0")
            self.button.add_css_class("pacman-update-checker-button")
            self.popover = None
            self.popover_box = None
            self.menu_button = self.gtk.MenuButton()
            self.button.connect("clicked", self._on_button_click)
            icon_name = self.icon_exist(
                "software-update-available-symbolic", ["software-update-available"]
            )
            self.menu_button.set_icon_name(icon_name)
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
            self.glib.timeout_add_seconds(
                self.check_interval_seconds, self._check_updates_periodically
            )

        def _setup_popover(self):
            """
            Creates and configures the popover and its contents, utilizing
            self.create_popover to handle instantiation and signal connections.
            """
            self.popover_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=6
            )
            self.popover_box.add_css_class("pacman-box")
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
            label.add_css_class("pacman-heading")
            self.popover_box.append(label)
            self.count_label = self.gtk.Label(label="No updates found")
            self.popover_box.append(self.count_label)
            refresh_btn = self.gtk.Button(label="Refresh")
            refresh_btn.add_css_class("pacman-refresh-button")
            refresh_btn.connect(
                "clicked", lambda x: self.run_in_async_task(self._manual_refresh())
            )
            self.gtk_helper.add_cursor_effect(refresh_btn)
            self.popover_box.append(refresh_btn)
            update_btn = self.gtk.Button(label="Update Now")
            update_btn.add_css_class("pacman-update-button")
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
                stdout, _ = await self.asyncio.wait_for(
                    proc.communicate(), timeout=self.check_timeout_seconds
                )
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
            for preferred_terminal in self.terminal_preference:
                if shutil.which(preferred_terminal):
                    terminal = preferred_terminal
                    break
            if not terminal:
                self.logger.warning(
                    f"No supported terminal emulator found ({', '.join(self.terminal_preference)})"
                )
                return
            command_parts = self.update_command.split()
            try:
                proc = self.subprocess.Popen(
                    [terminal, "-e"] + command_parts,
                    stdout=self.subprocess.PIPE,
                    stderr=self.subprocess.PIPE,
                    stdin=self.subprocess.PIPE,
                )
                self.terminal_pid = proc.pid
                self.logger.info(f"Launched terminal with PID: {self.terminal_pid}")
                self.glib.timeout_add_seconds(
                    self.terminal_monitor_interval_seconds,
                    self._monitor_terminal_process,
                )
            except Exception as e:
                self.logger.exception(f"Failed to launch terminal: {e}")
                self.terminal_pid = None
            self.popover.popdown()

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

        def code_explanation(self):
            """
            This plugin provides a user-friendly interface for managing system
            updates by integrating with Arch Linux's package management tools.
            Its core logic revolves around **asynchronous process management,
            UI integration, and dependency handling**:
            1. **Configuration-Driven Behavior**: All timing (check and timeout) and execution (terminal and command) parameters are read from configuration on initialization, making the plugin highly flexible.
            2. **Asynchronous Update Check**: The `_check_updates` method uses `self.asyncio.create_subprocess_exec` and the configurable `check_timeout_seconds` to run `checkupdates` non-blockingly.
            3. **GTK Thread Safety**: UI updates are safely marshaled to the main thread using `self.schedule_in_gtk_thread()`.
            4. **Process Management**: When updating, the plugin selects a terminal from the configurable `terminal_preference` list, executes the `update_command`, and uses a recurring `self.glib.timeout_add_seconds` (with configurable interval) to monitor the terminal process's PID. Once the terminal closes, a new update check is triggered.
            """
            return self.code_explanation.__doc__

    return UpdateCheckerPlugin
