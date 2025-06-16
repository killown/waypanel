import psutil
import gi
import subprocess
import shutil
from src.plugins.core._base import BasePlugin

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Adw, Pango

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-systray"
    order = 2
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the system monitor plugin.

    Args:
        obj: The main panel object (Panel instance).
        app: The main application instance.
    """
    if ENABLE_PLUGIN:
        return SystemMonitorPlugin(panel_instance)


class SystemMonitorPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.obj = panel_instance
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
        self.main_widget = (self.menubutton_system, "append")

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

    def add_gpu(self):
        try:
            import pyamdgpuinfo

            if pyamdgpuinfo.detect_gpus():
                gpu = pyamdgpuinfo.get_gpu(0)
                total_vram_mb = round(gpu.memory_info["vram_size"] / (1024 * 1024))
                used_vram_bytes = round(gpu.query_vram_usage())
                gpu_load = gpu.query_load()
                used_vram_mb = used_vram_bytes / (1024 * 1024)
                usage_percent = (used_vram_bytes / gpu.memory_info["vram_size"]) * 100
                self.add_list_box_row("GPU", gpu.name)
                self.add_list_box_row(
                    "VRAM", f"{used_vram_mb:.2f}/{total_vram_mb:.2f} MB"
                )
                self.add_list_box_row("GFX", f"{gpu_load:.2f}%")
                self.add_list_box_row("VRAM Usage", f"{usage_percent:.2f}%")
        except ImportError:
            pass  # pyamdgpuinfo not installed — skip silently
        return False

    def fetch_and_update_system_data(self):
        """Fetch system data and update the list box."""
        cpu_usage = self.get_cpu_usage()
        memory_usage = self.get_memory_usage()
        disk_usages = self.get_disk_usages()
        network_usage = self.get_network_usage()
        battery_status = self.get_battery_status()
        focused_view = self.last_toplevel_focused_view()
        process_usage = None
        process_disk_usage = None

        if focused_view:
            process_usage = self.get_process_usage(focused_view["pid"])
            process_disk_usage = self.get_process_disk_usage(focused_view["pid"])

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
        # AMD GPU Monitoring - Only if available
        GLib.idle_add(self.add_gpu)

        for usage in disk_usages:
            self.add_list_box_row(
                f"Disk ({usage['mountpoint']})", f"{usage['percent']}%"
            )
        self.add_list_box_row("Network", network_usage)
        self.add_list_box_row("Battery", battery_status)

        if focused_view:
            self.add_list_box_row(
                "Exec", self.get_process_executable(focused_view["pid"])
            )
            self.add_list_box_row("Win ID", focused_view["id"])
            self.add_list_box_row("Win PID", focused_view["pid"])
            if process_usage:
                self.add_list_box_row("Win Memory Usage", process_usage["memory_usage"])
            if process_disk_usage:
                self.add_list_box_row("Win Disk Read", process_disk_usage["read_bytes"])
                self.add_list_box_row(
                    "Win Disk Write", process_disk_usage["write_bytes"]
                )
                self.add_list_box_row(
                    "Win Disk Read Count", str(process_disk_usage["read_count"])
                )
                self.add_list_box_row(
                    "Win Disk Write Count", str(process_disk_usage["write_count"])
                )

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

    def get_process_disk_usage(self, pid):
        """
        Get the disk I/O usage for a given process PID using psutil.

        Args:
            pid (int): The process ID to monitor.

        Returns:
            dict: A dictionary containing 'read_bytes', 'write_bytes',
                  'read_count', and 'write_count' for the given PID,
                  or None if the PID is invalid or inaccessible.
        """
        try:
            # Check if the PID exists
            if not psutil.pid_exists(pid):
                print(f"No process found with PID: {pid}")
                return None

            # Get the process object
            process = psutil.Process(pid)

            # Retrieve I/O counters for the process
            io_counters = process.io_counters()

            # Extract disk I/O statistics
            disk_usage = {
                "read_bytes": self.format_bytes(io_counters.read_bytes),
                "write_bytes": self.format_bytes(io_counters.write_bytes),
                "read_count": io_counters.read_count,
                "write_count": io_counters.write_count,
            }

            return disk_usage

        except psutil.NoSuchProcess:
            print(f"Process with PID {pid} no longer exists.")
            return None
        except psutil.AccessDenied:
            print(f"Access denied for process with PID: {pid}")
            return None
        except Exception as e:
            print(f"Error retrieving disk usage for PID {pid}: {e}")
            return None

    def get_process_usage(self, pid):
        """
        Get the CPU and memory usage for a given process PID using psutil.

        Args:
            pid (int): The process ID to monitor.

        Returns:
            dict: A dictionary containing 'cpu_usage' and 'memory_usage' for the given PID,
                  or None if the PID is invalid or inaccessible.
        """
        try:
            # Check if the PID is valid and the process exists
            if not psutil.pid_exists(pid):
                print(f"No process found with PID: {pid}")
                return None
            # Get the process object
            process = psutil.Process(pid)
            memory_info = process.memory_info()
            memory_usage = memory_info.rss / (1024 * 1024)  # Convert bytes to MB

            return {
                "memory_usage": f"{memory_usage:.2f} MB",
            }
        except psutil.NoSuchProcess:
            print(f"Process with PID {pid} no longer exists.")
            return None
        except Exception as e:
            print(f"Error retrieving process usage for PID {pid}: {e}")
            return None

    def open_terminal_with_htop(self, pid):
        """
        Open a terminal (kitty or alacritty) with htop monitoring the specified PID.

        Args:
            pid (int): The process ID to monitor with htop.

        Returns:
            bool: True if the terminal was successfully opened, False otherwise.
        """
        # Check if kitty is installed
        if shutil.which("kitty"):
            terminal_command = ["kitty"]
        # Fallback to alacritty if kitty is not available
        elif shutil.which("alacritty"):
            terminal_command = ["alacritty"]
        else:
            print("Error: Neither kitty nor alacritty is installed.")
            return False

        # Construct the command to run htop with the given PID
        htop_command = ["htop", "-p", str(pid)]

        # Combine the terminal command with htop command
        full_command = terminal_command + ["-e"] + htop_command

        try:
            # Launch the terminal with htop
            subprocess.Popen(full_command)
            print(f"Launched {terminal_command[0]} with htop monitoring PID {pid}.")
            return True
        except Exception as e:
            print(f"Error launching terminal: {e}")
            return False

    def open_terminal_with_iotop(self, pid):
        """
        Open a terminal (kitty or alacritty) with iotop monitoring the specified PID.

        Args:
            pid (int): The process ID to monitor with iotop.

        Returns:
            bool: True if the terminal was successfully opened, False otherwise.
        """
        # Check if kitty is installed
        if shutil.which("kitty"):
            terminal_command = ["kitty"]
        # Fallback to alacritty if kitty is not available
        elif shutil.which("alacritty"):
            terminal_command = ["alacritty"]
        else:
            print("Error: Neither kitty nor alacritty is installed.")
            return False

        # Construct the command to run htop with the given PID
        htop_command = ["sudo", "iotop", "-p", str(pid)]
        self.utils.notify_send(
            "iotop command",
            f"iotop requires permissions to monitor disk usage from the given PID:{pid}",
        )
        # Combine the terminal command with iotop command
        full_command = terminal_command + ["-e"] + htop_command

        try:
            # Launch the terminal with iotop

            subprocess.Popen(full_command)
            print(f"Launched {terminal_command[0]} with iotop monitoring PID {pid}.")
            return True
        except Exception as e:
            print(f"Error launching terminal: {e}")
            return False

    def open_view_info_window(self, id):
        try:
            # Fetch the view details using the provided ID
            view = self.ipc.get_view(id)
            if not view:
                raise ValueError(f"No view found with ID: {id}")

            # Create a new window
            window = Gtk.Window(title=f"View Information (ID: {id})")
            window.set_default_size(600, 400)
            window.set_resizable(True)

            # Create a scrollable window
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_vexpand(True)
            scrolled_window.set_hexpand(True)

            # Create ListStore with two string columns: key and value
            list_store = Gtk.ListStore(str, str)

            # Populate the ListStore
            for key, value in view.items():
                # Format the value appropriately
                if isinstance(value, dict):
                    formatted_value = "\n".join(f"{k}: {v}" for k, v in value.items())
                elif isinstance(value, list):
                    formatted_value = "\n".join(str(item) for item in value)
                else:
                    formatted_value = str(value)

                list_store.append([key, formatted_value])

            # Create TreeView
            tree_view = Gtk.TreeView(model=list_store)

            # Create Key column
            key_renderer = Gtk.CellRendererText()
            key_column = Gtk.TreeViewColumn("Key", key_renderer, text=0)
            key_column.set_resizable(True)
            key_column.set_min_width(150)
            key_column.set_sort_column_id(0)
            tree_view.append_column(key_column)

            # Create Value column
            value_renderer = Gtk.CellRendererText()
            value_renderer.props.wrap_mode = Pango.WrapMode.WORD_CHAR
            value_renderer.props.wrap_width = 400  # Wrap after 400 pixels
            value_column = Gtk.TreeViewColumn("Value", value_renderer, text=1)
            value_column.set_resizable(True)
            value_column.set_expand(True)
            value_column.set_sort_column_id(1)
            tree_view.append_column(value_column)

            # Enable text selection
            tree_view.set_activate_on_single_click(True)

            scrolled_window.set_child(tree_view)
            window.set_child(scrolled_window)
            window.present()

        except Exception as e:
            # Handle errors gracefully
            error_dialog = Adw.MessageDialog(
                transient_for=self.obj.main_window,
                heading="Error Retrieving View Information",
                body=str(e),
            )
            error_dialog.add_response("close", "_Close")
            error_dialog.set_default_response("close")
            error_dialog.set_close_response("close")
            error_dialog.present()

    def get_process_executable(self, pid):
        """
        Get the executable path of a process by its PID.

        Args:
            pid (int): The process ID.

        Returns:
            str: The absolute path to the process executable, or None if the process doesn't exist or access is denied.
        """
        try:
            # Create a Process object for the given PID
            process = psutil.Process(pid)

            # Retrieve the executable path
            executable_path = process.exe()

            return executable_path
        except psutil.NoSuchProcess:
            print(f"No process found with PID: {pid}")
            return None
        except psutil.AccessDenied:
            print(f"Access denied for process with PID: {pid}")
            return None
        except Exception as e:
            print(f"Error retrieving executable path for PID {pid}: {e}")
            return None

    def format_value(self, value):
        """
        Format nested dictionaries and other complex values for display.

        Args:
            value: The value to format.

        Returns:
            str: A formatted string representation of the value.
        """
        if isinstance(value, dict):
            return "\n".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, bool):
            return "Yes" if value else "No"
        elif isinstance(value, int) and value == -1:
            return "N/A"
        return str(value)

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

    def last_toplevel_focused_view(self):
        # requires taskbar plugin to get the last focused view
        taskbar = self.plugins["taskbar"]
        return taskbar.last_toplevel_focused_view

    def create_gesture_for_focused_view_pid(self, hbox):
        focused_view = self.last_toplevel_focused_view()
        if focused_view is not None:
            last_view_pid = focused_view["pid"]
            create_gesture = self.plugins["gestures_setup"].create_gesture
            create_gesture(
                hbox,
                1,
                lambda _, pid=last_view_pid: self.open_terminal_with_htop(pid),
            )

    def create_iotop_gesture_for_focused_view_pid(self, hbox):
        focused_view = self.last_toplevel_focused_view()
        if focused_view is not None:
            last_view_pid = focused_view["pid"]
            create_gesture = self.plugins["gestures_setup"].create_gesture
            create_gesture(
                hbox,
                1,
                lambda _, pid=last_view_pid: self.open_terminal_with_iotop(pid),
            )

    def create_gesture_for_focused_view_id(self, hbox):
        focused_view = self.last_toplevel_focused_view()
        if focused_view is not None:
            last_view_id = focused_view["id"]
            create_gesture = self.plugins["gestures_setup"].create_gesture
            create_gesture(
                hbox,
                1,
                lambda _, id=last_view_id: self.open_view_info_window(id),
            )

    def add_list_box_row(self, name, value):
        """Add a row to the ListBox."""
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=10)
        if "Win PID" in name:
            self.create_gesture_for_focused_view_pid(hbox)
        if "Win ID" in name:
            self.create_gesture_for_focused_view_id(hbox)
        if "Win Disk" in name:
            self.create_iotop_gesture_for_focused_view_pid(hbox)

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
