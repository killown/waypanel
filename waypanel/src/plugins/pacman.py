import os
import subprocess
import shutil
from gi.repository import Gtk, GLib
from src.plugins.core._base import BasePlugin


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
        self.menu_button.set_icon_name("update-notifier")

        # Main widget to be added to the panel
        self.main_widget = (self.menu_button, "append")

        self.update_count = 0
        self.is_checking = False

        self._setup_popover()
        self._update_ui(0)  # Start hidden

    def _setup_popover(self):
        label = Gtk.Label(label="System Updates")
        label.add_css_class("heading")
        self.popover_box.append(label)

        self.count_label = Gtk.Label(label="No updates found")
        self.popover_box.append(self.count_label)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self._manual_refresh)
        self.popover_box.append(refresh_btn)

        update_btn = Gtk.Button(label="Update Now")
        update_btn.connect("clicked", self._launch_terminal)
        self.popover_box.append(update_btn)

        # Connect popover open/close events
        self.popover.connect("notify::visible", self._on_popover_visibility_changed)

    def _on_popover_visibility_changed(self, popover, param):
        if popover.get_property("visible"):
            self._manual_refresh(None)

    def _manual_refresh(self, button):
        if self.is_checking:
            return

        self.is_checking = True
        self.count_label.set_label("Checking for updates...")
        GLib.idle_add(self._check_updates)

    def _check_updates(self):
        try:
            result = subprocess.run(
                ["checkupdates"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
            lines = result.stdout.strip().splitlines()
            count = len(lines)
            self.update_count = count
            self._update_ui(count)
        except Exception as e:
            self.logger.error(f"Failed to check updates: {e}")
            self._update_ui(-1)
        finally:
            self.is_checking = False

    def _update_ui(self, count):
        if count == -1:
            self.count_label.set_label("Error checking updates")
            self.button.set_label("!")
            self.menu_button.show()
        elif count == 0:
            self.count_label.set_label("System is up to date")
            self.button.set_label("0")
            self.menu_button.hide()  # Hide icon if no updates
        else:
            self.count_label.set_label(f"{count} updates available")
            self.button.set_label(str(count))
            self.menu_button.show()  # Show icon again if updates exist

    def _on_button_click(self, button):
        self.popover.popup()

    def _launch_terminal(self, button):
        terminal = None
        if shutil.which("kitty"):
            terminal = "kitty"
        elif shutil.which("alacritty"):
            terminal = "alacritty"
        elif shutil.which("gnome-terminal"):
            terminal = "gnome-terminal"
        elif shutil.which("xterm"):
            terminal = "xterm"

        if terminal:
            subprocess.Popen([terminal, "-e", "sudo", "pacman", "-Syu"])
        else:
            self.logger.warning("No terminal emulator found")

    def on_stop(self):
        pass
