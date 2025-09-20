from gi.repository import Gtk, GLib
import subprocess
from typing import Optional
from src.plugins.core._base import BasePlugin

# Enable or disable the plugin globally
ENABLE_PLUGIN = True
DEPS = ["top_panel", "gestures_setup"]


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
        self.icon_connected = self.utils.set_widget_icon_name(
            None,
            [
                "gnome-dev-network-symbolic",
                "org.gnome.Settings-network-symbolic",
                "network-wired-activated-symbolic",
                "network-wired-symbolic",
            ],
        )
        self.icon_disconnected = self.utils.set_widget_icon_name(
            None, ["network-wired-disconnected-symbolic"]
        )
        self.icon = self.icon_disconnected

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
        self.utils.add_cursor_effect(self.button)
        self.popover.set_parent(self.button)
        self.update_icon()
        self.main_widget = (self.button, "append")

    def update_icon(self):
        """Update the icon based on current connection status."""
        is_connected = self.is_internet_connected()
        self.icon = self.icon_connected if is_connected else self.icon_disconnected
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
        main_box.add_css_class("network-manager-container")
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.add_css_class("network-manager-scrolledwindow")
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
            self.utils.set_widget_icon_name(
                None,
                ["gnome-control-center-symbolic", "org.gnome.Settings"],
            )
        )
        config_box.append(config_button)
        config_box.append(config_label)
        self.utils.add_cursor_effect(config_button)
        self.plugins["gestures_setup"].create_gesture(
            config_box, 1, self.on_config_clicked
        )
        self.utils.add_cursor_effect(config_box)
        main_box.append(config_box)

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
            subprocess.Popen(
                "env XDG_CURRENT_DESKTOP=GNOME gnome-control-center network".split()
            )
            self.popover.popdown()
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
            provides a button to launch the `gnome-control-center` for
            network settings.
        """
        return self.code_explanation.__doc__
