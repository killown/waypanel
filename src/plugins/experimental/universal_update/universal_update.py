def get_plugin_metadata(panel):
    import shutil

    bins = ["pacman", "dnf", "apt", "zypper", "xbps-install", "apk", "flatpak"]
    ENABLE = any(shutil.which(b) for b in bins)

    id = "org.waypanel.plugin.universal_update"
    default_container = "top-panel-center"
    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Universal Update",
        "version": "2.5.0",
        "enabled": ENABLE,
        "index": 3,
        "container": container,
        "deps": ["top_panel"],
        "description": "Universal Linux update manager with per-backend custom commands.",
    }


def get_plugin_class():
    import shutil
    from src.plugins.core._base import BasePlugin
    from ._manager import get_manager

    class UniversalUpdate(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

            custom_cmds = {
                "pacman": self.get_plugin_setting_add_hint(
                    ["commands", "pacman"], "", "Custom command for Pacman."
                ),
                "dnf": self.get_plugin_setting_add_hint(
                    ["commands", "dnf"], "", "Custom command for DNF."
                ),
                "apt": self.get_plugin_setting_add_hint(
                    ["commands", "apt"], "", "Custom command for APT."
                ),
                "zypper": self.get_plugin_setting_add_hint(
                    ["commands", "zypper"], "", "Custom command for Zypper."
                ),
                "xbps": self.get_plugin_setting_add_hint(
                    ["commands", "xbps"], "", "Custom command for XBPS."
                ),
                "apk": self.get_plugin_setting_add_hint(
                    ["commands", "apk"], "", "Custom command for APK."
                ),
                "flatpak": self.get_plugin_setting_add_hint(
                    ["commands", "flatpak"], "", "Custom command for Flatpak."
                ),
            }

            UpdateManager = get_manager()
            self.manager = UpdateManager(
                config={k: v for k, v in custom_cmds.items() if v}
            )

            self.check_interval_seconds = self.get_plugin_setting_add_hint(
                ["timing", "check_interval_seconds"], 3600, "Background check interval."
            )
            self.check_timeout_seconds = self.get_plugin_setting_add_hint(
                ["timing", "check_timeout_seconds"], 20, "Command timeout per backend."
            )
            self.terminal_monitor_interval_seconds = self.get_plugin_setting_add_hint(
                ["timing", "terminal_monitor_interval_seconds"],
                2,
                "PID check interval.",
            )
            self.update_command = self.get_plugin_setting_add_hint(
                ["actions", "update_command"],
                self.manager.get_combined_command(),
                "Combined update command for all detected managers.",
            )
            self.terminal_preference = self.get_plugin_setting_add_hint(
                ["actions", "terminal_preference"],
                ["kitty", "alacritty", "terminator", "xterm", "gnome-terminal"],
                "Preferred terminals.",
            )

            self.menu_button = self.gtk.MenuButton()
            icon_name = self.icon_exist(
                "software-update-available-symbolic", ["software-update-available"]
            )
            self.menu_button.set_icon_name(icon_name)
            self.menu_button.add_css_class("universal-update-button")
            self.gtk_helper.add_cursor_effect(self.menu_button)

            self.main_widget = (self.menu_button, "append")
            self.update_count = 0
            self.is_checking = False
            self.terminal_pid = None
            self.count_label = None

        def on_start(self):
            self.run_in_thread(self._setup_popover)
            self.run_in_async_task(self._manual_refresh())
            self.glib.timeout_add_seconds(
                self.check_interval_seconds, self._check_updates_periodically
            )

        def _setup_popover(self):
            self.popover_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=8
            )
            self.popover = self.create_popover(
                parent_widget=self.menu_button,
                css_class="universal-update-popover",
                visible_handler=self._on_popover_visibility_changed,
            )
            self.popover.set_child(self.popover_box)
            self.menu_button.set_popover(self.popover)

            self.count_label = self.gtk.Label(label="Initializing...")
            self.popover_box.append(self.count_label)

            refresh_btn = self.gtk.Button(label="Refresh")
            refresh_btn.connect(
                "clicked", lambda _: self.run_in_async_task(self._manual_refresh())
            )
            self.popover_box.append(refresh_btn)

            update_btn = self.gtk.Button(label="Update Now")
            update_btn.connect("clicked", self._launch_terminal)
            self.popover_box.append(update_btn)

        def _on_popover_visibility_changed(self, popover, _):
            if popover.get_property("visible"):
                self.run_in_async_task(self._manual_refresh())

        async def _manual_refresh(self):
            if self.is_checking:
                return
            self.is_checking = True
            self.schedule_in_gtk_thread(
                self.count_label.set_label, "Polling backends..."
            )
            await self._check_updates()
            self.is_checking = False

        def _check_updates_periodically(self):
            if not self.is_checking:
                self.run_in_async_task(self._manual_refresh())
            return True

        async def _check_updates(self):
            try:
                count = await self.manager.check_all(
                    self.asyncio, self.subprocess, self.check_timeout_seconds
                )
                self.update_count = count
                self.schedule_in_gtk_thread(self._update_ui, count)
            except Exception as e:
                self.logger.exception(f"Manager check failed: {e}")
                self.schedule_in_gtk_thread(self._update_ui, -1)

        def _update_ui(self, count):
            if count == -1:
                self.count_label.set_label("Backend Error")
                self.menu_button.show()
            elif count == 0:
                self.count_label.set_label("System up to date")
                self.menu_button.hide()
            else:
                self.count_label.set_label(f"{count} updates available")
                self.menu_button.show()

        def _launch_terminal(self, _):
            terminal = next(
                (t for t in self.terminal_preference if shutil.which(t)), None
            )
            if not terminal:
                return

            wrapped_command = f"sh -c \"{self.update_command}; echo; echo 'Task finished. Press Enter to exit...'; read\""
            cmd = [terminal, "-e", "sh", "-c", wrapped_command]

            try:
                proc = self.subprocess.Popen(cmd)
                self.terminal_pid = proc.pid
                self.glib.timeout_add_seconds(
                    self.terminal_monitor_interval_seconds, self._monitor_terminal
                )
            except Exception as e:
                self.logger.exception(f"Launch error: {e}")
            self.popover.popdown()

        def _monitor_terminal(self):
            if not self.terminal_pid:
                return False
            try:
                res = self.subprocess.run(
                    ["ps", "-p", str(self.terminal_pid)], capture_output=True
                )
                if res.returncode != 0:
                    self.terminal_pid = None
                    self.run_in_async_task(self._manual_refresh())
                    return False
                return True
            except Exception:
                return False

    return UniversalUpdate
