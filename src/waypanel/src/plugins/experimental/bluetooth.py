import gi
import asyncio
import subprocess
from gi.repository import Adw, GLib, Gtk, Gdk
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop

gi.require_version("Gtk", "4.0")

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 3
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        bt = BluetoothDashboard(panel_instance)
        global_loop.create_task(bt.create_menu_popover_bluetooth())
        return bt


class BluetoothDashboard(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_dashboard = None
        self.bluetooth_buttons = {}
        self.menubutton_dashboard = Gtk.Button()
        self.utils.add_cursor_effect(self.menubutton_dashboard)
        self.main_widget = (self.menubutton_dashboard, "append")

    async def _get_bluetooth_devices(self):
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                check=False,
            )
            devices = proc.stdout.strip()
            if not devices:
                return []
            device_list = [
                " ".join(device.split()[1:])
                for device in devices.split("\n")
                if "Device" in device
            ]
            return device_list
        except Exception as e:
            self.logger.error(f"Error getting bluetooth devices: {e}")
            return []

    async def _get_connected_devices(self):
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["bluetoothctl", "info"],
                capture_output=True,
                text=True,
                check=False,
            )
            return proc.stdout
        except Exception as e:
            self.logger.info(f"Error checking connected devices: {e}")
            return ""

    async def create_menu_popover_bluetooth(self):
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        icon_name = self.utils.set_widget_icon_name(
            "bluetooth", ["org.gnome.Settings-bluetooth-symbolic", "bluetooth"]
        )
        self.menubutton_dashboard.set_icon_name(icon_name)

    def CreateGesture(self, widget, mouse_button, arg):
        gesture = Gtk.GestureClick.new()
        gesture.connect(
            "released",
            lambda *_: global_loop.create_task(self.on_bluetooth_clicked(arg)),
        )
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        self.utils.add_cursor_effect(widget)
        return widget

    async def _fetch_and_update_bluetooth_info(self):
        devices = await self._get_bluetooth_devices()
        connected_devices_str = await self._get_connected_devices()

        # Schedule the UI update on the main thread
        GLib.idle_add(self._update_popover_buttons, devices, connected_devices_str)

    def _update_popover_buttons(self, devices, connected_devices_str):
        if not self.popover_dashboard:
            return False

        # Correct way to get the Gtk.Box inside the popover
        popover_box = self.popover_dashboard.get_child()

        # Clear existing buttons by iterating directly over the box
        for child in popover_box:
            popover_box.remove(child)

        self.bluetooth_buttons.clear()

        if not devices:
            no_devices_label = Gtk.Label(label="No Bluetooth devices found.")
            popover_box.append(no_devices_label)
        else:
            for device in devices:
                bluetooth_button = Gtk.Box.new(
                    orientation=Gtk.Orientation.HORIZONTAL, spacing=6
                )
                bluetooth_button.add_css_class("bluetooth-dashboard-buttons")

                icon = Gtk.Image()
                bluetooth_button.append(icon)

                label = Gtk.Label()
                bluetooth_button.append(label)

                device_id = device.split()[0]
                device_name = " ".join(device.split()[1:])
                self.bluetooth_buttons[device_name] = device_id
                label.set_label(device_name)

                gesture = Gtk.GestureClick.new()
                gesture.connect("released", self.on_bluetooth_clicked)
                gesture.set_button(1)
                bluetooth_button.add_controller(gesture)

                if device_id in connected_devices_str:
                    icon.set_from_icon_name("blueberry-tray")
                    bluetooth_button.add_css_class(
                        "bluetooth-dashboard-buttons-connected"
                    )
                else:
                    icon.set_from_icon_name("blueberry-tray-disabled")
                    bluetooth_button.remove_css_class(
                        "bluetooth-dashboard-buttons-connected"
                    )

                popover_box.append(bluetooth_button)
        return False

    def create_popover_with_loading_state(self):
        if self.popover_dashboard:
            return

        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.connect("notify::visible", self.popover_is_open)

        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        loading_label = Gtk.Label(label="Loading...")
        box.append(loading_label)

        self.popover_dashboard.set_child(box)
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()

        # Start fetching data in a background task
        global_loop.create_task(self._fetch_and_update_bluetooth_info())

    async def notify(self, title, message):
        await asyncio.to_thread(
            subprocess.run,
            ["notify-send", title, message],
            capture_output=True,
            text=True,
            check=False,
        )

    async def disconnect_bluetooth_device(self, device_id):
        await asyncio.to_thread(
            subprocess.run,
            ["bluetoothctl", "disconnect", device_id],
            capture_output=True,
            text=True,
            check=False,
        )

    async def connect_bluetooth_device(self, device_id):
        await asyncio.to_thread(
            subprocess.run,
            ["bluetoothctl", "connect", device_id],
            capture_output=True,
            text=True,
            check=False,
        )

    def on_bluetooth_clicked(self, gesture, *_):
        global_loop.create_task(self._handle_bluetooth_click(gesture))

    async def _handle_bluetooth_click(self, gesture):
        button = gesture.get_widget()
        label = button.get_last_child()
        icon = button.get_first_child()

        device_name = label.get_label()
        device_id = self.bluetooth_buttons[device_name]

        connected_devices_str = await self._get_connected_devices()

        if device_id in connected_devices_str:
            await self.notify(
                "Bluetooth plugin", f"Disconnecting bluetooth device: {device_name}"
            )
            await self.disconnect_bluetooth_device(device_id)
        else:
            await self.notify(
                "Bluetooth plugin", f"Connecting bluetooth device: {device_name}"
            )
            await self.connect_bluetooth_device(device_id)

        GLib.idle_add(self._update_button_state, button, icon, device_id)

    def _update_button_state(self, button, icon, device_id):
        try:
            proc = subprocess.run(
                ["bluetoothctl", "info"], capture_output=True, text=True, check=False
            )
            connected_devices_str = proc.stdout

            if device_id in connected_devices_str:
                icon.set_from_icon_name("blueberry-tray")
                button.add_css_class("bluetooth-dashboard-buttons-connected")
            else:
                icon.set_from_icon_name("blueberry-tray-disabled")
                button.remove_css_class("bluetooth-dashboard-buttons-connected")

            self.obj.load_css_from_file()

        except Exception as e:
            self.logger.error(f"Error updating button state: {e}")
        return False

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()
        elif self.popover_dashboard and not self.popover_dashboard.is_visible():
            self.popover_dashboard.popup()
        else:
            # Create a popover with loading state and start async data fetch
            self.create_popover_with_loading_state()

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        self.popover_dashboard = None
        return
