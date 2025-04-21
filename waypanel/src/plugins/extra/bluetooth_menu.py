import os
from subprocess import Popen, check_output
import toml
import gi
from gi.repository import Adw, Gtk

from waypanel.src.plugins.core._base import BasePlugin


gi.require_version("Gtk", "4.0")

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "systray"
    order = 3
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        bt = BluetoothDashboard(panel_instance)
        bt.create_menu_popover_bluetooth()
        return bt


class BluetoothDashboard(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_dashboard = None
        self.bluetooth_buttons = {}

    def get_bluetooth_list(self):
        devices = check_output("bluetoothctl devices".split()).decode().strip()
        if not devices:
            return
        devices = [" ".join(i.split(" ")[1:]) for i in devices.split("\n")]
        return devices

    def create_menu_popover_bluetooth(self):
        self.menubutton_dashboard = Gtk.Button()
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        bt_icon = "bluetooth"
        bt_icon = (
            self.config.get("panel", {})
            .get("top", {})
            .get("bluetooth_icon", "bluetooth")
        )
        self.menubutton_dashboard.set_icon_name(bt_icon)
        self.main_widget = (self.menubutton_dashboard, "append")
        return self.menubutton_dashboard

    def CreateGesture(self, widget, mouse_button, arg):
        gesture = Gtk.GestureClick.new()
        gesture.connect("released", lambda *_: self.on_bluetooth_clicked(arg))
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        return widget

    def create_popover_bluetooth(self, *_):
        # FIXME: need to add nothing paired to the popup in case there is no devices
        devices = self.get_bluetooth_list()
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
        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        connected_devices = "bluetoothctl info".split()
        try:
            connected_devices = check_output(connected_devices).decode()
        except Exception as e:
            print(e)

        for device in devices:
            bluetooth_button = Adw.ButtonContent()
            device_id = device.split()[0]
            device_name = " ".join(device.split()[1:])
            self.bluetooth_buttons[device_name] = device_id
            bluetooth_button.set_label(device_name)
            if device_id in connected_devices:
                bluetooth_button.set_icon_name("blueberry-tray")
            else:
                bluetooth_button.set_icon_name("blueberry-tray-disabled")
            gesture = Gtk.GestureClick.new()
            gesture.connect("released", self.on_bluetooth_clicked)
            gesture.set_button(1)
            bluetooth_button.add_controller(gesture)
            box.append(bluetooth_button)
            bluetooth_button.add_css_class("bluetooth-dashboard-buttons")

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
            self.popover_dashboard = self.create_popover_bluetooth()

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar
