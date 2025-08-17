import psutil
import gi
import subprocess
import shutil
import shlex
import tempfile
import os
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


ALL_EVENTS = [
    "view-focused",
    "view-unmapped",
    "view-mapped",
    "view-title-changed",
    "view-app-id-changed",
    "view-set-output",
    "view-workspace-changed",
    "view-geometry-changed",
    "view-tiled",
    "view-minimized",
    "view-fullscreen",
    "view-sticky",
    "wset-workspace-changed",
    "workspace-activated",
    "output-wset-changed",
    "view-wset-changed",
    "plugin-activation-state-changed",
    "output-gain-focus",
]

SELECT_EVENT_WATCH_SCRIPT = f"""
import sys
try:
    from wayfire import WayfireSocket
    from rich.pretty import pprint
    from rich import print
except ImportError as e:
    print(f"Missing dependency: {{e}}", file=sys.stderr)
    sys.exit(1)

ALL_EVENTS = {ALL_EVENTS!r}

print("Select an event to watch:")
for i, event in enumerate(ALL_EVENTS, 1):
    print(f"{{i}}: {{event}}")

selected = None
while selected is None:
    try:
        s = input("Enter event number: ").strip()
        if s.isdigit():
            idx = int(s) - 1
            if 0 <= idx < len(ALL_EVENTS):
                selected = ALL_EVENTS[idx]
            else:
                print(f"Invalid number. Please enter 1 to {{len(ALL_EVENTS)}}.")
        else:
            print("Please enter a valid number.")
    except (EOFError, KeyboardInterrupt):
        print("\\nCancelled.")
        sys.exit(0)

try:
    sock = WayfireSocket()
    sock.watch([selected])
    print(f"[bold]Watching event:[/bold] {{selected}} (press Ctrl+C to exit)")
    print("=" * 50)

    while True:
        event = sock.read_next_event()
        pprint(event)
        print()
except KeyboardInterrupt:
    print("\\n\\nExiting...")
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""


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

    def get_ram_info(self):
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        used_gb = mem.used / (1024**3)
        percent = mem.percent

        return f"({percent}%) {used_gb:.1f} / {total_gb:.0f}GB"

    def add_gpu(self):
        """Add GPU information with VRAM in GB to the list box."""
        try:
            import pyamdgpuinfo

            if pyamdgpuinfo.detect_gpus():
                gpu = pyamdgpuinfo.get_gpu(0)
                total_vram_gb = gpu.memory_info["vram_size"] / (
                    1024**3
                )  # Convert to GB
                used_vram_bytes = gpu.query_vram_usage()
                used_vram_gb = used_vram_bytes / (1024**3)  # Convert to GB
                usage_percent = (used_vram_bytes / gpu.memory_info["vram_size"]) * 100
                gpu_load = gpu.query_load()

                self.add_list_box_row("GPU", gpu.name)
                self.add_list_box_row(
                    "VRAM",
                    f"({usage_percent:.1f}%) {used_vram_gb:.1f} / {total_vram_gb:.1f} GB",
                )
                self.add_list_box_row("GPU Load", f"{gpu_load:.1f}%")
        except ImportError:
            pass  # pyamdgpuinfo not installed — skip silently
        except Exception as e:
            print(f"Error getting GPU info: {e}")
        return False

    def fetch_and_update_system_data(self):
        """Fetch system data and update the list box."""
        cpu_usage = self.get_cpu_usage()
        memory_usage = self.get_ram_info()
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
        self.add_list_box_row("RAM Usage", f"{memory_usage}")
        # AMD GPU Monitoring - Only if available
        GLib.idle_add(self.add_gpu)

        for usage in disk_usages:
            mountpoint = usage["mountpoint"]
            used = usage["used"]
            total = usage["total"]

            self.add_list_box_row(f"Disk ({mountpoint})", f"{used:.1f} / {total:.0f}GB")
        self.add_list_box_row("Network", network_usage)
        if battery_status is not None:
            self.add_list_box_row("Battery", battery_status)

        if focused_view:
            self.add_list_box_row(
                "Exec", self.get_process_executable(focused_view["pid"])
            )
            self.add_list_box_row(
                "APP ID", f"({focused_view['app-id']}): {focused_view['id']}"
            )
            hbox = self.add_list_box_row("APP PID", focused_view["pid"])
            hbox.set_tooltip_text("Right click to kill process")
            if process_usage:
                self.add_list_box_row("Win Memory Usage", process_usage["memory_usage"])
            if process_disk_usage:
                self.add_list_box_row("Win Disk Read", process_disk_usage["read_bytes"])
                self.add_list_box_row(
                    "APP Disk Write", process_disk_usage["write_bytes"]
                )
                self.add_list_box_row(
                    "APP Disk Read Count", str(process_disk_usage["read_count"])
                )
                self.add_list_box_row(
                    "APP Disk Write Count", str(process_disk_usage["write_count"])
                )

        self.add_list_box_row("Watch events", "all")

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
        """Get disk usage for all mounted partitions with values in GB."""
        disk_usages = []
        for part in psutil.disk_partitions(all=False):  # Exclude special devices
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_usages.append(
                    {
                        "mountpoint": part.mountpoint,
                        "total": round(
                            usage.total / (1024**3), 1
                        ),  # Convert to GB with 1 decimal
                        "used": round(
                            usage.used / (1024**3), 1
                        ),  # Convert to GB with 1 decimal
                        "free": round(
                            usage.free / (1024**3), 1
                        ),  # Convert to GB with 1 decimal
                        "percent": round(usage.percent, 1),  # Percentage with 1 decimal
                    }
                )
            except (PermissionError, psutil.AccessDenied):
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
        return None

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

    def open_system_monitor(self):
        subprocess.Popen(["gnome-system-monitor"])

    # FIXME: make it work for other gpu tools too
    def open_terminal_with_amdgpu_top(self, *__):
        """
        Open a terminal (kitty or alacritty) with amdgpu_top for GPU monitoring.

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

        # Check if amdgpu_top is installed
        if not shutil.which("amdgpu_top"):
            print("Error: amdgpu_top is not installed.")
            return False

        try:
            # Launch the terminal with amdgpu_top
            subprocess.Popen(terminal_command + ["-e", "amdgpu_top"])
            print(f"Launched {terminal_command[0]} with amdgpu_top.")
            return True
        except Exception as e:
            print(f"Error launching terminal: {e}")
            return False

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

    def open_kitty_with_prompt_and_watch_selected_event(self, *__):
        def is_installed(cmd):
            return shutil.which(cmd) is not None

        if not is_installed("kitty"):
            self.logger.info("kitty terminal is not installed.")
            return

        if not is_installed("ipython") and not is_installed("python"):
            self.logger.error("Neither ipython nor python is available.")
            return

        # Build the script content

        # Write to temp file
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".py", text=True)
            os.write(fd, SELECT_EVENT_WATCH_SCRIPT.encode("utf-8"))
            os.close(fd)

            # Choose runner: prefer ipython if available
            if is_installed("ipython"):
                cmd = ["ipython", temp_path]
            else:
                cmd = ["python", temp_path]

            # Launch kitty with the command, then drop into shell on exit
            full_bash_cmd = f"{' '.join(map(shlex.quote, cmd))}; exec bash"

            subprocess.Popen(["kitty", "bash", "-c", full_bash_cmd])

            # Optional: clean up later? Or let OS handle it.
            # You could spawn a delayed cleanup, but risky if still in use.
        except Exception as e:
            self.logger.error(f"Failed to create or run script: {e}")

    def open_kitty_with_rich_events_view(self, *__):
        def is_installed(cmd):
            return shutil.which(cmd) is not None

        if not is_installed("python3"):
            self.logger.info("python3 is not installed.")
            return

        terminal = None
        if is_installed("kitty"):
            terminal = "kitty"
        elif is_installed("alacritty"):
            terminal = "alacritty"
        else:
            self.logger.info(
                "Neither kitty nor alacritty terminal emulators are installed."
            )
            return

        # Comando Python em string para passar ao ipython -c
        python_cmd = (
            "from wayfire import WayfireSocket; "
            "from rich.pretty import pprint; "
            "from rich import print; "
            "sock=WayfireSocket(); "
            "sock.watch(); "
            "print('[bold]Wayfire Events Monitor[/bold] (press Ctrl+C to exit)'); "
            "print('='*40); "
            "import itertools; "
            "[(pprint(sock.read_next_event()), print()) for _ in itertools.repeat(None)]"
        )

        # Monta o comando ipython -c "python_cmd" como string única
        full_cmd = f"ipython -c {shlex.quote(python_cmd)}"

        if terminal == "kitty":
            subprocess.Popen([terminal, "bash", "-c", f"{full_cmd}; exec bash"])
        else:  # alacritty
            subprocess.Popen([terminal, "-e", "bash", "-c", f"{full_cmd}; exec bash"])

    def open_kitty_with_ipython_view(self, view):
        def is_installed(cmd):
            return shutil.which(cmd) is not None

        if not is_installed("ipython"):
            self.logger.info("ipython is not installed.")
            return

        terminal = None
        if is_installed("kitty"):
            terminal = "kitty"
        elif is_installed("alacritty"):
            terminal = "alacritty"
        else:
            self.logger.info(
                "Neither kitty nor alacritty terminal emulators are installed."
            )
            return

        view_id = view["id"]
        code = (
            "from wayfire import WayfireSocket; "
            "sock = WayfireSocket(); "
            f"id = {view_id};"
            f"view = sock.get_view({view_id});"
            "view;"
        )
        cmd = f'ipython -i -c "{code}"'

        if terminal == "kitty":
            subprocess.Popen([terminal, "bash", "-c", f"{cmd} ; exec bash"])
        else:  # alacritty
            subprocess.Popen([terminal, "-e", "bash", "-c", f"{cmd} ; exec bash"])

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

    def create_gesture_for_amdgpu_top(self, hbox):
        """Create a gesture to launch amdgpu_top in a terminal."""
        create_gesture = self.plugins["gestures_setup"].create_gesture
        create_gesture(
            hbox,
            1,
            self.open_terminal_with_amdgpu_top,
        )

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
            create_gesture(
                hbox,
                2,
                lambda _, pid=last_view_pid: self.open_system_monitor(),
            )
            create_gesture(
                hbox,
                3,
                lambda _, pid=last_view_pid: self.kill_process(pid),
            )

    def kill_process(self, pid):
        try:
            p = psutil.Process(pid)
            p.terminate()
            p.wait(3)
        except psutil.NoSuchProcess:
            pass

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

    def create_watch_events_gesture(self, hbox):
        create_gesture = self.plugins["gestures_setup"].create_gesture
        create_gesture(
            hbox,
            1,
            self.open_kitty_with_rich_events_view,
        )
        create_gesture(hbox, 3, self.open_kitty_with_prompt_and_watch_selected_event)

    def create_gesture_for_focused_view_id(self, hbox):
        focused_view = self.last_toplevel_focused_view()
        if focused_view is not None:
            last_view_id = focused_view["id"]
            create_gesture = self.plugins["gestures_setup"].create_gesture
            create_gesture(
                hbox,
                1,
                lambda _, id=last_view_id: self.open_kitty_with_ipython_view(
                    focused_view
                ),
            )

    def add_list_box_row(self, name, value):
        """Add a row to the ListBox."""
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=10)
        if "APP PID" in name:
            self.create_gesture_for_focused_view_pid(hbox)
        if "APP ID" in name:
            self.create_gesture_for_focused_view_id(hbox)
        if "APP Disk" in name:
            self.create_iotop_gesture_for_focused_view_pid(hbox)

        if "GPU" in name:
            self.create_gesture_for_amdgpu_top(hbox)
        if "Watch events" in name:
            self.create_watch_events_gesture(hbox)

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
        return hbox

    def popover_is_open(self, *_):
        """Callback when the popover is opened."""

    def popover_is_closed(self, *_):
        """Callback when the popover is closed."""
        self.stop_system_updates()
