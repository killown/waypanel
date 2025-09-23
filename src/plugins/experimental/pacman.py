import shutil
import asyncio
import subprocess

from gi.repository import Gtk, GLib
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop

ENABLE_PLUGIN = bool(shutil.which("pacman"))
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    return "top-panel-center", 99


def initialize_plugin(panel_instance):
    if not ENABLE_PLUGIN:
        panel_instance.logger.info("update_checker: pacman not found, plugin disabled")
        return None
    return UpdateCheckerPlugin(panel_instance)


class UpdateCheckerPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.button = Gtk.Button(label="0")
        self.button.add_css_class("update-checker-button")
        self.popover = Gtk.Popover()
        self.menu_button = Gtk.MenuButton()
        self.menu_button.set_popover(self.popover)
        self.popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.popover.set_child(self.popover_box)

        self.button.connect("clicked", self._on_button_click)
        self.menu_button.set_icon_name("software-update-available-symbolic")
        self.gtk_helper.add_cursor_effect(self.menu_button)

        # Main widget to be added to the panel
        self.main_widget = (self.menu_button, "append")

        self.update_count = 0
        self.is_checking = False
        self.terminal_pid = None

        self._setup_popover()
        self._update_ui(0)  # Start hidden

        # Initial refresh + hourly checks
        self.logger.info("Scheduling initial update check with asyncio.")
        global_loop.create_task(self._manual_refresh())
        GLib.timeout_add_seconds(3600, self._check_updates_periodically)

    def _setup_popover(self):
        label = Gtk.Label(label="System Updates")
        label.add_css_class("heading")
        self.popover_box.append(label)

        self.count_label = Gtk.Label(label="No updates found")
        self.popover_box.append(self.count_label)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect(
            "clicked", lambda x: global_loop.create_task(self._manual_refresh())
        )
        self.gtk_helper.add_cursor_effect(refresh_btn)
        self.popover_box.append(refresh_btn)

        update_btn = Gtk.Button(label="Update Now")
        update_btn.connect("clicked", self._launch_terminal)
        self.popover_box.append(update_btn)
        self.gtk_helper.add_cursor_effect(update_btn)

        self.popover.connect("notify::visible", self._on_popover_visibility_changed)

    def _on_popover_visibility_changed(self, popover, param):
        if popover.get_property("visible"):
            global_loop.create_task(self._manual_refresh())

    async def _manual_refresh(self, button=None):
        if self.is_checking:
            return

        self.is_checking = True
        self.count_label.set_label("Checking for updates...")

        # Await the async update check
        await self._check_updates()

        self.is_checking = False

    def _check_updates_periodically(self):
        if not self.is_checking:
            global_loop.create_task(self._manual_refresh())
        return True

    async def _check_updates(self):
        """
        Runs the 'checkupdates' command asynchronously.
        """
        proc = None
        try:
            # Use asyncio.create_subprocess_exec for non-blocking I/O
            proc = await asyncio.create_subprocess_exec(
                "checkupdates",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)

            lines = stdout.decode("utf-8").strip().splitlines()
            count = len(lines)
            self.update_count = count
            self._update_ui(count)

        except asyncio.TimeoutError:
            self.logger.warning("Update check timed out - no internet connection?")
            self._update_ui(-1)
        except FileNotFoundError:
            self.logger.warning("checkupdates command not found")
            self._update_ui(-1)
        except Exception as e:
            self.logger.error(f"Failed to check updates: {e}")
            self._update_ui(-1)
        finally:
            if proc and proc.returncode is None:
                proc.kill()

    def _update_ui(self, count):
        if count == -1:
            self.count_label.set_label("Error checking updates")
            self.button.set_label("!")
            self.menu_button.show()
        elif count == 0:
            self.count_label.set_label("System is up to date")
            self.button.set_label("0")
            self.menu_button.hide()
        else:
            self.count_label.set_label(f"{count} updates available")
            self.button.set_label(str(count))
            self.menu_button.show()

    def _on_button_click(self, button):
        GLib.idle_add(self.popover.popup)

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
            # Popen is acceptable here as the user interaction is synchronous
            proc = subprocess.Popen(
                [terminal, "-e", "sudo", "pacman", "-Syu"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
            self.terminal_pid = proc.pid
            self.logger.info(f"Launched terminal with PID: {self.terminal_pid}")

            # Start monitoring terminal process
            GLib.timeout_add_seconds(2, self._monitor_terminal_process)

        except Exception as e:
            self.logger.error(f"Failed to launch terminal: {e}")
            self.terminal_pid = None

    def _monitor_terminal_process(self):
        if not hasattr(self, "terminal_pid") or self.terminal_pid is None:
            return False

        try:
            # Check if process still exists
            proc = subprocess.run(
                ["ps", "-p", str(self.terminal_pid)], capture_output=True
            )
            if proc.returncode != 0:
                self.logger.info("Terminal process ended. Re-checking for updates.")
                self.terminal_pid = None
                global_loop.create_task(self._manual_refresh())
                return False

            return True
        except Exception as e:
            self.logger.error(f"Error monitoring terminal: {e}")
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

        1.  **Dependency and UI Initialization**: The plugin checks for the
            presence of the `pacman` command and disables itself if not found.
            It sets up a `Gtk.MenuButton` on the panel which opens a
            `Gtk.Popover`. This popover contains labels and buttons for
            user interaction. An initial update check is performed, and
            a timer is set to refresh the check hourly.
        2.  **Asynchronous Update Check**: The `_check_updates` method uses
            `asyncio.create_subprocess_exec` to run the `checkupdates`
            command. This is crucial as it prevents the UI from freezing
            while waiting for the command to return. The plugin then counts
            the lines of output to determine the number of available updates
            and updates the UI accordingly.
        3.  **Process and State Management**: When the "Update Now" button
            is clicked, the plugin launches a new terminal process (using
            `kitty` or `alacritty`) to execute `sudo pacman -Syu`. It then
            monitors this process's PID asynchronously. Once the terminal
            process is no longer running, the plugin automatically triggers a
            new update check to reflect the system's new state.
        """
        return self.code_explanation.__doc__
