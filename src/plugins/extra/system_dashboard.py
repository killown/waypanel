import os
import subprocess
import sys
from subprocess import Popen, check_output
import psutil
from gi.repository import Gtk
from src.tools.control_center import ControlCenter
from src.plugins.core._base import BasePlugin


ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 999
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        system = SystemDashboard(panel_instance)
        system.create_menu_popover_system()
        return system


class SystemDashboard(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_dashboard = None

    def message(self, msg):
        dialog = Gtk.MessageDialog(
            transient_for=None,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text=msg,
        )

        close_btn = Gtk.Button(label="_Close", use_underline=True)
        close_btn.connect("clicked", lambda *_: dialog.close())
        dialog.get_message_area().append(close_btn)  # pyright: ignore
        dialog.show()

    def launch_settings(self):
        app = ControlCenter()
        app.run(None)
        try:
            subprocess.Popen(["waypanel-settings"], start_new_session=True)
        except FileNotFoundError:
            for path in [
                "/usr/local/bin/waypanel-settings",
                "/usr/bin/waypanel-settings",
                f"{os.path.expanduser('~')}/.local/bin/waypanel-settings",
            ]:
                if os.path.exists(path):
                    subprocess.Popen([path], start_new_session=True)
                    break
            else:
                self.logger.info(
                    "Error: waypanel-sett # pyright: ignoreings not found in PATH",
                    file=sys.stderr,
                )

    def get_system_list(self):
        devices = check_output("systemctl devices".split()).decode().strip().split("\n")
        return [" ".join(i.split(" ")[1:]) for i in devices]

    def create_menu_popover_system(self):
        self.menubutton_dashboard = Gtk.Button()
        self.main_widget = (self.menubutton_dashboard, "append")
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        icon_name = self.gtk_helper.set_widget_icon_name(
            "exit-symbolic",
            [
                "exit",
                "gnome-logout-symbolic",
                "application-exit-symbolic",
            ],
        )
        self.menubutton_dashboard.set_icon_name(icon_name)
        self.gtk_helper.add_cursor_effect(self.menubutton_dashboard)
        self.menubutton_dashboard.add_css_class("system-dashboard-button")
        return self.menubutton_dashboard

    def create_popover_system(self, *_):
        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.set_has_arrow(True)
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.connect("notify::visible", self.popover_is_open)
        self.popover_dashboard.set_vexpand(True)
        self.popover_dashboard.set_hexpand(True)
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.stack = Gtk.Stack.new()

        logout_icon = self.gtk_helper.set_widget_icon_name(
            None,
            [
                "system-log-out-symbolic",
                "gnome-logout-symbolic",
                "gnome-logout",
                "xfsm-logout",
            ],
        )
        reboot_icon = self.gtk_helper.set_widget_icon_name(
            None, ["system-reboot-symbolic", "system-reboot"]
        )
        shutdown_icon = self.gtk_helper.set_widget_icon_name(
            None,
            ["gnome-shutdown-symbolic", "system-shutdown-symbolic", "system-shutdown"],
        )
        suspend_icon = self.gtk_helper.set_widget_icon_name(
            None, ["system-suspend-symbolic", "system-suspend"]
        )
        lock_icon = self.gtk_helper.set_widget_icon_name(
            None, ["system-lock-screen-symbolic", "system-lock-screen"]
        )
        exit_icon = self.gtk_helper.set_widget_icon_name(
            None, ["application-exit-symbolic", "application-exit", "exit"]
        )
        restart_icon = self.gtk_helper.set_widget_icon_name(
            None, ["system-restart-symbolic", "gnome-panel-separator"]
        )
        settings_icon = self.gtk_helper.set_widget_icon_name(
            None,
            [
                "settings-configure-symbolic",
                "systemsettings-symbolic",
                "settings",
                "system-settings-symbolic",
                "preferences-activities-symbolic",
                "preferences-system",
            ],
        )

        data_and_categories = {
            ("Logout", "", logout_icon): "",
            ("Reboot", "", reboot_icon): "",
            ("Shutdown", "", shutdown_icon): "",
            ("Suspend", "", suspend_icon): "",
            ("Lock", "", lock_icon): "",
            ("Exit Waypanel", "", exit_icon): "",
            ("Restart Waypanel", "", restart_icon): "",
            ("Settings", "", settings_icon): "",
        }
        done = []
        for data, category in data_and_categories.items():
            if category not in done:
                flowbox = Gtk.FlowBox.new()
                flowbox.props.homogeneous = True
                flowbox.set_valign(Gtk.Align.START)
                flowbox.props.margin_start = 15
                flowbox.props.margin_end = 15
                flowbox.props.margin_top = 15
                flowbox.props.margin_bottom = 15
                flowbox.props.hexpand = True
                flowbox.props.vexpand = True
                flowbox.props.max_children_per_line = 3
                flowbox.props.selection_mode = Gtk.SelectionMode.NONE
                self.stack.add_titled(flowbox, category, category)
                done.append(category)
            else:
                flowbox = self.stack.get_child_by_name(category)

            icon_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

            icon = Gtk.Image.new_from_icon_name(data[2])
            icon.set_icon_size(Gtk.IconSize.LARGE)
            icon_vbox.append(icon)

            name_label = Gtk.Label.new(data[0])
            icon_vbox.append(name_label)

            summary_label = Gtk.Label.new(data[1])
            icon_vbox.append(summary_label)

            button = Gtk.Button.new()
            button.set_has_frame(False)
            if icon_vbox is not None and isinstance(icon_vbox, Gtk.Widget):
                button.set_child(icon_vbox)
            else:
                self.logger.info("Error: Invalid icon_vbox provided")
            flowbox.append(button)  # pyright: ignore
            button.connect("clicked", self.on_action, data[0])
            name_label.add_css_class("system_dash_label")
            summary_label.add_css_class("system_dash_summary")
            self.gtk_helper.add_cursor_effect(button)

        self.main_box.append(self.stack)
        self.popover_dashboard.set_child(self.main_box)
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()
        self.stack.add_css_class("system_dashboard_stack")
        return self.popover_dashboard

    def on_system_clicked(self, device, *_):
        device_id = device.split()[0]
        cmd = "systemctl connect {0}".format(device_id).split()
        Popen(cmd)

        connected_devices = "systemctl info".split()
        try:
            connected_devices = check_output(connected_devices).decode()
        except Exception as e:
            self.log_error(e)
            return

        if device_id in connected_devices:
            cmd = "systemctl disconnect {0}".format(device_id).split()
            Popen(cmd)

    def run_app_from_dashboard(self, x):
        selected_text, filename = x.get_child().MYTEXT
        cmd = "gtk-launch {}".format(filename)
        self.cmd.run(cmd)
        self.popover_dashboard.popdown()  # pyright: ignore

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()
        if self.popover_dashboard and not self.popover_dashboard.is_visible():
            self.popover_dashboard.popup()
        if not self.popover_dashboard:
            self.popover_dashboard = self.create_popover_system()

    def kill_process_by_name(self, name):
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if name in proc.info["name"]:
                    proc.kill()
                    self.logger.info(
                        f"Killed process {proc.info['name']} with PID {proc.info['pid']}"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def run_later(self, command, delay):
        Popen(["bash", "-c", f"sleep {delay} && {command}"])

    def on_action(self, button, action):
        if action == "Exit Waypanel":
            # FIXME: need a better way to exit the panel
            Popen("pkill -f waypanel/main.py".split())
        if action == "Restart Waypanel":
            # FIXME: need a better way to exit the panel
            self.run_later("waypanel &", 0.1)

        if action == "Logout":
            Popen("wayland-logout".split())
        if action == "Shutdown":
            Popen("shutdown -h now".split())
        if action == "Suspend":
            Popen("systemctl suspend".split())
        if action == "Reboot":
            Popen("reboot".split())
        if action == "Lock":
            # FIXME: allow the user set their own cmd in toml
            Popen(
                """swaylock --screenshots --clock --indicator
                     --grace-no-mouse --indicator-radius 99
                     --indicator-thickness 6 --effect-blur 7x5
                     --effect-vignette -1.5:0.5  --ring-color ffffff
                     --key-hl-color 880032 --line-color 00000000
                     --inside-color 00000087 --separator-color 00000000
                     --grace 1 --fade-in 4""".split()
            )
        if action == "Settings":
            self.launch_settings()
            self.popover_dashboard.popdown()  # pyright: ignore

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(  # pyright: ignore
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

    def about(self):
        """A system dashboard providing quick access to common system actions like power management, session control, and settings."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin creates a popover-based user interface for managing system-level actions.
        It provides a single access point for common tasks such as logging out, shutting down, or accessing settings.

        Its core logic is centered on **dynamic UI generation and system command execution**:

        1.  **UI Generation**: It creates a popover that contains a grid of buttons (`Gtk.FlowBox`), where each button represents a system action. It dynamically selects the most suitable icon for each button from a predefined list.
        2.  **System Command Execution**: For each button, it executes a corresponding system command (e.g., `reboot`, `shutdown`, `swaylock`) using `subprocess.Popen`, which allows the plugin to interact with the underlying operating system.
        3.  **External Tool Integration**: It includes a check to verify the existence of an external application (`waypanel-settings`) before attempting to launch it, providing graceful error handling if the dependency is not met.
        4.  **Session Management**: It provides direct commands to manage the user's session, including exiting and restarting the panel itself.
        """
        return self.code_explanation.__doc__
