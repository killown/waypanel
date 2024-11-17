import os
import psutil
from subprocess import Popen
from gi.repository import Gtk, Adw
from subprocess import Popen, check_output
from ..core.utils import Utils


class SystemDashboard(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_dashboard = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()
        self.utils = Utils(application_id="com.github.utils")

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.scripts = os.path.join(self.home, ".config/hypr/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.topbar_dashboard_config = os.path.join(
            self.config_path, "topbar-launcher.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}

    def get_system_list(self):
        devices = check_output("systemctl devices".split()).decode().strip().split("\n")
        return [" ".join(i.split(" ")[1:]) for i in devices]

    def create_menu_popover_system(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        self.menubutton_dashboard = Gtk.Button()
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        self.menubutton_dashboard.set_icon_name("gshutdown-symbolic")
        return self.menubutton_dashboard

    def create_popover_system(self, *_):
        # Create a popover
        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.set_has_arrow(False)
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.connect("notify::visible", self.popover_is_open)
        # Set width and height of the popover dashboard
        self.popover_dashboard.set_size_request(
            400, 440
        )  # Set width to 600 and height to 400

        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.stack = Gtk.Stack.new()
        self.stack.add_css_class("system_dash_box")
        self.stack.add_css_class("system_dash_stack")
        self.stack.props.hexpand = True
        self.stack.props.vexpand = True
        data_and_categories = {
            ("Logout", "", "gnome-logout-symbolic"): "",
            ("Reboot", "", "system-reboot-symbolic"): "",
            ("Shutdown", "", "gnome-shutdown-symbolic"): "",
            ("Lock", "", "system-lock-screen-symbolic"): "",
            ("Turn Off Monitors", "", "display-symbolic"): "",
            ("Exit Waypanel", "", "display-symbolic"): "",
            ("Restart Waypanel", "", "display-symbolic"): "",
        }
        done = []
        for data, category in data_and_categories.items():
            if category not in done:  # if flowbox not exist in stack
                sw = Gtk.ScrolledWindow.new()
                flowbox = Gtk.FlowBox.new()
                sw.set_child(flowbox)
                flowbox.props.homogeneous = True
                flowbox.set_valign(Gtk.Align.START)  # top to bottom
                flowbox.props.margin_start = 20
                flowbox.props.margin_end = 20
                flowbox.props.margin_top = 20
                flowbox.props.margin_bottom = 20
                flowbox.props.hexpand = True
                flowbox.props.vexpand = True
                flowbox.props.max_children_per_line = 4
                flowbox.props.selection_mode = Gtk.SelectionMode.NONE
                self.stack.add_titled(sw, category, category)
                done.append(category)
            else:
                flowbox = self.stack.get_child_by_name(category).get_child().get_child()

            icon_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

            icon = Gtk.Image.new_from_icon_name(data[2])
            icon.set_icon_size(Gtk.IconSize.LARGE)
            icon_vbox.append(icon)

            name_label = Gtk.Label.new(data[0])
            name_label.add_css_class("system_dash_label")
            icon_vbox.append(name_label)

            summary_label = Gtk.Label.new(data[1])
            summary_label.add_css_class("system_dash_summary")
            icon_vbox.append(summary_label)

            button = Gtk.Button.new()
            button.set_has_frame(False)
            button.set_child(icon_vbox)
            flowbox.append(button)
            button.connect("clicked", self.on_action, data[0])

        stack_switcher = Gtk.StackSwitcher.new()
        stack_switcher.props.hexpand = False
        stack_switcher.props.vexpand = False
        stack_switcher.set_stack(self.stack)

        self.main_box.append(stack_switcher)
        self.main_box.append(self.stack)

        # Set the box as the child of the popover
        self.popover_dashboard.set_child(self.main_box)

        # Set the parent widget of the popover and display it
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()

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
            print(e)
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
            self.popover_dashboard = self.create_popover_system(self.app)

    def kill_process_by_name(self, name):
        # Iterate over all running processes
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Check if the process name matches
                if name in proc.info['name']:
                    proc.kill()
                    print(f"Killed process {proc.info['name']} with PID {proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    def run_later(self, command, delay):
        # Schedule the command to run after `delay` seconds
        Popen(['bash', '-c', f'sleep {delay} && {command}'])
        
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

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar
