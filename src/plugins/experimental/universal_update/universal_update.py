def get_plugin_metadata(panel):
    """Retrieves the metadata for the Universal Update plugin.

    Args:
        panel: The panel instance used to resolve plugin configuration and containers.

    Returns:
        dict: A dictionary containing plugin identification, requirements, and metadata.
    """
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
        "index": 11,
        "container": container,
        "deps": ["css_generator", "status_notifier"],
        "description": "Universal Linux update manager with per-backend custom commands.",
    }


def get_plugin_class():
    """Returns the UniversalUpdate plugin class definition with logic for background updates.

    Returns:
        type: The UniversalUpdate class inheriting from BasePlugin.
    """
    import shutil
    from src.plugins.core._base import BasePlugin
    from ._manager import get_manager

    class UniversalUpdate(BasePlugin):
        """Plugin for orchestrating system updates across multiple Linux package managers."""

        def __init__(self, panel_instance):
            """Initializes the UniversalUpdate plugin, registering settings and UI components.

            Args:
                panel_instance: The main panel instance this plugin is attached to.
            """
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
            self.trigger_button = self.gtk.Button()
            main_icon = self.get_plugin_setting_add_hint(
                ["main_icon"],
                "software-update-available-symbolic",
                "universal-update-button icon",
            )
            self.trigger_button.add_css_class("universal-update-button")
            self.trigger_button.set_icon_name(main_icon)
            self.gtk_helper.add_cursor_effect(self.trigger_button)
            self.trigger_button.connect("clicked", self._on_button_clicked)

            self.plugins["status_notifier"].tray_box.append(self.trigger_button)
            self.update_count = 0
            self.is_checking = False
            self.terminal_pid = None
            self.count_label = None

        def on_start(self):
            """Initializes the UI popover and starts the periodic update checking loop."""
            self._setup_popover()
            self.run_in_async_task(self._manual_refresh())
            self.glib.timeout_add_seconds(
                self.check_interval_seconds, self._check_updates_periodically
            )
            self.plugins["css_generator"].install_css("universal-update.css")

        def _setup_popover(self):
            """Constructs the GTK popover menu containing status info and action buttons."""
            self.popover_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=8
            )
            self.popover = self.create_popover(
                parent_widget=self.trigger_button,
                css_class="universal-update-popover",
                visible_handler=self._on_popover_visibility_changed,
            )
            self.popover.set_child(self.popover_box)
            self.count_label = self.gtk.Label(label="Initializing...")
            self.popover_box.append(self.count_label)
            refresh_btn = self.gtk.Button(label="Refresh")
            refresh_btn.connect(
                "clicked", lambda _: self.run_in_async_task(self._manual_refresh())
            )
            self.popover_box.append(refresh_btn)
            update_btn = self.gtk.Button(label="Update Now")
            update_btn.add_css_class("universal-update-now")
            update_btn.connect("clicked", self._launch_terminal)
            self.popover_box.append(update_btn)

        def _on_button_clicked(self, _):
            """Toggles the visibility of the update popover when the main button is clicked."""
            if self.popover.get_visible():
                self.popover.popdown()
            else:
                self.popover.popup()

        def _on_popover_visibility_changed(self, popover, _):
            """Triggers a refresh of the update count when the popover becomes visible."""
            if popover.get_property("visible"):
                self.run_in_async_task(self._manual_refresh())

        async def _manual_refresh(self):
            """Performs an asynchronous update check, preventing concurrent polling operations."""
            if self.is_checking:
                return
            self.is_checking = True
            self.schedule_in_gtk_thread(
                self.count_label.set_label,
                "Polling backends...",
            )
            await self._check_updates()
            self.is_checking = False

        def _check_updates_periodically(self):
            """Periodic callback for GLib timeout to trigger background update checks.

            Returns:
                bool: True to keep the timeout active.
            """
            if not self.is_checking:
                self.run_in_async_task(self._manual_refresh())
            return True

        async def _check_updates(self):
            """Queries all available update backends and schedules a UI update with the results."""
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
            """Updates the button visibility and popover label based on the update count.

            Args:
                count (int): Number of updates found, or -1 for error.
            """
            if count == -1:
                self.count_label.set_label("Backend Error")
                self.trigger_button.show()
            elif count == 0:
                self.count_label.set_label("System up to date")
                self.trigger_button.hide()
            else:
                self.count_label.set_label(f"{count} updates available")
                self.trigger_button.show()

        def _launch_terminal(self, _):
            """Spawns the preferred terminal to execute the combined update command string."""
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
            """Monitors the terminal process PID and refreshes status once the process exits.

            Returns:
                bool: True if monitoring should continue, False if process finished.
            """
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
