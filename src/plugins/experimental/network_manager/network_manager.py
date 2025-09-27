from gi.repository import Gtk, GLib  # pyright: ignore
import asyncio
from typing import Dict, Any, List
import time
from src.plugins.core._base import BasePlugin
from src.plugins.core._event_loop import global_loop
import os
from ._network_cli_backend import NetworkCLI

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
        return NetworkManager(panel_instance)
    return None


class NetworkManager(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.cli_backend = NetworkCLI(self.logger)
        self.button = Gtk.MenuButton()
        self.popover = Gtk.Popover()
        self.icon_wired_connected = self.gtk_helper.icon_exist(
            "gnome-dev-network-symbolic",
            [
                "org.gnome.Settings-network-symbolic",
                "network-wired-activated-symbolic",
                "network-wired-symbolic",
            ],
        )
        self.icon_wired_disconnected = self.gtk_helper.icon_exist(
            "network-wired-disconnected-symbolic"
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
        await self.scan_networks_and_update_cache()
        while True:
            await asyncio.sleep(WIFI_SCAN_INTERVAL)
            await self.scan_networks_and_update_cache()

    def notify_send_network_disconnected(self):
        if self.network_disconnected and self.notify_was_sent is False:
            default_interface = self.cli_backend.get_default_interface_sync()
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
        is_connected = await self.cli_backend.is_internet_connected_async()
        default_interface = await self.cli_backend.get_default_interface_async()
        if default_interface and self._is_wireless_interface(default_interface):
            if is_connected:
                connected_ssid = await self.cli_backend.get_connected_wifi_ssid_async()
                if connected_ssid:
                    signal = await self.cli_backend._get_wifi_signal_strength_async(
                        connected_ssid
                    )
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

    async def is_internet_connected_async(self) -> bool:
        """
        Check if internet is available. UI wrapper to update disconnection state.
        """
        is_connected = await self.cli_backend.is_internet_connected_async()
        if is_connected:
            self.notify_was_sent = False
            self.network_disconnected = False
            return True
        self.network_disconnected = True
        self.notify_send_network_disconnected()
        return False

    async def create_scrollable_grid_content_async(self):
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
        output = await self.cli_backend.run_nmcli_device_show_async()
        devices = self.cli_backend.parse_nmcli_output(output)
        revealers = []

        def update_scrolled_window_height(*_):
            """Update height based on whether any revealer is open."""
            if any(r.get_reveal_child() for r in revealers):
                scrolled_window.set_min_content_height(500)
            else:
                max_devices_height = 60 * len(devices)
                scrolled_window.set_min_content_height(min(500, max_devices_height))

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
            self.gtk_helper.icon_exist(
                "gnome-control-center-symbolic",
                ["org.gnome.Settings"],
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

    async def populate_wifi_list_async(self):
        """Populates the Wi-Fi list box with cached data or a status message."""
        while child := self.wifi_list_box.get_first_child():  # pyright: ignore
            GLib.idle_add(self.wifi_list_box.remove, child)  # pyright: ignore
        connected_ssid = await self.cli_backend.get_connected_wifi_ssid_async()
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
        """Update popover content after a scan, without updating the whole UI."""
        await self.populate_wifi_list_async()

    async def update_icon_and_popover(self):
        """Update icon and refresh popover content."""
        await self.update_icon_async()
        content = await self.create_scrollable_grid_content_async()
        GLib.idle_add(self.popover.set_child, content)

    def on_connect_button_clicked(self, button, ssid):
        """UI event handler to connect to a specified Wi-Fi network."""
        global_loop.create_task(self._connect_to_network_async(ssid))

    async def on_config_clicked_async(self, widget=None):
        """Launches the Control Center to configure the network settings."""
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

    async def scan_networks_and_update_cache(self):
        """
        Runs the CLI scan, updates the UI's cache, and refreshes the popover if visible.
        """
        if self.scanning_in_progress:
            return
        self.scanning_in_progress = True
        if self.popover.get_property("visible") and self.scan_status_label:
            GLib.idle_add(self.scan_status_label.set_label, "Scanning...")
        return_code, raw_output = await self.cli_backend.scan_networks_async()
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
        """Applies autoconnect settings from config via the CLI backend."""
        ssids_to_autoconnect: List[str] = self.ssids_to_auto_connect
        await self.cli_backend._apply_config_autoconnect_settings_async(
            ssids_to_autoconnect
        )

    async def _connect_to_network_async(self, ssid: str):
        """UI-side wrapper for the connection attempt."""
        self.logger.info(f"UI: Attempting connection to {ssid}")
        GLib.idle_add(self.popover.popdown)
        await self.cli_backend._connect_to_network_async(ssid)
        await self.update_icon_and_popover()
