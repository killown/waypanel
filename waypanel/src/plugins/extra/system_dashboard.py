import os
import subprocess
import sys
from importlib.util import find_spec
from subprocess import Popen, check_output
import psutil
from gi.repository import Gtk

from waypanel.src.plugins.core._base import BasePlugin


# set to False or remove the plugin file to disable it
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
        # Create a message dialog
        dialog = Gtk.MessageDialog(
            transient_for=None,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,  # We'll add our own button
            text=msg,
        )

        # Add a custom close button
        close_btn = Gtk.Button(label="_Close", use_underline=True)
        close_btn.connect("clicked", lambda *_: dialog.close())
        dialog.get_message_area().append(close_btn)
        dialog.show()

    def is_settings_installed(self):
        """Check if waypanel-settings is installed"""
        if find_spec("waypanel_settings") is not None:
            return True
        try:
            subprocess.run(
                ["waypanel-settings", "--version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            msg = """Error: waypanel-settings is not installed"
                    Install it with:
                          git clone https://github.com/killown/waypanel-settings
                          cd waypanel-settings && pip install -e ."""
            self.message(msg)
            return False

    def launch_settings(self):
        try:
            # Try direct execution first
            subprocess.Popen(["waypanel-settings"], start_new_session=True)
        except FileNotFoundError:
            # Fallback to absolute path lookup
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
                    "Error: waypanel-settings not found in PATH", file=sys.stderr
                )

    def get_system_list(self):
        devices = check_output("systemctl devices".split()).decode().strip().split("\n")
        return [" ".join(i.split(" ")[1:]) for i in devices]

    def create_menu_popover_system(self):
        self.menubutton_dashboard = Gtk.Button()
        self.main_widget = (self.menubutton_dashboard, "append")
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        system_icon = "system-shutdown"
        system_icon = (
            self.config.get("panel", {})
            .get("top", {})
            .get("system_icon", "system-shutdown")
        )
        self.menubutton_dashboard.set_icon_name(system_icon)
        return self.menubutton_dashboard

    def create_popover_system(self, *_):
        # Create a popover
        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.set_has_arrow(True)
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.connect("notify::visible", self.popover_is_open)
        # Set width and height of the popover dashboard
        self.popover_dashboard.set_vexpand(True)
        self.popover_dashboard.set_hexpand(True)
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.stack = Gtk.Stack.new()

        data_and_categories = {
            ("Logout", "", "gnome-logout-symbolic"): "",
            ("Reboot", "", "system-reboot-symbolic"): "",
            ("Shutdown", "", "gnome-shutdown-symbolic"): "",
            ("Lock", "", "system-lock-screen-symbolic"): "",
            ("Turn Off Monitors", "", "display-symbolic"): "",
            ("Exit Waypanel", "", "display-symbolic"): "",
            ("Restart Waypanel", "", "display-symbolic"): "",
            ("Settings", "", "preferences-activities-symbolic"): "",
        }
        done = []
        for data, category in data_and_categories.items():
            if category not in done:  # if flowbox not exist in stack
                flowbox = Gtk.FlowBox.new()
                flowbox.props.homogeneous = True
                flowbox.set_valign(Gtk.Align.START)  # top to bottom
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
            flowbox.append(button)
            button.connect("clicked", self.on_action, data[0])
            name_label.add_css_class("system_dash_label")
            summary_label.add_css_class("system_dash_summary")

        self.main_box.append(self.stack)

        # Set the box as the child of the popover
        self.popover_dashboard.set_child(self.main_box)

        # Set the parent widget of the popover and display it
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()
        self.stack.add_css_class("system_dashboard_stack")
        return self.popover_dashboard

    def on_system_clicked(self, device, *_):
        device_id = device.split()[0]
        cmd = "systemctl connect {0}".format(device_id).split()
        Popen(cmd)

        # this part is for disconnect if the device is already connected
        # so the button will toggle connect/disconnect
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
        self.utils.run_app(cmd)
        self.popover_dashboard.popdown()

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()
        if self.popover_dashboard and not self.popover_dashboard.is_visible():
            self.popover_dashboard.popup()
        if not self.popover_dashboard:
            self.popover_dashboard = self.create_popover_system()

    def kill_process_by_name(self, name):
        # Iterate over all running processes
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                # Check if the process name matches
                if name in proc.info["name"]:
                    proc.kill()
                    self.logger.info(
                        f"Killed process {proc.info['name']} with PID {proc.info['pid']}"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def run_later(self, command, delay):
        # Schedule the command to run after `delay` seconds
        Popen(["bash", "-c", f"sleep {delay} && {command}"])

    def on_action(self, button, action):
        if action == "Exit Waypanel":
            # FIXME: need a better way to exit the panel
            self.kill_process_by_name("waypanel")
        if action == "Restart Waypanel":
            # FIXME: need a better way to exit the panel
            self.run_later("/home/neo/.local/bin/waypanel&", 0.4)
            self.kill_process_by_name("waypanel")

        if action == "Logout":
            Popen("wayland-logout".split())
        if action == "Shutdown":
            Popen("shutdown -h now".split())
        if action == "Reboot":
            Popen("reboot".split())
        if action == "Turn Off Monitors":
            Popen("wayctl --dpms off_all".split())
        if action == "Lock":
            # FIXME: allow the user set their own cmd in toml
            Popen(
                """swaylock --screenshots --clock --indicator
                    --grace-no-mouse --indicator-radius 100
                    --indicator-thickness 7 --effect-blur 7x5
                    --effect-vignette 0.5:0.5  --ring-color ffffff
                    --key-hl-color 880033 --line-color 00000000
                    --inside-color 00000088 --separator-color 00000000
                    --grace 2 --fade-in 4""".split()
            )
        if action == "Settings":
            if self.is_settings_installed():
                self.launch_settings()
                self.popover_dashboard.popdown()

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar
