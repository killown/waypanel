import gi
import asyncio
import subprocess
import re
import pulsectl
from gi.repository import GLib, Gtk  # pyright: ignore
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop

gi.require_version("Gtk", "4.0")
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
        self.gtk_helper.add_cursor_effect(self.menubutton_dashboard)
        self.main_widget = (self.menubutton_dashboard, "append")

    async def _get_devices(self):
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                check=False,
            )
            device_list = []
            for line in proc.stdout.strip().split("\n"):
                match = re.search(r"Device (\S+) (.*)", line)
                if match:
                    device_list.append({"mac": match.group(1), "name": match.group(2)})
            return device_list
        except Exception as e:
            self.logger.error(f"Error getting bluetooth devices: {e}")
            return []

    async def _get_device_info(self, mac_address):
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["bluetoothctl", "info", mac_address],
                capture_output=True,
                text=True,
                check=False,
            )
            if "Device not found" in proc.stdout:
                return None
            info = {}
            for line in proc.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                match = re.match(r"(\S+):\s*(.*)", line)
                if match:
                    key = match.group(1)
                    value = match.group(2)
                    info[key] = value.strip()
            return info
        except Exception as e:
            self.logger.error(f"Error getting device info for {mac_address}: {e}")
            return None

    async def _get_pa_sink_for_device(self, mac_address):
        """
        Retrieves the PulseAudio sink Info object for a given Bluetooth MAC address
        using the pulsectl library.
        """
        mac_upper = mac_address.upper().replace(":", "_")

        def _sync_get_sink():
            with pulsectl.Pulse("Waypanel Bluetooth") as pulse:
                sinks = pulse.sink_list()
                for sink in sinks:
                    if sink.name.startswith("bluez_") and mac_upper in sink.name:
                        return sink
                return None

        try:
            sink_info = await asyncio.to_thread(_sync_get_sink)
            return sink_info
        except Exception as e:
            self.logger.error(
                f"Error listing PulseAudio sinks (pulsectl) for mac {mac_address}: {e}"
            )
            return None

    async def _set_default_sink(self, sink_info, device_name):
        """Sets the default PulseAudio sink (output device) using pulsectl."""
        if not sink_info:
            self.logger.warning("No PulseAudio sink info provided to set as default.")
            return

        def _sync_set_default(sink):
            with pulsectl.Pulse("Waypanel Bluetooth") as pulse:
                pulse.sink_default_set(sink)

        try:
            self.logger.info(f"Setting default sink: {device_name}")
            await asyncio.to_thread(_sync_set_default, sink_info)
            display_name_part = device_name
            self.notifier.notify_send(
                "Bluetooth Audio",
                f"Default audio set to {display_name_part}",
                "audio-volume-high-symbolic",
            )
        except Exception as e:
            self.logger.error(f"Failed to set default sink with pulsectl: {e}")

    async def create_menu_popover_bluetooth(self):
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        icon_name = self.gtk_helper.set_widget_icon_name(
            "bluetooth", ["org.gnome.Settings-bluetooth-symbolic", "bluetooth"]
        )
        self.menubutton_dashboard.set_icon_name(icon_name)

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()
        elif self.popover_dashboard and not self.popover_dashboard.is_visible():
            self.popover_dashboard.popup()
        else:
            self.create_popover_with_loading_state()

    def create_popover_with_loading_state(self):
        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        loading_label = Gtk.Label(label="Loading...")
        box.append(loading_label)
        self.popover_dashboard.set_child(box)
        self.popover_dashboard.popup()
        global_loop.create_task(self._fetch_and_update_bluetooth_info())

    async def _fetch_and_update_bluetooth_info(self):
        devices_list = await self._get_devices()
        device_details = []
        for device in devices_list:
            info = await self._get_device_info(device["mac"])
            if info:
                info["mac"] = device["mac"]
                device_details.append(info)
        GLib.idle_add(self._update_popover_buttons, device_details)

    def _update_popover_buttons(self, device_details):
        if not self.popover_dashboard:
            return False
        popover_box = self.popover_dashboard.get_child()
        for child in popover_box:  # pyright: ignore
            popover_box.remove(child)  # pyright: ignore
        self.bluetooth_buttons.clear()
        if not device_details:
            no_devices_label = Gtk.Label(label="No Bluetooth devices found.")
            popover_box.append(no_devices_label)  # pyright: ignore
        else:
            for device in device_details:
                bluetooth_button = Gtk.Box.new(
                    orientation=Gtk.Orientation.HORIZONTAL, spacing=6
                )
                self.gtk_helper.add_cursor_effect(bluetooth_button)
                bluetooth_button.add_css_class("bluetooth-dashboard-buttons")
                label = Gtk.Label()
                label.set_label(" " + device.get("Name", device.get("mac")))
                bluetooth_button.append(label)
                spacer = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                spacer.set_hexpand(True)
                bluetooth_button.append(spacer)
                icon = Gtk.Image()
                icon_name = device.get("Icon", "audio-card")
                icon.set_from_icon_name(icon_name)
                icon.set_pixel_size(24)
                bluetooth_button.append(icon)
                gesture = Gtk.GestureClick.new()
                device_mac = device["mac"]
                gesture.connect(
                    "released",
                    lambda _, *args, mac=device_mac: global_loop.create_task(
                        self._handle_bluetooth_click(mac)
                    ),
                )
                gesture.set_button(1)
                bluetooth_button.add_controller(gesture)
                if device.get("Connected", "no").lower() == "yes":
                    bluetooth_button.add_css_class(
                        "bluetooth-dashboard-buttons-connected"
                    )
                else:
                    bluetooth_button.remove_css_class(
                        "bluetooth-dashboard-buttons-connected"
                    )
                self.bluetooth_buttons[device["mac"]] = bluetooth_button
                popover_box.append(bluetooth_button)  # pyright: ignore
        return False

    async def _handle_bluetooth_click(self, device_id):
        device_info = await self._get_device_info(device_id)
        if not device_info:
            return
        device_name = device_info.get("Name", device_id)
        icon_name = device_info.get("Icon", "bluetooth")
        is_connected = device_info.get("Connected", "no").lower() == "yes"
        is_audio_device = any(
            s in icon_name.lower() for s in ["audio", "headset", "speaker", "card"]
        )
        if is_connected:
            self.notifier.notify_send(
                "Bluetooth plugin",
                f"Disconnecting bluetooth device: {device_name}",
                icon_name,
            )
            await self.disconnect_bluetooth_device(device_id)
        else:
            self.notifier.notify_send(
                "Bluetooth plugin",
                f"Connecting bluetooth device: {device_name}",
                icon_name,
            )
            await self.connect_bluetooth_device(device_id)
            if is_audio_device:
                self.logger.info(
                    f"Attempting to set connected Bluetooth audio device ({device_name}) as default sink."
                )
                pa_sink_info = None
                MAX_RETRIES = 10
                WAIT_TIME = 0.5
                for i in range(MAX_RETRIES):
                    self.logger.debug(
                        f"Attempt {i + 1}/{MAX_RETRIES}: Searching for PA sink..."
                    )
                    pa_sink_info = await self._get_pa_sink_for_device(device_id)
                    if pa_sink_info:
                        self.logger.info(
                            f"Successfully found PA sink on attempt {i + 1}."
                        )
                        break
                    await asyncio.sleep(WAIT_TIME)
                if pa_sink_info:
                    await self._set_default_sink(pa_sink_info, device_name)
                else:
                    self.logger.warning(
                        f"Could not find PulseAudio sink for connected device {device_name} ({device_id}) after {MAX_RETRIES * WAIT_TIME} seconds."
                    )
        await self._update_single_button_state(device_id)

    async def _update_single_button_state(self, device_id):
        if device_id in self.bluetooth_buttons:
            device_info = await self._get_device_info(device_id)
            if not device_info:
                return
            button = self.bluetooth_buttons[device_id]
            if device_info.get("Connected", "no").lower() == "yes":
                button.add_css_class("bluetooth-dashboard-buttons-connected")
            else:
                button.remove_css_class("bluetooth-dashboard-buttons-connected")

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

    def popover_is_closed(self, *_):
        self.popover_dashboard = None
        return

    def about(self):
        """
        A plugin that provides a dashboard for managing Bluetooth devices.
        It displays a list of paired devices, indicates their connection status,
        and allows the user to connect or disconnect them with a single click.
        When an audio device is connected, it is automatically set as the
        system's default sound output device using the robust 'pulsectl' library
        with a retry mechanism to handle PulseAudio sink creation delays.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin acts as a user-friendly interface for the system's
        Bluetooth functionality, using external commands and asynchronous
        programming to provide a responsive user experience.
        Its core functionality is built on **asynchronous execution, external
        process control, and robust audio management**:
        1.  **Asynchronous Execution**: The plugin leverages Python's `asyncio`
            library to perform system-level operations without freezing the UI.
            Tasks that involve I/O, such as running `bluetoothctl` or
            communicating with PulseAudio via `pulsectl`, are executed in a
            separate thread using `asyncio.to_thread`.
        2.  **Robust Audio Control (pulsectl with Retry)**: The plugin uses the
            **`pulsectl`** library for direct and stable interaction with the
            PulseAudio server. After a successful Bluetooth audio device
            connection, a **retry loop** is introduced. It checks for the new
            audio sink (using the device's MAC address) up to 10 times over a
            period of 5 seconds. The corrected logic for searching the sink now
            checks for the necessary `bluez_` prefix (instead of the too-specific
            `bluez_sink`) and the MAC address, ensuring compatibility with modern
            PipeWire environments that use `bluez_output`.
        3.  **Dynamic UI Updates**: The user interface is dynamically generated
            based on the current state of Bluetooth devices. When a user clicks
            a device, the connection/disconnection is handled, and the button's
            style is updated without having to reload the entire popover.
        """
        return self.code_explanation.__doc__
