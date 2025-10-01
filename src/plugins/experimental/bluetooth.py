import gi
import asyncio
import subprocess
import re
import pulsectl
from gi.repository import GLib, Gtk  # pyright: ignore
from src.plugins.core._base import BasePlugin

gi.require_version("Gtk", "4.0")
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "top-panel-systray"
    order = 3
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        bt = Bluetooth(panel_instance)
        bt.global_loop.create_task(bt.create_menu_popover_bluetooth())
        bt.global_loop.create_task(bt._auto_connect_devices())
        return bt


class Bluetooth(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_dashboard = None
        self.bluetooth_buttons = {}
        self.bluetooth_button_popover = Gtk.Button()
        self.gtk_helper.add_cursor_effect(self.bluetooth_button_popover)
        self.main_widget = (self.bluetooth_button_popover, "append")

    def _extract_mac_from_string(self, entry_string):
        """
        Extracts a MAC address (e.g., B4:B7:42:F7:9B:AD) from a string.
        Handles PA sink names (B4_B7_42_F7_9B_AD) and standard MAC format.
        """
        mac_pattern = r"([0-9A-F]{2}[_:]?){5}[0-9A-F]{2}"
        match = re.search(mac_pattern, entry_string, re.IGNORECASE)
        if match:
            mac = match.group(0).replace("_", ":").upper()
            if mac.count(":") == 5:
                return mac
        return None

    async def _auto_connect_devices(self):
        """Reads config and attempts to connect specified Bluetooth devices."""
        connect_devices = self.get_config(
            ["hardware", "bluetooth", "connect_devices"], []
        )
        if not connect_devices:
            self.logger.info("No devices configured for auto-connect.")
            return
        self.logger.info(
            f"Attempting Bluetooth auto-connect for configured devices: {connect_devices}"
        )
        known_devices = await self._get_devices()
        macs_to_connect = set()
        for entry in connect_devices:
            mac = self._extract_mac_from_string(entry)
            if mac:
                macs_to_connect.add(mac)
                continue
            for device in known_devices:
                if device.get("name") == entry:
                    macs_to_connect.add(device["mac"])
                    break
        if not macs_to_connect:
            self.logger.warning(
                f"Could not find MAC addresses for any configured auto-connect device based on input: {connect_devices}"
            )
            return
        for mac in macs_to_connect:
            device_info = await self._get_device_info(mac)
            if not device_info:
                self.logger.warning(
                    f"Device info not found for MAC: {mac}. Skipping auto-connect."
                )
                continue
            device_name = device_info.get("Name", mac)
            is_connected = device_info.get("Connected", "no").lower() == "yes"
            if is_connected:
                self.logger.info(
                    f"Device '{device_name}' is already connected. Skipping auto-connect."
                )
                continue
            self.logger.info(f"Auto-connecting to device: {device_name} ({mac})")
            await self._connect_device_and_set_sink(mac, device_info)
        self.logger.info("Bluetooth auto-connect routine complete.")

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
            self.logger.exception(f"Error getting bluetooth devices: {e}")
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
            self.logger.exception(f"Error getting device info for {mac_address}: {e}")
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
            self.logger.exception(
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
            self.logger.exception(f"Failed to set default sink with pulsectl: {e}")

    async def create_menu_popover_bluetooth(self):
        self.bluetooth_button_popover.connect("clicked", self.open_popover_dashboard)

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
        self.popover_dashboard.set_parent(self.bluetooth_button_popover)
        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        loading_label = Gtk.Label(label="Loading...")
        box.append(loading_label)
        self.popover_dashboard.set_child(box)
        self.popover_dashboard.popup()
        self.global_loop.create_task(self._fetch_and_update_bluetooth_info())

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
                    lambda _, *args, mac=device_mac: self.global_loop.create_task(
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

    async def _connect_device_and_set_sink(self, device_id, device_info):
        """Helper to handle connection, sink setup, and notification (used by click and auto-connect)."""
        device_name = device_info.get("Name", device_id)
        icon_name = device_info.get("Icon", "bluetooth")
        is_audio_device = any(
            s in icon_name.lower() for s in ["audio", "headset", "speaker", "card"]
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
                    self.logger.info(f"Successfully found PA sink on attempt {i + 1}.")
                    break
                await asyncio.sleep(WAIT_TIME)
            if pa_sink_info:
                await self._set_default_sink(pa_sink_info, device_name)
            else:
                self.logger.warning(
                    f"Could not find PulseAudio sink for connected device {device_name} ({device_id}) after {MAX_RETRIES * WAIT_TIME} seconds."
                )

    async def _handle_bluetooth_click(self, device_id):
        device_info = await self._get_device_info(device_id)
        if not device_info:
            return
        device_name = device_info.get("Name", device_id)
        icon_name = device_info.get("Icon", "bluetooth")
        is_connected = device_info.get("Connected", "no").lower() == "yes"
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
            await self._connect_device_and_set_sink(device_id, device_info)
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
        It also automatically connects devices listed in the `[hardware.bluetooth]`
        section of the configuration upon startup.
        When an audio device is connected, it is automatically set as the
        system's default sound output device using the robust 'pulsectl' library
        with a retry mechanism to handle PulseAudio sink creation delays.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin acts as a user-friendly interface for the system's
        Bluetooth functionality.
        **Concurrency Fix:**
        The explicit import of `global_loop` was removed. All asynchronous task
        scheduling is now correctly handled using the inherited instance attribute
        `self.global_loop` (or `bt.global_loop` in the factory function), which
        is injected by `BasePlugin.__init__`.
        1. **Initialization:** The `initialize_plugin` function now correctly uses
           `bt.global_loop.create_task()` to schedule startup tasks.
        2. **Popover Logic:** `create_popover_with_loading_state` uses
           `self.global_loop.create_task()`.
        3. **Click Handling:** The `GestureClick` connection uses
           `self.global_loop.create_task()`.
        This refactoring ensures a consistent and robust approach to concurrency,
        using the resources provided by the base class.
        """
        return self.code_explanation.__doc__
