from gi.repository import Gtk, GLib
import subprocess
from typing import Optional
from src.plugins.core._base import BasePlugin

# Enable or disable the plugin globally
ENABLE_PLUGIN = True
DEPS = ["top_panel"]

# Icon names - adjust to match your system's icon theme
ICON_CONNECTED = "notification-network-wired"
ICON_DISCONNECTED = "network-wired-disconnected-symbolic"


def get_plugin_placement(panel_instance):
    """Define where the plugin should appear."""
    return "top-panel-systray", 4


def initialize_plugin(panel_instance):
    """Initialize the Network Status plugin."""
    if ENABLE_PLUGIN:
        return NetworkMonitorPlugin(panel_instance)
    return None


# TODO: add wifi scanner or create a new  plugin that will append that content
class NetworkMonitorPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

        # UI elements
        self.button = Gtk.MenuButton()
        self.popover = Gtk.Popover()
        self.icon = ICON_DISCONNECTED

        # Set parent before setting child
        self.popover.set_parent(self.button)

        # Initialize UI
        self.init_ui()

        # Start periodic check (every 30 seconds)
        self.timeout_id = GLib.timeout_add_seconds(30, self.periodic_check)

        # Track popover visibility
        self.popover.connect("notify::visible", self.on_popover_visibility_changed)

    def init_ui(self):
        """Initialize button and popover UI."""
        self.update_icon()
        self.button.set_icon_name(self.icon)
        self.button.set_popover(self.popover)
        self.popover.set_parent(self.button)
        self.update_icon()
        self.main_widget = (self.button, "append")

    def update_icon(self):
        """Update the icon based on current connection status."""
        is_connected = self.is_internet_connected()
        self.icon = ICON_CONNECTED if is_connected else ICON_DISCONNECTED
        self.button.set_icon_name(self.icon)

    def periodic_check(self):
        """Periodically check network status."""
        self.update_icon()
        return GLib.SOURCE_CONTINUE  # Continue calling this timeout

    def on_popover_visibility_changed(self, popover, param):
        """Update content when popover becomes visible."""
        if self.popover.get_property("visible"):
            self.update_popover_content()

    def update_popover_content(self):
        """Update popover content without changing the icon."""
        content = self.create_scrollable_grid_content()
        self.popover.set_child(content)

    def on_wifi_scan_clicked(self, button):
        self.wifi_list_box.remove_all()

        networks = self.scan_wifi_networks()
        if not networks:
            empty_label = Gtk.Label(label="No networks found.")
            self.wifi_list_box.append(empty_label)
            return

        for network in networks:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            ssid_label = Gtk.Label(label=f"{network['ssid']}")
            signal_label = Gtk.Label(label=f"{network['signal']}%")
            security_label = Gtk.Label(label=f"{network['security']}")
            box.append(ssid_label)
            box.append(signal_label)
            box.append(security_label)
            self.wifi_list_box.append(box)

    def scan_wifi_networks(self):
        """Scan for available WiFi networks using nmcli."""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            lines = result.stdout.strip().split("\n")
            networks = []
            for line in lines:
                parts = line.split(":")
                if len(parts) >= 3:
                    ssid, signal, security = parts[0], parts[1], parts[2]
                    networks.append(
                        {
                            "ssid": ssid or "<unknown>",
                            "signal": int(signal),
                            "security": security,
                        }
                    )
            return networks
        except Exception as e:
            self.logger.error(f"Failed to scan WiFi networks: {e}")
            return []

    def is_internet_connected(self):
        """
        Check if internet is available.
        Returns:
            bool: True if connected, False otherwise
        """
        interface = self.get_default_interface()
        if interface and self.check_interface_carrier(interface):
            return True
        return False

    def create_scrollable_grid_content(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_width(600)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        output = self.run_nmcli_device_show()
        devices = self.parse_nmcli_output(output)

        # Store all revealers to track open/closed state
        revealers = []

        def update_scrolled_window_height(*_):
            """Update height based on whether any revealer is open."""
            if any(r.get_reveal_child() for r in revealers):
                scrolled_window.set_min_content_height(500)
            else:
                # Set height dynamically: 60px per device header
                scrolled_window.set_min_content_height(60 * len(devices))

        for idx, device in enumerate(devices):
            interface_name = device.get("GENERAL.DEVICE", "Unknown")

            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            header_label = Gtk.Label(label=f"{interface_name}")
            arrow_icon = Gtk.Image.new_from_icon_name("pan-down-symbolic")
            header_box.append(header_label)
            header_box.append(arrow_icon)

            toggle_button = Gtk.Button()
            toggle_button.set_child(header_box)

            revealer = Gtk.Revealer()
            revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
            revealer.set_reveal_child(False)
            revealer.connect("notify::reveal-child", update_scrolled_window_height)
            revealers.append(revealer)

            grid = Gtk.Grid()
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
                vbox.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

        scrolled_window.set_child(vbox)
        main_box.append(scrolled_window)

        # === START: WiFi Scan Section ===
        # FIXME: missing connect to the network?
        wifi_scan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        wifi_scan_box.set_margin_top(12)

        scan_button = Gtk.Button(label="Scan WiFi Networks")
        scan_button.connect("clicked", self.on_wifi_scan_clicked)
        wifi_scan_box.append(scan_button)

        self.wifi_list_box = Gtk.ListBox()
        self.wifi_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        wifi_scan_box.append(self.wifi_list_box)

        main_box.append(wifi_scan_box)
        # === END: WiFi Scan Section ===

        config_button = Gtk.Button(label="Configure Connections")
        config_button.connect("clicked", self.on_config_clicked)
        main_box.append(config_button)

        # Set initial size based on number of devices
        update_scrolled_window_height()

        return main_box

    def update_icon_and_popover(self):
        """Update icon and refresh popover content."""
        self.update_icon()
        content = self.create_scrollable_grid_content()
        self.popover.set_child(content)

    def on_config_clicked(self, button):
        """Launch nm-connection-editor when button is clicked."""
        try:
            subprocess.Popen(["nm-connection-editor"])
        except Exception as e:
            print(f"Failed to launch nm-connection-editor: {e}")

    def run_nmcli_device_show(self):
        """Run 'nmcli device show' and return its output."""
        try:
            result = subprocess.run(
                ["nmcli", "device", "show"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error running nmcli device show:\n{result.stderr}"
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
                    devices.append(current_device)
                    current_device = {}
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                current_device[key.strip()] = value.strip()

        if current_device:
            devices.append(current_device)

        return devices

    def get_default_interface(self) -> Optional[str]:
        """
        Get the name of the default network interface by reading `/proc/net/route`.
        Returns:
            str | None: Interface name (e.g., 'enp3s0') or None if no default route found.
        """
        try:
            with open("/proc/net/route") as f:
                for line in f.readlines():
                    parts = line.strip().split()
                    if parts[1] == "00000000":  # Default route
                        return parts[0]  # Interface name
        except Exception as e:
            print("Error reading default route:", e)
        return None

    def check_interface_carrier(self, interface: str) -> bool:
        """
        Check if a network interface is physically connected (carrier is up).

        Args:
            interface (str): The name of the network interface (e.g. 'eth0', 'enp3s0').

        Returns:
            bool: True if connected, False otherwise.
        """
        try:
            with open(f"/sys/class/net/{interface}/carrier", "r") as f:
                return f.read().strip() == "1"
        except FileNotFoundError:
            print(f"Interface '{interface}' not found.")
            return False
