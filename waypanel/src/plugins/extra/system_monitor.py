import psutil
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def position():
    """Define the plugin's position and order."""
    position = "right"  # Can be "left", "right", or "center"
    order = 2  # Lower numbers have higher priority
    return position, order


def initialize_plugin(obj, app):
    """Initialize the system monitor plugin.

    Args:
        obj: The main panel object (Panel instance).
        app: The main application instance.
    """
    if ENABLE_PLUGIN:
        return SystemMonitorPlugin(obj, app)


class SystemMonitorPlugin:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app
        self.popover_system = None
        self.update_timeout_id = None
        self.update_interval = 2  # Update interval in seconds
        self.prev_net_io = psutil.net_io_counters()

        self.create_menu_popover_system()

    def create_menu_popover_system(self):
        """Create the system monitor button and popover."""
        # Create the system monitor button
        self.menubutton_system = Gtk.Button()
        self.menubutton_system.set_icon_name("utilities-system-monitor")  # Default icon
        self.menubutton_system.connect("clicked", self.open_popover_system)

        # Add the button to the systray
        if hasattr(self.obj, "top_panel_box_right"):
            self.obj.top_panel_box_systray.append(self.menubutton_system)
        else:
            print("Error: top_panel_box_right not found in Panel object.")

    def start_system_updates(self):
        """Start periodic updates for system data."""
        # Fetch data immediately for the first time
        self.fetch_and_update_system_data()

        # Schedule periodic updates
        self.update_timeout_id = GLib.timeout_add_seconds(
            self.update_interval, self.fetch_and_update_system_data
        )

    def stop_system_updates(self):
        """Stop periodic updates for system data."""
        if self.update_timeout_id:
            GLib.source_remove(self.update_timeout_id)
            self.update_timeout_id = None

    def fetch_and_update_system_data(self):
        """Fetch system data and update the list box."""
        cpu_usage = self.get_cpu_usage()
        memory_usage = self.get_memory_usage()
        disk_usages = self.get_disk_usages()
        network_usage = self.get_network_usage()
        battery_status = self.get_battery_status()

        # Clear existing rows
        child = self.list_box.get_first_child()
        while child:
            next_child = (
                child.get_next_sibling()
            )  # Get the next sibling before removing
            self.list_box.remove(child)
            child = next_child

        # Add new rows to the list box
        self.add_list_box_row("CPU Usage", f"{cpu_usage}%")
        self.add_list_box_row("Memory Usage", f"{memory_usage}%")
        for usage in disk_usages:
            self.add_list_box_row(
                f"Disk ({usage['mountpoint']})", f"{usage['percent']}%"
            )
        self.add_list_box_row("Network", network_usage)
        self.add_list_box_row("Battery", battery_status)

        # Return True to keep the timeout active
        return self.popover_system and self.popover_system.is_visible()

    def get_cpu_usage(self):
        """Get current CPU usage."""
        return psutil.cpu_percent(interval=None)

    def get_memory_usage(self):
        """Get current memory usage."""
        mem = psutil.virtual_memory()
        return mem.percent

    def get_disk_usages(self):
        """Get disk usage for all mounted partitions."""
        disk_usages = []
        for part in psutil.disk_partitions(all=False):  # Exclude loop devices etc.
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_usages.append(
                    {"mountpoint": part.mountpoint, "percent": usage.percent}
                )
            except PermissionError:
                continue
        return disk_usages

    def get_network_usage(self):
        """Get current network usage."""
        current_net_io = psutil.net_io_counters()
        upload_speed = (
            current_net_io.bytes_sent - self.prev_net_io.bytes_sent
        ) / self.update_interval
        download_speed = (
            current_net_io.bytes_recv - self.prev_net_io.bytes_recv
        ) / self.update_interval
        self.prev_net_io = current_net_io
        return f"Up: {self.format_bytes(upload_speed)}/s, Down: {self.format_bytes(download_speed)}/s"

    def get_battery_status(self):
        """Get current battery status."""
        battery = psutil.sensors_battery()
        if battery:
            plugged = "Plugged" if battery.power_plugged else "Not Plugged"
            percent = battery.percent
            return f"{percent}% ({plugged})"
        return "No battery"

    def format_bytes(self, bytes_count):
        """Format bytes into a human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_count < 1024:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f} PB"

    def open_popover_system(self, *_):
        """Handle opening the system monitor popover."""
        if self.popover_system and self.popover_system.is_visible():
            self.popover_system.popdown()
            self.stop_system_updates()
        elif self.popover_system and not self.popover_system.is_visible():
            self.popover_system.popup()
            self.start_system_updates()
        else:
            self.create_popover_system()
            self.popover_system.popup()
            self.start_system_updates()

    def create_popover_system(self):
        """Create the system monitor popover and populate it with a ListBox."""
        # Create the popover
        self.popover_system = Gtk.Popover.new()

        # Create a vertical box to hold the ListBox
        vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_size_request(250, -1)

        # Create a ListBox to display system information
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)  # Disable selection
        vbox.append(self.list_box)

        # Set the box as the child of the popover
        self.popover_system.set_child(vbox)

        # Set the parent widget of the popover and display it
        self.popover_system.set_parent(self.menubutton_system)

    def add_list_box_row(self, name, value):
        """Add a row to the ListBox."""
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_halign(Gtk.Align.FILL)
        hbox.set_margin_top(5)
        hbox.set_margin_bottom(5)

        # Add name label
        name_label = Gtk.Label(label=name)
        name_label.set_halign(Gtk.Align.START)
        name_label.set_hexpand(True)
        hbox.append(name_label)

        # Add value label
        value_label = Gtk.Label(label=value)
        value_label.set_halign(Gtk.Align.END)
        hbox.append(value_label)

        row.set_child(hbox)
        self.list_box.append(row)

    def popover_is_open(self, *_):
        """Callback when the popover is opened."""

    def popover_is_closed(self, *_):
        """Callback when the popover is closed."""
        self.stop_system_updates()
