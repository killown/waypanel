import os
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Adw
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen, check_output
from ..core.utils import Utils


class BluetoothDashboard(Adw.Application):
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
        self.bluetooth_buttons = {}

    def get_bluetooth_list(self):
        devices = (
            check_output("bluetoothctl devices".split()).decode().strip()
        )
        if not devices:
            return
        devices = [" ".join(i.split(" ")[1:]) for i in devices.split("\n")]
        print(devices)
        return devices

    def create_menu_popover_bluetooth(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        self.menubutton_dashboard = Gtk.Button()
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        self.menubutton_dashboard.set_icon_name("preferences-bluetooth-symbolic")
        return self.menubutton_dashboard

    def CreateGesture(self, widget, mouse_button, arg):
        gesture = Gtk.GestureClick.new()
        gesture.connect("released", lambda *_: self.on_bluetooth_clicked(arg))
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        return widget

    def create_popover_bluetooth(self, *_):
        #FIXME: need to add nothing paired to the popup in case there is no devices
        devices =  self.get_bluetooth_list()
        if not devices:
            return

        # Create a popover
        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.set_has_arrow(False)
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.connect("notify::visible", self.popover_is_open)

        # Set width and height of the popover dashboard
        # self.popover_dashboard.set_size_request(600, 400)

        # Create a box to hold the elements vertically
        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        connected_devices = "bluetoothctl info".split()
        try:
            connected_devices = check_output(connected_devices).decode()
        except Exception as e:
            print(e)

        for device in devices:
            bluetooth_button = Adw.ButtonContent()
            bluetooth_button.add_css_class("bluetooth-dashboard-buttons")
            device_id = device.split()[0]
            device_name = " ".join(device.split()[1:])
            self.bluetooth_buttons[device_name] = device_id
            bluetooth_button.set_label(device_name)
            if device_id in connected_devices:
                bluetooth_button.set_icon_name("blueberry-tray")
            else:
                bluetooth_button.set_icon_name("blueman-disabled-symbolic")
            gesture = Gtk.GestureClick.new()
            gesture.connect("released", self.on_bluetooth_clicked)
            gesture.set_button(1)
            bluetooth_button.add_controller(gesture)
            box.append(bluetooth_button)

        # Set the box as the child of the popover
        self.popover_dashboard.set_child(box)

        # Set the parent widget of the popover and display it
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()
        return self.popover_dashboard

    def on_bluetooth_clicked(self, gesture, *_):
        button = gesture.get_widget()
        device_name = button.get_label()
        device_id = self.bluetooth_buttons[device_name]
        cmd = "bluetoothctl connect {0}".format(device_id).split()
        Popen(cmd)

        # this part is for disconnect if the device is already connected
        # so the button will toggle connect/disconnect
        connected_devices = "bluetoothctl info".split()
        try:
            connected_devices = check_output(connected_devices).decode()
        except Exception as e:
            print(e)
            return

        if device_id in connected_devices:
            cmd = "bluetoothctl disconnect {0}".format(device_id).split()
            Popen(cmd)

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()
        if self.popover_dashboard and not self.popover_dashboard.is_visible():
            self.popover_dashboard.popup()
        if not self.popover_dashboard:
            self.popover_dashboard = self.create_popover_bluetooth(self.app)

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar
