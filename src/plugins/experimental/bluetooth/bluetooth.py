def get_plugin_metadata(panel):
    about = (
        "A plugin that provides a dashboard for managing Bluetooth devices.",
        "It displays a list of paired devices, indicates their connection status",
        "and allows the user to connect or disconnect them with a single click.",
    )

    id = "org.waypanel.plugin.bluetooth"
    default_container = "right-panel-center"
    container, id = panel.config_handler.get_plugin_container(default_container, id)
    hidden = panel.config_handler.get_root_setting([id, "hide_in_systray"], True)

    return {
        "id": id,
        "name": "Bluetooth Manager",
        "version": "1.0.0",
        "enabled": True,
        "index": 6,
        "hidden": hidden,
        "container": container,
        "deps": ["top_panel", "css_generator"],
        "description": about,
    }


def get_plugin_class():
    import re
    import pulsectl
    from dbus_fast import BusType
    from dbus_fast.aio import MessageBus
    from src.plugins.core._base import BasePlugin

    class Bluetooth(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover_dashboard = None
            self.bluetooth_buttons = {}
            self.bluetooth_button_popover = self.gtk.Button()
            self.add_cursor_effect(self.bluetooth_button_popover)
            self.main_widget = (self.bluetooth_button_popover, "append")
            self.main_icon = self.get_plugin_setting(
                "main_icon", "bluetooth-active-symbolic"
            )
            self.fallback_main_icons = self.get_plugin_setting(
                ["fallback_main_icons"],
                ["org.gnome.Settings-bluetooth-symbolic", "bluetooth"],
            )
            self.connect_devices = self.get_plugin_setting_add_hint(
                ["auto_connect"],
                ["B4:B7:42:F7:9B:AD"],
                (
                    "A list of **Bluetooth MAC addresses** (e.g., "
                    "['00:1A:7D:XX:XX:XX']) for devices Waypanel should "
                    "automatically attempt to connect to when it starts."
                ),
            )
            self.bus = None
            self._bus_lock = self.asyncio.Lock()

        def on_start(self):
            """Hook called by BasePlugin after successful initialization."""
            self.bluetooth_button_popover.connect(
                "clicked", self.open_popover_dashboard
            )
            self.run_in_async_task(self._init_dbus_and_auto_connect())
            self.plugins["css_generator"].install_css("bluetooth.css")

        async def _ensure_bus(self):
            async with self._bus_lock:
                if self.bus is None:
                    try:
                        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
                    except Exception as e:
                        self.logger.error(f"Failed to connect to System Bus: {e}")
                return self.bus

        async def _init_dbus_and_auto_connect(self):
            if await self._ensure_bus():
                await self._auto_connect_devices()

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
            if not self.connect_devices:
                return

            known_devices = await self._get_devices()
            macs_to_connect = set()
            for entry in self.connect_devices:
                mac = self._extract_mac_from_string(entry)
                if mac:
                    macs_to_connect.add(mac)
                    continue
                for device in known_devices:
                    if device.get("name") == entry:
                        macs_to_connect.add(device["mac"])
                        break

            for mac in macs_to_connect:
                info = await self._get_device_info(mac)
                if info and not info.get("Connected"):
                    await self._connect_device_and_set_sink(mac, info)

        async def _get_devices(self):
            bus = await self._ensure_bus()
            if not bus:
                return []
            try:
                introspection = await bus.introspect("org.bluez", "/")
                proxy = bus.get_proxy_object("org.bluez", "/", introspection)
                manager = proxy.get_interface("org.freedesktop.DBus.ObjectManager")
                objects = await manager.call_get_managed_objects()

                device_list = []
                for path, interfaces in objects.items():
                    if "org.bluez.Device1" in interfaces:
                        props = interfaces["org.bluez.Device1"]
                        mac = props["Address"].value
                        name = (
                            props.get("Name", {}).value
                            or props.get("Alias", {}).value
                            or "Unknown"
                        )
                        device_list.append({"mac": mac, "name": name, "path": path})
                return device_list
            except Exception as e:
                self.logger.exception(f"Error getting devices: {e}")
                return []

        async def _get_device_info(self, mac_address):
            bus = await self._ensure_bus()
            if not bus:
                return None
            try:
                obj_path = f"/org/bluez/hci0/dev_{mac_address.replace(':', '_')}"
                introspection = await bus.introspect("org.bluez", obj_path)
                proxy = bus.get_proxy_object("org.bluez", obj_path, introspection)
                properties = proxy.get_interface("org.freedesktop.DBus.Properties")
                all_props = await properties.call_get_all("org.bluez.Device1")

                info = {k: v.value for k, v in all_props.items()}
                info["mac"] = mac_address
                info["path"] = obj_path
                return info
            except Exception:
                return None

        async def _get_pa_sink_for_device(self, mac_address):
            """Retrieves the PulseAudio sink Info object using pulsectl."""
            mac_upper = mac_address.upper().replace(":", "_")

            def _sync_get_sink():
                with pulsectl.Pulse("Waypanel Bluetooth") as pulse:
                    sinks = pulse.sink_list()
                    for sink in sinks:
                        if sink.name.startswith("bluez_") and mac_upper in sink.name:
                            return sink
                    return None

            try:
                return await self.asyncio.to_thread(_sync_get_sink)
            except Exception as e:
                self.logger.exception(f"PulseAudio error for {mac_address}: {e}")
                return None

        async def _set_default_sink(self, sink_info, device_name):
            """Sets the default PulseAudio sink using pulsectl."""
            if not sink_info:
                return

            def _sync_set_default(sink):
                with pulsectl.Pulse("Waypanel Bluetooth") as pulse:
                    pulse.sink_default_set(sink)

            try:
                await self.asyncio.to_thread(_sync_set_default, sink_info)
                self.notifier.notify_send(
                    "Bluetooth Audio",
                    f"Default audio set to {device_name}",
                    "audio-volume-high-symbolic",
                )
            except Exception as e:
                self.logger.exception(f"Failed to set default sink: {e}")

        def open_popover_dashboard(self, *_):
            if self.popover_dashboard and self.popover_dashboard.is_visible():
                self.popover_dashboard.popdown()
            elif self.popover_dashboard and not self.popover_dashboard.is_visible():
                self.popover_dashboard.popup()
            else:
                self.create_popover_with_loading_state()

        def create_popover_with_loading_state(self):
            self.popover_dashboard = self.create_popover(
                parent_widget=self.bluetooth_button_popover,
                closed_handler=self.popover_is_closed,
                css_class="bluetooth-dashboard-popover",
            )
            box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)
            for side in ["top", "bottom", "start", "end"]:
                getattr(box, f"set_margin_{side}")(10)

            box.append(self.gtk.Label(label="Loading..."))
            self.popover_dashboard.set_child(box)
            self.popover_dashboard.popup()
            self.run_in_async_task(self._fetch_and_update_bluetooth_info())

        async def _fetch_and_update_bluetooth_info(self):
            devices_list = await self._get_devices()
            device_details = []
            for device in devices_list:
                info = await self._get_device_info(device["mac"])
                if info:
                    device_details.append(info)
            self.schedule_in_gtk_thread(self._update_popover_buttons, device_details)

        def _update_popover_buttons(self, device_details):
            if not self.popover_dashboard:
                return False
            popover_box = self.popover_dashboard.get_child()
            while child := popover_box.get_first_child():
                popover_box.remove(child)

            self.bluetooth_buttons.clear()
            if not device_details:
                popover_box.append(self.gtk.Label(label="No Bluetooth devices found."))
            else:
                for device in device_details:
                    btn = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 6)
                    btn.add_css_class("bluetooth-dashboard-buttons")
                    self.add_cursor_effect(btn)

                    name = device.get("Name", device["mac"])
                    btn.append(self.gtk.Label(label=f" {name}"))

                    spacer = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
                    spacer.set_hexpand(True)
                    btn.append(spacer)

                    icon = self.gtk.Image.new_from_icon_name(
                        device.get("Icon", "audio-card")
                    )
                    icon.set_pixel_size(24)
                    btn.append(icon)

                    mac = device["mac"]
                    gesture = self.gtk.GestureClick.new()
                    gesture.connect(
                        "released",
                        lambda *_, m=mac: self.run_in_async_task(
                            self._handle_bluetooth_click(m)
                        ),
                    )
                    btn.add_controller(gesture)

                    if device.get("Connected"):
                        btn.add_css_class("bluetooth-dashboard-buttons-connected")

                    self.bluetooth_buttons[mac] = btn
                    popover_box.append(btn)
            return False

        async def _connect_device_and_set_sink(self, device_id, device_info):
            """Handles connection and PulseAudio sink setup."""
            device_name = device_info.get("Name", device_id)
            icon = device_info.get("Icon", "bluetooth")
            is_audio = any(
                s in icon.lower() for s in ["audio", "headset", "speaker", "card"]
            )

            await self.connect_bluetooth_device(device_id)

            if is_audio:
                pa_sink = None
                for _ in range(10):
                    pa_sink = await self._get_pa_sink_for_device(device_id)
                    if pa_sink:
                        break
                    await self.asyncio.sleep(0.5)
                if pa_sink:
                    await self._set_default_sink(pa_sink, device_name)

        async def _handle_bluetooth_click(self, device_id):
            info = await self._get_device_info(device_id)
            if not info:
                return

            name = info.get("Name", device_id)
            icon = info.get("Icon", "bluetooth")

            if info.get("Connected"):
                self.notifier.notify_send("Bluetooth", f"Disconnecting: {name}", icon)
                await self.disconnect_bluetooth_device(device_id)
            else:
                self.notifier.notify_send("Bluetooth", f"Connecting: {name}", icon)
                await self._connect_device_and_set_sink(device_id, info)

            if self.popover_dashboard and self.popover_dashboard.is_visible():
                await self._update_single_button_state(device_id)

        async def _update_single_button_state(self, device_id):
            if device_id in self.bluetooth_buttons:
                info = await self._get_device_info(device_id)
                if not info:
                    return
                btn = self.bluetooth_buttons[device_id]
                conn = info.get("Connected")
                self.schedule_in_gtk_thread(
                    lambda: btn.add_css_class("bluetooth-dashboard-buttons-connected")
                    if conn
                    else self.safe_remove_css_class(
                        btn, "bluetooth-dashboard-buttons-connected"
                    )
                )

        async def disconnect_bluetooth_device(self, device_id):
            bus = await self._ensure_bus()
            if not bus:
                return
            try:
                obj_path = f"/org/bluez/hci0/dev_{device_id.replace(':', '_')}"
                introspection = await bus.introspect("org.bluez", obj_path)
                proxy = bus.get_proxy_object("org.bluez", obj_path, introspection)
                await proxy.get_interface("org.bluez.Device1").call_disconnect()
            except Exception as e:
                self.logger.error(f"D-Bus Disconnect failed: {e}")

        async def connect_bluetooth_device(self, device_id):
            bus = await self._ensure_bus()
            if not bus:
                return
            try:
                obj_path = f"/org/bluez/hci0/dev_{device_id.replace(':', '_')}"
                introspection = await bus.introspect("org.bluez", obj_path)
                proxy = bus.get_proxy_object("org.bluez", obj_path, introspection)
                await proxy.get_interface("org.bluez.Device1").call_connect()
            except Exception as e:
                self.logger.error(f"D-Bus Connect failed: {e}")

        def popover_is_closed(self, *_):
            self.popover_dashboard = None

        def code_explanation(self):
            """
            This plugin acts as a user-friendly interface for the system's
            Bluetooth functionality.
            **Refactoring Summary:**
            - **Protocol Transition:** Replaced the external 'bluetoothctl'
              binary dependency with 'dbus-fast'.
            - **D-Bus Integration:** Implemented direct communication with
              the BlueZ System Bus (BusType.SYSTEM) via the D-Bus
              ObjectManager interface.
            - **Lazy Connection Pattern:** Added an asynchronous lock
              mechanism (_bus_lock) and a helper method (_ensure_bus) to
              prevent race conditions and ensure the MessageBus is fully
              connected before introspection or method calls.
            - **Path Normalization:** Automates the conversion of MAC
              addresses to BlueZ object paths (e.g., replacing ':' with '_')
              to interact with Device1 interfaces.
            - **Audio Synchronization:** Maintains the PulseAudio sink
              management logic, ensuring that connected audio devices are
              automatically set as the default output through 'pulsectl'.
            """
            return self.code_explanation.__doc__

    return Bluetooth
