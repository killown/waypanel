from gi.repository import Gtk, GLib  # pyright: ignore
import subprocess
import asyncio
from typing import Optional, Dict, Any, List
import time
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop
import functools
import os

ENABLE_PLUGIN = True
DEPS = ["top_panel", "gestures_setup"]
ICON_CONNECTED = "notification-network-wired"
ICON_DISCONNECTED = "network-wired-disconnected-symbolic"
ICON_WIFI_CONNECTED = "wifi"
ICON_WIFI_DISCONNECTED = "network-wireless-disconnected-symbolic"
ICON_WIFI_EXCELLENT = "network-wireless-signal-excellent-symbolic"
ICON_WIFI_GOOD = "network-wireless-signal-good-symbolic"
ICON_WIFI_OK = "network-wireless-signal-ok-symbolic"
ICON_WIFI_WEAK = "network-wireless-signal-weak-symbolic"
WIFI_SCAN_INTERVAL = 300


def get_plugin_placement(panel_instance):
    """Define where the plugin should appear."""
    return "top-panel-systray", 4


def initialize_plugin(panel_instance):
    """Initialize the Network Status plugin."""
    if ENABLE_PLUGIN:
        return NetworkMonitorPlugin(panel_instance)
    return None


class NetworkMonitorPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.button = Gtk.MenuButton()
        self.popover = Gtk.Popover()
        self.icon_wired_connected = self.gtk_helper.set_widget_icon_name(
            None,
            [
                "gnome-dev-network-symbolic",
                "org.gnome.Settings-network-symbolic",
                "network-wired-activated-symbolic",
                "network-wired-symbolic",
            ],
        )
        self.icon_wired_disconnected = self.gtk_helper.set_widget_icon_name(
            None, ["network-wired-disconnected-symbolic"]
        )
        self.icon_wifi_connected = self.gtk_helper.icon_exist(
            ICON_WIFI_CONNECTED, ["network-wireless-connected-symbolic"]
        )
        self.icon_wifi_disconnected = self.gtk_helper.icon_exist(
            ICON_WIFI_DISCONNECTED, ["network-wireless-disconnected-symbolic"]
        )
        self.icon = self.icon_wired_disconnected
        self.popover.set_parent(self.button)
        self.init_ui()
        global_loop.create_task(self.periodic_check_async())
        self.popover.connect("notify::visible", self.on_popover_visibility_changed)
        self.network_disconnected = None
        self.notify_was_sent = False
        self.scan_revealer = None
        self.wifi_list_box = None
        self.wifi_scan_button = None
        self.scanning_in_progress = False
        self.cached_wifi_networks: List[Dict[str, Any]] = []
        self.last_scan_time: float = 0.0
        self.scan_status_label = None
        self.wifi_list_revealer = None
        self.ssids_to_auto_connect = self.config_handler.check_and_get_config(
            ["hardware", "network", "auto_connect_ssids"]
        )
        global_loop.create_task(self.start_periodic_wifi_scan_async())
        global_loop.create_task(self._apply_config_autoconnect_settings_async())

    async def start_periodic_wifi_scan_async(self):
        """Starts a periodic background scan for Wi-Fi networks using asyncio."""
        await self.scan_networks_async()
        while True:
            await asyncio.sleep(WIFI_SCAN_INTERVAL)
            await self.scan_networks_async()

    def notify_send_network_disconnected(self):
        if self.network_disconnected and self.notify_was_sent is False:
            default_interface = self.get_default_interface_sync()
            if default_interface and self._is_wireless_interface(default_interface):
                icon_name = self.icon_wifi_disconnected
            else:
                icon_name = self.icon_wired_disconnected
            self.notifier.notify_send(
                "Network Manager", "Network disconnected", icon_name
            )
            self.notify_was_sent = True

    def init_ui(self):
        """Initialize button and popover UI."""
        global_loop.create_task(self.update_icon_async())
        GLib.idle_add(self.button.set_icon_name, self.icon)
        self.button.set_popover(self.popover)
        self.gtk_helper.add_cursor_effect(self.button)
        self.popover.set_parent(self.button)
        global_loop.create_task(self.update_icon_async())
        self.main_widget = (self.button, "append")

    def _is_wireless_interface(self, interface: str) -> bool:
        """Check if an interface name indicates a wireless device."""
        return interface.startswith(("wlan", "wl"))

    async def update_icon_async(self):
        """Update the icon based on current connection status and type."""
        is_connected = await self.is_internet_connected_async()
        default_interface = await self.get_default_interface_async()
        if default_interface and self._is_wireless_interface(default_interface):
            if is_connected:
                connected_ssid = await self.get_connected_wifi_ssid_async()
                if connected_ssid:
                    signal = await self._get_wifi_signal_strength_async(connected_ssid)
                    if signal > 80:
                        self.icon = ICON_WIFI_EXCELLENT
                    elif signal > 60:
                        self.icon = ICON_WIFI_GOOD
                    elif signal > 40:
                        self.icon = ICON_WIFI_OK
                    else:
                        self.icon = ICON_WIFI_WEAK
                else:
                    self.icon = self.icon_wifi_disconnected
            else:
                self.icon = self.icon_wifi_disconnected
        else:
            self.icon = (
                self.icon_wired_connected
                if is_connected
                else self.icon_wired_disconnected
            )
        GLib.idle_add(self.button.set_icon_name, self.icon)

    async def _get_wifi_signal_strength_async(self, ssid: str) -> int:
        """
        Gets the signal strength of a given SSID using nmcli.
        Returns 0 if not found.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                "-g",
                "SSID,SIGNAL",
                "device",
                "wifi",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            output_lines = stdout.decode("utf-8").strip().split("\n")
            for line in output_lines:
                if ":" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        current_ssid = ":".join(parts[:-1]).replace("\\", "")
                        signal = parts[-1]
                        if current_ssid == ssid:
                            try:
                                return int(signal)
                            except (ValueError, TypeError):
                                return 0
            return 0
        except Exception as e:
            self.logger.error(f"Error getting signal strength: {e}")
            return 0

    async def periodic_check_async(self):
        """Periodically check network status using asyncio."""
        while True:
            await self.update_icon_async()
            await asyncio.sleep(30)

    def on_popover_visibility_changed(self, popover, param):
        """Update content when popover becomes visible."""
        if self.popover.get_property("visible"):
            global_loop.create_task(self.update_popover_content_async())

    async def update_popover_content_async(self):
        """Update popover content without changing the icon."""
        content = await self.create_scrollable_grid_content_async()
        GLib.idle_add(self.popover.set_child, content)

    async def is_internet_connected_async(self):
        """
        Check if internet is available.
        Returns:
            bool: True if connected, False otherwise
        """
        interface = await self.get_default_interface_async()
        if interface and await self.check_interface_carrier_async(interface):
            self.notify_was_sent = False
            self.network_disconnected = False
            return True
        self.network_disconnected = True
        self.notify_send_network_disconnected()
        return False

    async def create_scrollable_grid_content_async(self):
        revealers = []
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.add_css_class("network-manager-container")
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        wifi_scan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        wifi_scan_box.add_css_class("network-manager-wifi-scan-box")
        wifi_toggle_button = Gtk.Button()
        wifi_toggle_button.add_css_class("network-manager-device-toggle-button")
        wifi_toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        wifi_toggle_box.add_css_class("network-manager-device-header")
        self.scan_status_label = Gtk.Label(label="Wi-Fi Networks")
        self.scan_status_label.set_halign(Gtk.Align.START)
        wifi_arrow_icon = Gtk.Image.new_from_icon_name("pan-down-symbolic")
        wifi_toggle_box.append(self.scan_status_label)
        wifi_toggle_box.append(wifi_arrow_icon)
        wifi_toggle_button.set_child(wifi_toggle_box)
        wifi_scan_box.append(wifi_toggle_button)
        self.wifi_list_revealer = Gtk.Revealer()
        self.wifi_list_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self.wifi_list_revealer.set_reveal_child(False)
        self.wifi_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.wifi_list_revealer.set_child(self.wifi_list_box)

        def on_toggle_wifi_list(
            btn, revealer=self.wifi_list_revealer, icon=wifi_arrow_icon
        ):
            revealed = revealer.get_reveal_child()
            revealer.set_reveal_child(not revealed)
            icon.set_from_icon_name(
                "pan-up-symbolic" if revealed else "pan-down-symbolic"
            )

        wifi_toggle_button.connect("clicked", on_toggle_wifi_list)
        wifi_scan_box.append(self.wifi_list_revealer)
        main_box.append(wifi_scan_box)
        await self.populate_wifi_list_async()
        separator = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        main_box.append(separator)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.add_css_class("network-manager-scrolledwindow")
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_width(600)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        output = await self.run_nmcli_device_show_async()
        devices = self.parse_nmcli_output(output)
        revealers = []

        def update_scrolled_window_height(*_):
            """Update height based on whether any revealer is open."""
            if any(r.get_reveal_child() for r in revealers):
                scrolled_window.set_min_content_height(500)
            else:
                scrolled_window.set_min_content_height(60 * len(devices))

        for idx, device in enumerate(devices):
            interface_name = device.get("GENERAL.DEVICE", "Unknown")
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            header_box.add_css_class("network-manager-device-header")
            header_label = Gtk.Label(label=f"{interface_name}")
            arrow_icon = Gtk.Image.new_from_icon_name("pan-down-symbolic")
            header_box.append(header_label)
            header_box.append(arrow_icon)
            toggle_button = Gtk.Button()
            toggle_button.add_css_class("network-manager-device-toggle-button")
            toggle_button.set_child(header_box)
            revealer = Gtk.Revealer()
            revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
            revealer.set_reveal_child(False)
            revealer.connect("notify::reveal-child", update_scrolled_window_height)
            revealers.append(revealer)
            grid = Gtk.Grid()
            grid.add_css_class("network-manager-device-details-grid")
            grid.set_row_spacing(6)
            grid.set_column_spacing(12)
            row = 0
            for key, value in device.items():
                label_key = Gtk.Label(label=key.strip())
                label_key.set_halign(Gtk.Align.START)
                label_key.add_css_class("dim-label")
                label_value = Gtk.Label(label=value.strip())
                label_value.set_halign(Gtk.Align.START)
                label_value.set_selectable(True)
                label_value.set_wrap(True)
                grid.attach(label_key, 0, row, 1, 1)
                grid.attach(label_value, 1, row, 1, 1)
                row += 1
            revealer.set_child(grid)

            def on_toggled(btn, r=revealer, icon=arrow_icon):
                revealed = r.get_reveal_child()
                r.set_reveal_child(not revealed)
                icon.set_from_icon_name(
                    "pan-up-symbolic" if revealed else "pan-down-symbolic"
                )

            toggle_button.connect("clicked", on_toggled)
            vbox.append(toggle_button)
            vbox.append(revealer)
            if idx < len(devices) - 1:
                separator = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
                separator.add_css_class("network-manager-device-separator")
                vbox.append(separator)
        scrolled_window.set_child(vbox)
        main_box.append(scrolled_window)
        config_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        config_box.add_css_class("network-manager-config-box")
        config_label = Gtk.Label(label="Network Settings")
        config_label.add_css_class("network-manager-config-label")
        config_button = Gtk.Button()
        config_button.add_css_class("network-manager-config-button")
        config_button.set_icon_name(
            self.gtk_helper.set_widget_icon_name(
                None,
                ["gnome-control-center-symbolic", "org.gnome.Settings"],
            )
        )
        config_box.append(config_button)
        config_box.append(config_label)
        self.gtk_helper.add_cursor_effect(config_button)
        self.plugins["gestures_setup"].create_gesture(
            config_box,
            1,
            lambda _: global_loop.create_task(self.on_config_clicked_async()),
        )
        self.gtk_helper.add_cursor_effect(config_box)
        main_box.append(config_box)
        update_scrolled_window_height()
        return main_box

    async def get_connected_wifi_ssid_async(self) -> Optional[str]:
        """
        Gets the SSID of the currently connected Wi-Fi network using nmcli.
        Returns None if not connected to Wi-Fi.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                "-t",
                "-f",
                "DEVICE,TYPE,STATE,CONNECTION",
                "device",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            for line in stdout.decode().strip().split("\n"):
                parts = line.strip().split(":")
                if len(parts) >= 4:
                    device, type_, state, connection = parts
                    if type_ == "wifi" and state.lower() == "connected":
                        return connection
            return None
        except Exception:
            self.logger.error("Error: nmcli command failed.")
            return None

    def get_connected_wifi_ssid_sync(self) -> Optional[str]:
        """
        Gets the SSID of the currently connected Wi-Fi network using nmcli.
        This is a synchronous helper for cases where async is not possible.
        """
        try:
            result = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "DEVICE,TYPE,STATE,CONNECTION",
                    "device",
                    "status",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            for line in result.stdout.strip().split("\n"):
                parts = line.strip().split(":")
                if len(parts) >= 4:
                    device, type_, state, connection = parts
                    if type_ == "wifi" and state.lower() == "connected":
                        return connection
            return None
        except subprocess.CalledProcessError:
            self.logger.error("Error: nmcli command failed.")
            return None

    async def populate_wifi_list_async(self):
        """Populates the Wi-Fi list box with cached data or a status message."""
        while child := self.wifi_list_box.get_first_child():  # pyright: ignore
            GLib.idle_add(self.wifi_list_box.remove, child)  # pyright: ignore
        connected_ssid = await self.get_connected_wifi_ssid_async()
        if connected_ssid and self.scan_status_label:
            GLib.idle_add(
                self.scan_status_label.set_label, f"Connected to: {connected_ssid}"
            )
        elif self.scan_status_label:
            GLib.idle_add(self.scan_status_label.set_label, "Wi-Fi Networks")
        if self.scanning_in_progress and self.wifi_list_box:
            if self.scan_status_label:
                GLib.idle_add(self.scan_status_label.set_label, "Scanning...")
            spinner = Gtk.Spinner(spinning=True, visible=True)
            GLib.idle_add(self.wifi_list_box.append, spinner)
        elif self.cached_wifi_networks and self.wifi_list_box:
            last_scan_str = time.strftime(
                "%H:%M:%S", time.localtime(self.last_scan_time)
            )
            if not connected_ssid and self.scan_status_label:
                GLib.idle_add(
                    self.scan_status_label.set_label,
                    f"Wi-Fi Networks (Last scan: {last_scan_str})",
                )
            for network in self.cached_wifi_networks:
                network_button = Gtk.Button()
                network_button.add_css_class("network-scan-item")
                network_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                network_box.set_halign(Gtk.Align.START)
                icon_name = "network-wireless-symbolic"
                try:
                    signal = int(network.get("signal", 0))
                except (ValueError, TypeError):
                    signal = 0
                if signal > 80:
                    icon_name = "network-wireless-signal-excellent-symbolic"
                elif signal > 60:
                    icon_name = "network-wireless-signal-good-symbolic"
                elif signal > 40:
                    icon_name = "network-wireless-signal-ok-symbolic"
                else:
                    icon_name = "network-wireless-signal-weak-symbolic"
                signal_icon = Gtk.Image.new_from_icon_name(icon_name)
                network_box.append(signal_icon)
                ssid = network.get("ssid", "Unknown SSID")
                ssid_label = Gtk.Label(label=f"<b>{ssid}</b>", use_markup=True)
                ssid_label.set_halign(Gtk.Align.START)
                network_box.append(ssid_label)
                if ssid == connected_ssid:
                    connected_icon = Gtk.Image.new_from_icon_name(
                        "object-select-symbolic"
                    )
                    network_box.append(connected_icon)
                strength_label = Gtk.Label(label=f"{signal}%")
                strength_label.set_halign(Gtk.Align.END)
                network_box.append(strength_label)
                network_button.set_child(network_box)
                network_button.connect("clicked", self.on_connect_button_clicked, ssid)
                GLib.idle_add(self.wifi_list_box.append, network_button)
        elif not connected_ssid and self.scan_status_label:
            GLib.idle_add(self.scan_status_label.set_label, "No Wi-Fi networks found.")

    async def update_popover_async(self):
        await self.populate_wifi_list_async()

    async def update_icon_and_popover(self):
        """Update icon and refresh popover content."""
        await self.update_icon_async()
        content = await self.create_scrollable_grid_content_async()
        GLib.idle_add(self.popover.set_child, content)

    def on_connect_button_clicked(self, button, ssid):
        """
        Connect to a specified Wi-Fi network using nmcli.
        """
        global_loop.create_task(self._connect_to_network_async(ssid))

    async def on_config_clicked_async(self, widget=None):
        """
        Launches the Control Center to configure the network settings.
        """
        try:
            self.logger.info("Opening configuration window for network plugin.")
            env = os.environ.copy()
            env["XDG_CURRENT_DESKTOP"] = "GNOME"
            await asyncio.create_subprocess_exec(
                "gnome-control-center", "network", env=env
            )
        except FileNotFoundError:
            self.logger.error("gnome-control-center not found. Please install it.")
        except Exception as e:
            self.logger.error(f"Failed to launch config tool: {e}")

    async def run_nmcli_device_show_async(self):
        """Run 'nmcli device show' and return its output."""
        try:
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                "device",
                "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return stdout.decode()
            else:
                return f"Error running nmcli device show:\n{stderr.decode()}"
        except Exception as e:
            return f"Exception while running nmcli:\n{str(e)}"

    def parse_nmcli_output(self, raw_output):
        """Parse raw nmcli device show output into list of device sections."""
        devices = []
        current_device = {}
        lines = raw_output.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                if current_device:
                    if current_device.get("GENERAL.DEVICE") != "lo":
                        devices.append(current_device)
                    current_device = {}
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                current_device[key.strip()] = value.strip()
        if current_device:
            if current_device.get("GENERAL.DEVICE") != "lo":
                devices.append(current_device)
        return devices

    def get_default_interface_sync(self) -> Optional[str]:
        """Synchronous version for a quick check."""
        try:
            with open("/proc/net/route") as f:
                for line in f.readlines():
                    parts = line.strip().split()
                    if parts[1] == "00000000":
                        return parts[0]
        except Exception as e:
            self.logger.error("Error reading default route:", e)
        return None

    async def get_default_interface_async(self) -> Optional[str]:
        """
        Get the name of the default network interface asynchronously.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_default_interface_sync)

    def check_interface_carrier_sync(self, interface: str) -> bool:
        """
        Check if a network interface is physically connected (carrier is up) synchronously.
        """
        try:
            with open(f"/sys/class/net/{interface}/carrier", "r") as f:
                return f.read().strip() == "1"
        except FileNotFoundError:
            self.logger.error(f"Interface '{interface}' not found.")
            return False

    async def check_interface_carrier_async(self, interface: str) -> bool:
        """
        Check if a network interface is physically connected (carrier is up) asynchronously.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, functools.partial(self.check_interface_carrier_sync, interface)
        )

    async def scan_networks_async(self):
        """
        Asynchronously run nmcli to scan for networks and update the UI.
        """
        if self.scanning_in_progress:
            return
        self.logger.error("Starting async nmcli scan...")
        self.scanning_in_progress = True
        if self.scan_status_label:
            GLib.idle_add(self.scan_status_label.set_label, "Scanning...")
        try:
            rescan_process = await asyncio.create_subprocess_exec(
                "nmcli",
                "device",
                "wifi",
                "rescan",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await rescan_process.wait()
            list_process = await asyncio.create_subprocess_exec(
                "nmcli",
                "-g",
                "SSID,SIGNAL,BSSID",
                "device",
                "wifi",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await list_process.communicate()
            raw_output = stdout.decode("utf-8")
            return_code = list_process.returncode
        except Exception as e:
            self.logger.error(f"Error executing nmcli: {e}")
            return_code = 1
            raw_output = ""
        self.scanning_in_progress = False
        self.last_scan_time = time.time()
        self.cached_wifi_networks = []
        if return_code != 0:
            self.logger.error(f"Error executing nmcli: {return_code}")
            if self.scan_status_label:
                GLib.idle_add(
                    self.scan_status_label.set_label,
                    "Error: Could not scan for networks.",
                )
            return
        output_lines = raw_output.strip().split("\n")
        if not output_lines or output_lines[0] == "":
            if self.scan_status_label:
                GLib.idle_add(
                    self.scan_status_label.set_label, "No Wi-Fi networks found."
                )
            return
        for line in output_lines:
            parts = line.split(":")
            if len(parts) >= 7:
                bssid_parts = parts[-6:]
                bssid = ":".join(bssid_parts)
                signal = parts[-7]
                ssid_parts = parts[:-7]
                ssid = ":".join(ssid_parts)
            else:
                try:
                    ssid, signal, bssid = line.rsplit(":", 2)
                except ValueError:
                    self.logger.error(f"Skipping malformed nmcli output line: {line}")
                    continue
            self.cached_wifi_networks.append(
                {
                    "ssid": ssid.replace("\\", ""),
                    "signal": signal,
                    "bssid": bssid,
                }
            )
        if self.popover.get_property("visible"):
            global_loop.create_task(self.update_popover_async())

    async def _apply_config_autoconnect_settings_async(self):
        """
        Enforces a whitelist for auto-connect: sets connection.autoconnect=yes for
        networks in the config list, and connection.autoconnect=no for all others.
        The multiple subprocess calls are necessary because NetworkManager
        stores the SSID (what is in the config list) separate from the Connection
        Name (what is needed to modify the profile).
        """
        ssids_to_autoconnect: List[str] = self.ssids_to_auto_connect
        try:
            list_proc = await asyncio.create_subprocess_exec(
                "nmcli",
                "-t",
                "-f",
                "NAME,TYPE",
                "connection",
                "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await list_proc.communicate()
            all_wifi_connections: List[str] = []
            for line in stdout.decode().strip().split("\n"):
                if ":802-11-wireless" in line:
                    connection_name = line.split(":")[0].strip()
                    if connection_name:
                        all_wifi_connections.append(connection_name)
            self.logger.info(
                f"Checking {len(all_wifi_connections)} Wi-Fi connection profiles."
            )
        except Exception as e:
            self.logger.error(f"Error listing all connections: {e}")
            return
        for conn_name in all_wifi_connections:
            profile_ssid = conn_name
            try:
                ssid_proc = await asyncio.create_subprocess_exec(
                    "nmcli",
                    "-g",
                    "802-11-wireless.ssid",
                    "connection",
                    "show",
                    conn_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                ssid_out, _ = await ssid_proc.communicate()
                profile_ssid = ssid_out.decode().strip() or conn_name
            except Exception as e:
                self.logger.error(
                    f"Network Manager: Failed to retrieve SSID for {conn_name}: {e}"
                )
                pass
            if not ssids_to_autoconnect:
                return
            autoconnect_state = "yes" if profile_ssid in ssids_to_autoconnect else "no"
            try:
                modify_proc = await asyncio.create_subprocess_exec(
                    "nmcli",
                    "connection",
                    "modify",
                    conn_name,
                    "connection.autoconnect",
                    autoconnect_state,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await modify_proc.wait()
                if modify_proc.returncode == 0:
                    self.logger.info(
                        f"Successfully set autoconnect={autoconnect_state} for profile '{conn_name}' (SSID: {profile_ssid})."
                    )
                else:
                    self.logger.warning(
                        f"Warning: Failed to set autoconnect={autoconnect_state} for profile '{conn_name}' (SSID: {profile_ssid})."
                    )
            except Exception as e:
                self.logger.error(
                    f"Error applying autoconnect modification for {conn_name}: {e}"
                )

    async def _connect_to_network_async(self, ssid):
        """
        Async implementation of connecting to a network.
        """
        self.logger.error(f"Attempting to connect to network: {ssid}")
        GLib.idle_add(self.popover.popdown)
        try:
            profile_list_output = await asyncio.create_subprocess_exec(
                "nmcli",
                "-g",
                "NAME",
                "connection",
                "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await profile_list_output.communicate()
        except Exception as e:
            self.logger.error(f"Network Manager: {e}")

    def about(self):
        """
        A plugin that monitors and displays the status of network connections.
        It provides a panel icon that indicates connectivity and a popover
        menu with detailed information about all network devices, sourced from
        the `nmcli` command.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin provides a comprehensive view of the system's network status
        by combining low-level checks with a dynamic user interface.
        Its core logic is built on **system-level checks, process execution,
        and a dynamic GTK UI**:
        1.  **Status Monitoring**: The plugin periodically checks for internet
            connectivity using a low-level approach. It reads the system's
            default network interface from `/proc/net/route` and verifies
            its "carrier" status from `/sys/class/net/{interface}/carrier`.
            This allows for a quick, reliable status check that is reflected
            by a changing panel icon.
        2.  **External Process Execution**: When the user opens the popover,
            the plugin uses `subprocess` to execute the `nmcli device show`
            command. The output of this command is then parsed into a structured
            format, allowing the plugin to retrieve detailed information about
            all network devices.
        3.  **Dynamic UI Generation**: The popover is dynamically populated with
            the parsed `nmcli` data. It uses `Gtk.Revealer` widgets to create
            expandable sections for each network device, keeping the initial
            view clean while providing an option to see full details. It also
            proves a button to launch the `gnome-control-center` for
            network settings.
        4.  **Asynchronous Wi-Fi Scanning**: The network monitor actively scans
            for available Wi-Fi networks in the background. It uses
            `asyncio.create_subprocess_exec` to run `nmcli device wifi rescan`
            and then `nmcli device wifi list`. This ensures the UI remains
            responsive and the network list is up-to-date with a minimal
            impact on performance. The results are cached and used to populate
            the Wi-Fi section of the popover dynamically.
        """
        return self.code_explanation.__doc__
