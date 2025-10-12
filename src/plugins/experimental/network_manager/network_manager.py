def get_plugin_metadata(_):
    about = """
            A plugin that monitors and displays system network status (wired and Wi-Fi)
            in the panel. It provides a Gtk.Popover with detailed device information,
            a list of available Wi-Fi networks for easy connection via nmcli, and
            direct access to network settings.
            """
    return {
        "id": "org.waypanel.plugin.network_manager",
        "name": "Network Manager",
        "version": "1.0.0",
        "enabled": True,
        "index": 10,
        "container": "top-panel-systray",
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    from typing import Dict, Any, List
    from src.plugins.core._base import BasePlugin
    from ._network_cli_backend import NetworkCLI

    ICON_WIFI_CONNECTED = "wifi"
    ICON_WIFI_DISCONNECTED = "network-wireless-disconnected-symbolic"
    ICON_WIFI_EXCELLENT = "network-wireless-signal-excellent-symbolic"
    ICON_WIFI_GOOD = "network-wireless-signal-good-symbolic"
    ICON_WIFI_OK = "network-wireless-signal-ok-symbolic"
    ICON_WIFI_WEAK = "network-wireless-signal-weak-symbolic"

    class NetworkManager(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.cli_backend = NetworkCLI(self.logger)
            self.button = self.gtk.MenuButton()
            self.popover = None
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
            self.stack = None
            self.header_box = None
            self.header_back_button = None
            self.header_title = None
            self.detail_container = None
            self.init_ui()
            self.global_loop.create_task(self.periodic_check_async())
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
            self.ssids_to_auto_connect = self.config_handler.get_root_setting(
                ["hardware", "network", "auto_connect_ssids"]
            )
            self.scan_interval = self.get_plugin_setting(["scan_interval"], 300)
            self.add_hint(
                "Settings for the Network Manager plugin, which controls and displays network connection status."
            )
            self.add_hint(
                "Time in (Seconds) to scan for Wi-Fi networks.", "scan_interval"
            )

        def on_start(self):
            self.global_loop.create_task(self.start_periodic_wifi_scan_async())
            self.global_loop.create_task(
                self._apply_config_autoconnect_settings_async()
            )

        async def start_periodic_wifi_scan_async(self):
            """Starts a periodic background scan for Wi-Fi networks using self.asyncio."""
            await self.scan_networks_and_update_cache()
            while True:
                await self.asyncio.sleep(self.scan_interval)
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
            """
            Initialize button and popover UI.
            Refactored to use self.create_popover helper.
            """
            self.popover = self.create_popover(
                parent_widget=self.button,
                css_class="network-manager-popover",
                has_arrow=False,
                closed_handler=None,
                visible_handler=self.on_popover_visibility_changed,
            )
            self.glib.idle_add(self.button.set_popover, self.popover)
            self.global_loop.create_task(self.update_icon_async())
            self.glib.idle_add(self.button.set_icon_name, self.icon)
            self.gtk_helper.add_cursor_effect(self.button)
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
                    connected_ssid = (
                        await self.cli_backend.get_connected_wifi_ssid_async()
                    )
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
            self.glib.idle_add(self.button.set_icon_name, self.icon)

        async def periodic_check_async(self):
            """Periodically check network status using self.asyncio."""
            while True:
                await self.update_icon_async()
                await self.asyncio.sleep(30)

        def on_popover_visibility_changed(self, popover, param):
            """Update content when popover becomes visible."""
            if self.popover.get_property("visible"):
                self.global_loop.create_task(self.update_popover_content_async())

        async def update_popover_content_async(self):
            """Update popover content without changing the icon."""
            content = await self.create_scrollable_grid_content_async()
            self.glib.idle_add(self.popover.set_child, content)

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

        def _create_device_detail_content(self, device: Dict[str, str]):
            """Creates the Gtk.Grid with all details for a single network device."""
            detail_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=10
            )
            grid = self.gtk.Grid()
            grid.add_css_class("network-manager-device-details-grid")
            grid.set_row_spacing(6)
            grid.set_column_spacing(12)
            row = 0
            for key, value in device.items():
                label_key = self.gtk.Label(label=key.strip())
                label_key.set_halign(self.gtk.Align.START)
                label_key.add_css_class("dim-label")
                label_value = self.gtk.Label(label=value.strip())
                label_value.set_halign(self.gtk.Align.START)
                label_value.set_selectable(True)
                label_value.set_wrap(True)
                grid.attach(label_key, 0, row, 1, 1)
                grid.attach(label_value, 1, row, 1, 1)
                row += 1
            detail_box.append(grid)
            return detail_box

        def on_device_icon_clicked(self, button, device_data):
            """Handles the click on a device icon to show its details (drill-down)."""
            interface_name = device_data.get("GENERAL.DEVICE", "Unknown")

            def switch_to_detail():
                self.header_title.set_label(f"{interface_name} Details")
                self.header_back_button.set_visible(True)
                detail_content = self._create_device_detail_content(device_data)
                while child := self.detail_container.get_first_child():
                    self.detail_container.remove(child)
                self.detail_container.append(detail_content)
                self.stack.set_visible_child_name("detail_view")

            self.glib.idle_add(switch_to_detail)

        def on_back_button_clicked(self, button):
            """Handles the back button click to return to the dashboard view."""

            def switch_to_dashboard():
                self.stack.set_visible_child_name("dashboard_view")

            self.glib.idle_add(switch_to_dashboard)

        async def create_scrollable_grid_content_async(self):
            main_popover_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=0
            )
            main_popover_box.add_css_class("network-manager-popover-content")
            self.header_box = self.gtk.Box(
                orientation=self.gtk.Orientation.HORIZONTAL, spacing=6
            )
            self.header_box.set_margin_top(10)
            self.header_box.set_margin_bottom(10)
            self.header_box.set_margin_start(10)
            self.header_box.set_margin_end(10)
            self.header_box.add_css_class("network-manager-header")
            self.header_back_button = self.gtk.Button.new_from_icon_name(
                "go-previous-symbolic"
            )
            self.header_back_button.set_visible(False)
            self.header_back_button.connect("clicked", self.on_back_button_clicked)
            self.header_title = self.gtk.Label(label="Network Dashboard")
            self.header_title.add_css_class("network-manager-heading")
            self.header_title.set_halign(self.gtk.Align.START)
            self.header_box.append(self.header_back_button)
            self.header_box.append(self.header_title)
            main_popover_box.append(self.header_box)
            self.stack = self.gtk.Stack()
            self.stack.set_transition_type(
                self.gtk.StackTransitionType.SLIDE_LEFT_RIGHT
            )
            dashboard_vbox = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=10
            )
            dashboard_vbox.set_margin_start(10)
            dashboard_vbox.set_margin_end(10)
            dashboard_vbox.set_margin_bottom(10)
            dashboard_vbox.add_css_class("network-dashboard-view")
            wifi_scan_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=10
            )
            wifi_scan_box.add_css_class("network-manager-wifi-scan-box")
            wifi_toggle_button = self.gtk.Button()
            wifi_toggle_button.add_css_class("network-manager-device-toggle-button")
            wifi_toggle_box = self.gtk.Box(
                orientation=self.gtk.Orientation.HORIZONTAL, spacing=6
            )
            wifi_toggle_box.add_css_class("network-manager-device-header")
            self.scan_status_label = self.gtk.Label(label="Wi-Fi Networks")
            self.scan_status_label.set_halign(self.gtk.Align.START)
            wifi_arrow_icon = self.gtk.Image.new_from_icon_name("pan-down-symbolic")
            wifi_toggle_box.append(self.scan_status_label)
            wifi_toggle_box.append(wifi_arrow_icon)
            wifi_toggle_button.set_child(wifi_toggle_box)
            wifi_scan_box.append(wifi_toggle_button)
            self.wifi_list_revealer = self.gtk.Revealer()
            self.wifi_list_revealer.set_transition_type(
                self.gtk.RevealerTransitionType.SLIDE_DOWN
            )
            self.wifi_list_revealer.set_reveal_child(False)
            self.wifi_list_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=6
            )
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
            dashboard_vbox.append(wifi_scan_box)
            await self.populate_wifi_list_async()
            dashboard_vbox.append(
                self.gtk.Separator.new(self.gtk.Orientation.HORIZONTAL)
            )
            output = await self.cli_backend.run_nmcli_device_show_async()
            devices = self.cli_backend.parse_nmcli_output(output)
            device_dashboard_label = self.gtk.Label(label="<b>Network Devices</b>")
            device_dashboard_label.set_use_markup(True)
            device_dashboard_label.set_halign(self.gtk.Align.START)
            dashboard_vbox.append(device_dashboard_label)
            device_flowbox = self.gtk.FlowBox()
            device_flowbox.set_selection_mode(self.gtk.SelectionMode.NONE)
            device_flowbox.set_max_children_per_line(2)
            device_flowbox.set_row_spacing(10)
            device_flowbox.set_column_spacing(10)
            device_flowbox.set_homogeneous(True)
            for device in devices:
                interface_name = device.get("GENERAL.DEVICE", "Unknown")
                device_type = device.get("GENERAL.TYPE", "").lower()
                state = device.get("GENERAL.STATE", "").lower()
                if "wifi" in device_type or self._is_wireless_interface(interface_name):
                    icon_name = "network-wireless-symbolic"
                    if "connected" in state or "activated" in state:
                        icon_name = "network-wireless-signal-good-symbolic"
                elif "ethernet" in device_type or "wired" in device_type:
                    icon_name = "network-wired-symbolic"
                    if "connected" in state or "activated" in state:
                        icon_name = "network-wired-activated-symbolic"
                else:
                    icon_name = "network-server-symbolic"
                device_button_box = self.gtk.Box(
                    orientation=self.gtk.Orientation.VERTICAL, spacing=5
                )
                device_button_box.add_css_class("network-dashboard-device-icon")
                icon = self.gtk.Image.new_from_icon_name(icon_name)
                icon.set_pixel_size(32)
                label = self.gtk.Label(label=interface_name)
                label.set_wrap(True)
                status_label = self.gtk.Label(
                    label=device.get("GENERAL.STATE", "Unknown").split(" (")[0]
                )
                status_label.add_css_class("dim-label")
                device_button_box.append(icon)
                device_button_box.append(label)
                device_button_box.append(status_label)
                device_button = self.gtk.Button()
                device_button.set_child(device_button_box)
                device_button.add_css_class("network-dashboard-device-button")
                device_button.connect("clicked", self.on_device_icon_clicked, device)
                self.gtk_helper.add_cursor_effect(device_button)
                flowbox_child = self.gtk.FlowBoxChild()
                flowbox_child.set_child(device_button)
                device_flowbox.append(flowbox_child)
            dashboard_vbox.append(device_flowbox)
            separator = self.gtk.Separator.new(self.gtk.Orientation.HORIZONTAL)
            dashboard_vbox.append(separator)
            config_box = self.gtk.Box(
                orientation=self.gtk.Orientation.HORIZONTAL, spacing=6
            )
            config_box.add_css_class("network-manager-config-box")
            config_label = self.gtk.Label(label="Network Settings")
            config_label.add_css_class("network-manager-config-label")
            config_button = self.gtk.Button()
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
                lambda _: self.global_loop.create_task(self.on_config_clicked_async()),
            )
            self.gtk_helper.add_cursor_effect(config_box)
            dashboard_vbox.append(config_box)
            self.stack.add_titled(dashboard_vbox, "dashboard_view", "Dashboard")
            self.detail_container = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=10
            )
            self.detail_container.set_margin_start(10)
            self.detail_container.set_margin_end(10)
            self.detail_container.set_margin_bottom(10)
            detail_scroll_window = self.gtk.ScrolledWindow()
            detail_scroll_window.set_policy(
                self.gtk.PolicyType.NEVER, self.gtk.PolicyType.AUTOMATIC
            )
            detail_scroll_window.set_child(self.detail_container)
            self.stack.add_titled(detail_scroll_window, "detail_view", "Device Details")
            main_popover_box.append(self.stack)
            return main_popover_box

        async def populate_wifi_list_async(self):
            """Populates the Wi-Fi list box with cached data or a status message."""
            while child := self.wifi_list_box.get_first_child():
                self.glib.idle_add(self.wifi_list_box.remove, child)
            connected_ssid = await self.cli_backend.get_connected_wifi_ssid_async()
            if connected_ssid and self.scan_status_label:
                self.glib.idle_add(
                    self.scan_status_label.set_label, f"Connected to: {connected_ssid}"
                )
            elif self.scan_status_label:
                self.glib.idle_add(self.scan_status_label.set_label, "Wi-Fi Networks")
            if self.scanning_in_progress and self.wifi_list_box:
                if self.scan_status_label:
                    self.glib.idle_add(self.scan_status_label.set_label, "Scanning...")
                spinner = self.gtk.Spinner(spinning=True, visible=True)
                self.glib.idle_add(self.wifi_list_box.append, spinner)
            elif self.cached_wifi_networks and self.wifi_list_box:
                last_scan_str = self.time.strftime(
                    "%H:%M:%S", self.time.localtime(self.last_scan_time)
                )
                if not connected_ssid and self.scan_status_label:
                    self.glib.idle_add(
                        self.scan_status_label.set_label,
                        f"Wi-Fi Networks (Last scan: {last_scan_str})",
                    )
                for network in self.cached_wifi_networks:
                    network_button = self.gtk.Button()
                    network_button.add_css_class("network-scan-item")
                    network_box = self.gtk.Box(
                        orientation=self.gtk.Orientation.HORIZONTAL, spacing=6
                    )
                    network_box.set_halign(self.gtk.Align.START)
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
                    signal_icon = self.gtk.Image.new_from_icon_name(icon_name)
                    network_box.append(signal_icon)
                    ssid = network.get("ssid", "Unknown SSID")
                    ssid_label = self.gtk.Label(label=f"<b>{ssid}</b>", use_markup=True)
                    ssid_label.set_halign(self.gtk.Align.START)
                    network_box.append(ssid_label)
                    if ssid == connected_ssid:
                        connected_icon = self.gtk.Image.new_from_icon_name(
                            "object-select-symbolic"
                        )
                        network_box.append(connected_icon)
                    strength_label = self.gtk.Label(label=f"{signal}%")
                    strength_label.set_halign(self.gtk.Align.END)
                    network_box.append(strength_label)
                    network_button.set_child(network_box)
                    network_button.connect(
                        "clicked", self.on_connect_button_clicked, ssid
                    )
                    self.glib.idle_add(self.wifi_list_box.append, network_button)
            elif not connected_ssid and self.scan_status_label:
                self.glib.idle_add(
                    self.scan_status_label.set_label, "No Wi-Fi networks found."
                )

        async def update_popover_async(self):
            """Update popover content after a scan, without updating the whole UI."""
            await self.populate_wifi_list_async()

        async def update_icon_and_popover(self):
            """Update icon and refresh popover content."""
            await self.update_icon_async()
            content = await self.create_scrollable_grid_content_async()
            self.glib.idle_add(self.popover.set_child, content)

        def on_connect_button_clicked(self, button, ssid):
            """UI event handler to connect to a specified Wi-Fi network."""
            self.global_loop.create_task(self._connect_to_network_async(ssid))

        async def on_config_clicked_async(self, widget=None):
            """Launches the Control Center to configure the network settings."""
            try:
                self.logger.info("Opening configuration window for network plugin.")
                env = self.os.environ.copy()
                env["XDG_CURRENT_DESKTOP"] = "GNOME"
                await self.asyncio.create_subprocess_exec(
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
                self.glib.idle_add(self.scan_status_label.set_label, "Scanning...")
            return_code, raw_output = await self.cli_backend.scan_networks_async()
            self.scanning_in_progress = False
            self.last_scan_time = self.time.time()
            self.cached_wifi_networks = []
            if return_code != 0:
                self.logger.error(f"Error executing nmcli: {return_code}")
                if self.scan_status_label:
                    self.glib.idle_add(
                        self.scan_status_label.set_label,
                        "Error: Could not scan for networks.",
                    )
                return
            output_lines = raw_output.strip().split("\n")
            if not output_lines or output_lines[0] == "":
                if self.scan_status_label:
                    self.glib.idle_add(
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
                        self.logger.error(
                            f"Skipping malformed nmcli output line: {line}"
                        )
                        continue
                self.cached_wifi_networks.append(
                    {
                        "ssid": ssid.replace("\\", ""),
                        "signal": signal,
                        "bssid": bssid,
                    }
                )
            if self.popover.get_property("visible"):
                self.global_loop.create_task(self.update_popover_async())

        async def _apply_config_autoconnect_settings_async(self):
            """Applies autoconnect settings from config via the CLI backend."""
            ssids_to_autoconnect: List[str] = self.ssids_to_auto_connect
            await self.cli_backend._apply_config_autoconnect_settings_async(
                ssids_to_autoconnect
            )

        async def _connect_to_network_async(self, ssid: str):
            """UI-side wrapper for the connection attempt."""
            self.logger.info(f"UI: Attempting connection to {ssid}")
            self.glib.idle_add(self.popover.popdown)
            await self.cli_backend._connect_to_network_async(ssid)
            await self.update_icon_and_popover()

        def code_explanation(self):
            """
            This plugin manages network status display and control using asynchronous
            operations and the NetworkManager Command Line Interface (nmcli) via a
            dedicated backend. Key aspects include:
            1. Asynchronous Networking: All network checks (`is_internet_connected_async`,
                `scan_networks_async`) are run non-blockingly using asyncio to ensure
                the panel UI remains responsive.
            2. Dynamic Icon Status: The panel icon dynamically reflects the current
                connection status (wired/Wi-Fi) and visually indicates Wi-Fi quality
                using signal strength icons (excellent, good, ok, weak).
            3. Popover Management: The `Gtk.Popover` is set up using the
                `self.create_popover` helper, which automatically connects the
                `notify::visible` signal to refresh the popover content whenever it is opened.
            4. Data Presentation (Refactored): The popover now uses a **Gtk.Stack**
                for drill-down navigation:
                - A main **Dashboard View** uses a `Gtk.FlowBox` to display network
                  devices as clickable icons, providing a visual overview.
                - Clicking a device switches the stack to a **Detail View**, populated
                  with the device's full `nmcli device show` output, enhancing user access to diagnostics.
            """
            return self.code_explanation.__doc__

    return NetworkManager
