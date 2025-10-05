ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-systray"
    order = 5
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the system monitor plugin.
    Args:
        obj: The main panel object (Panel instance).
        app: The main application instance.
    """
    if ENABLE_PLUGIN:
        system_monitor = call_plugin_class()
        return system_monitor(panel_instance)


def call_plugin_class():
    import psutil
    import shutil
    import shlex
    import tempfile
    from src.plugins.core._base import BasePlugin

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
        "output-layout-changed",
        "view-wset-changed",
        "plugin-activation-state-changed",
        "output-gain-focus",
    ]
    SELECT_EVENT_WATCH_SCRIPT = f"""
    import sys
    import os # Added os import for stderr check
    try:
        from wayfire import WayfireSocket
        from rich.pretty import pprint # Changed pself.logger.error to pprint
        from rich.console import Console # Changed rich import
        console = Console()
    except ImportError as e:
        print(f"Missing dependency: {{e}}", file=sys.stderr)
        sys.exit(1)
    ALL_EVENTS = {ALL_EVENTS!r}
    console.print("[bold]Select an event to watch:[/bold]") # Using console.print
    for i, event in enumerate(ALL_EVENTS, 1):
        console.print(f"{{i}}: {{event}}") # Using console.print
    selected = None
    while selected is None:
        try:
            s = input("Enter event number: ").strip()
            if s.isdigit():
                idx = int(s) - 1
                if 0 <= idx < len(ALL_EVENTS):
                    selected = ALL_EVENTS[idx]
                else:
                    console.print(f"[red]Invalid number. Please enter 1 to {{len(ALL_EVENTS)}}.[/red]", file=sys.stderr)
            else:
                console.print("[red]Please enter a valid number.[/red]", file=sys.stderr)
        except (EOFError, KeyboardInterrupt):
            console.print("\\nCancelled.")
            sys.exit(0)
    try:
        sock = WayfireSocket()
        sock.watch([selected])
        console.print(f"[bold]Watching event:[/bold] {{selected}} (press Ctrl+C to exit)")
        console.print("=" * 50)
        while True:
            event = sock.read_next_event()
            pprint(event) # Using pprint
            console.print()
    except KeyboardInterrupt:
        console.print("\\n\\nExiting...")
    except Exception as e:
        console.print(f"[red]Error: {{e}}[/red]", file=sys.stderr)
        sys.exit(1)
    """

    class SystemMonitorPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover_system = None
            self.update_timeout_id = None
            self.update_interval = 2
            self.prev_net_io = psutil.net_io_counters()
            self.create_menu_popover_system()

        def create_menu_popover_system(self):
            """Create the system monitor button and popover."""
            self.menubutton_system = self.gtk.Button()
            icon_name = self.gtk_helper.icon_exist(
                "system-monitor-app-symbolic",
                [
                    "utilities-system-monitor-symbolic",
                    "com.github.stsdc.monitor-symbolic",
                    "utilities-system-monitor-symbolic",
                    "system-monitor-app-symbolic",
                ],
            )
            self.menubutton_system.set_icon_name(icon_name)
            self.menubutton_system.connect("clicked", self.open_popover_system)
            self.gtk_helper.add_cursor_effect(self.menubutton_system)
            self.main_widget = (self.menubutton_system, "append")

        def start_system_updates(self):
            """Start periodic updates for system data."""
            self.fetch_and_update_system_data()
            self.update_timeout_id = self.glib.timeout_add_seconds(
                self.update_interval, self.fetch_and_update_system_data
            )

        def stop_system_updates(self):
            """Stop periodic updates for system data."""
            if self.update_timeout_id:
                self.glib.source_remove(self.update_timeout_id)
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
                    total_vram_gb = gpu.memory_info["vram_size"] / (1024**3)
                    used_vram_bytes = gpu.query_vram_usage()
                    used_vram_gb = used_vram_bytes / (1024**3)
                    usage_percent = (
                        used_vram_bytes / gpu.memory_info["vram_size"]
                    ) * 100
                    gpu_load = gpu.query_load()
                    self.add_list_box_row("GPU", gpu.name)
                    self.add_list_box_row(
                        "VRAM",
                        f"({usage_percent:.1f}%) {used_vram_gb:.1f} / {total_vram_gb:.1f} GB",
                    )
                    self.add_list_box_row("GPU Load", f"{gpu_load:.1f}%")
            except ImportError:
                pass
            except Exception as e:
                self.logger.error(f"Error getting GPU info: {e}")
            return False

        def fetch_and_update_system_data(self):
            """Fetch system data and update the list box."""
            cpu_usage = self.get_cpu_usage()
            memory_usage = self.get_ram_info()
            disk_usages = self.get_disk_usages()
            network_usage = self.get_network_usage()
            battery_status = self.get_battery_status()
            focused_view_id = self._wf_helper.get_the_last_focused_view_id()
            focused_view = self.ipc.get_view(focused_view_id)
            process_usage = None
            process_disk_usage = None
            if focused_view:
                process_usage = self.get_process_usage(focused_view["pid"])
                process_disk_usage = self.get_process_disk_usage(focused_view["pid"])
            child = self.list_box.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.list_box.remove(child)
                child = next_child
            self.add_list_box_row("CPU Usage", f"{cpu_usage}%")
            self.add_list_box_row("RAM Usage", f"{memory_usage}")
            self.glib.idle_add(self.add_gpu)
            for usage in disk_usages:
                mountpoint = usage["mountpoint"]
                used = usage["used"]
                total = usage["total"]
                self.add_list_box_row(
                    f"Disk ({mountpoint})", f"{used:.1f} / {total:.0f}GB"
                )
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
                    self.add_list_box_row(
                        "Win Memory Usage", process_usage["memory_usage"]
                    )
                if process_disk_usage:
                    self.add_list_box_row(
                        "Win Disk Read", process_disk_usage["read_bytes"]
                    )
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
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk_usages.append(
                        {
                            "mountpoint": part.mountpoint,
                            "total": round(usage.total / (1024**3), 1),
                            "used": round(usage.used / (1024**3), 1),
                            "free": round(usage.free / (1024**3), 1),
                            "percent": round(usage.percent, 1),
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
                if not psutil.pid_exists(pid):
                    self.logger.error(f"No process found with PID: {pid}")
                    return None
                process = psutil.Process(pid)
                io_counters = process.io_counters()
                disk_usage = {
                    "read_bytes": self.format_bytes(io_counters.read_bytes),
                    "write_bytes": self.format_bytes(io_counters.write_bytes),
                    "read_count": io_counters.read_count,
                    "write_count": io_counters.write_count,
                }
                return disk_usage
            except psutil.NoSuchProcess:
                self.logger.error(f"Process with PID {pid} no longer exists.")
                return None
            except psutil.AccessDenied:
                self.logger.error(f"Access denied for process with PID: {pid}")
                return None
            except Exception as e:
                self.logger.error(f"Error retrieving disk usage for PID {pid}: {e}")
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
                if not psutil.pid_exists(pid):
                    self.logger.error(f"No process found with PID: {pid}")
                    return None
                process = psutil.Process(pid)
                memory_info = process.memory_info()
                memory_usage = memory_info.rss / (1024 * 1024)
                return {
                    "memory_usage": f"{memory_usage:.2f} MB",
                }
            except psutil.NoSuchProcess:
                self.logger.error(f"Process with PID {pid} no longer exists.")
                return None
            except Exception as e:
                self.logger.error(f"Error retrieving process usage for PID {pid}: {e}")
                return None

        def open_system_monitor(self):
            self.run_cmd("gnome-system-monitor")

        def open_terminal_with_amdgpu_top(self, *__):
            """
            Open a terminal (kitty or alacritty) with amdgpu_top for GPU monitoring.
            Returns:
                bool: True if the terminal was successfully opened, False otherwise.
            """
            if shutil.which("kitty"):
                terminal_command = "kitty"
            elif shutil.which("alacritty"):
                terminal_command = "alacritty"
            else:
                self.logger.error("Error: Neither kitty nor alacritty is installed.")
                return False
            if not shutil.which("amdgpu_top"):
                self.logger.error("Error: amdgpu_top is not installed.")
                return False
            try:
                self.run_cmd(f"{terminal_command} -e amdgpu_top")
                return True
            except Exception as e:
                self.logger.error(f"Error launching terminal: {e}")
                return False

        def open_terminal_with_htop(self, pid):
            """
            Open a terminal (kitty or alacritty) with htop monitoring the specified PID.
            Args:
                pid (int): The process ID to monitor with htop.
            Returns:
                bool: True if the terminal was successfully opened, False otherwise.
            """
            if shutil.which("kitty"):
                terminal_command = "kitty"
            elif shutil.which("alacritty"):
                terminal_command = "alacritty"
            else:
                self.logger.error("Error: Neither kitty nor alacritty is installed.")
                return False
            htop_command = f"htop -p {pid}"
            full_command = f"{terminal_command} -e {htop_command}"
            try:
                self.run_cmd(full_command)
                return True
            except Exception as e:
                self.logger.error(f"Error launching terminal: {e}")
                return False

        def open_terminal_with_iotop(self, pid):
            """
            Open a terminal (kitty or alacritty) with iotop monitoring the specified PID.
            Args:
                pid (int): The process ID to monitor with iotop.
            Returns:
                bool: True if the terminal was successfully opened, False otherwise.
            """
            if shutil.which("kitty"):
                terminal_command = "kitty"
            elif shutil.which("alacritty"):
                terminal_command = "alacritty"
            else:
                self.logger.error("Error: Neither kitty nor alacritty is installed.")
                return False
            htop_command = f"sudo iotop -p {pid}"
            self.notifier.notify_send(
                "iotop command",
                f"iotop requires permissions to monitor disk usage from the given PID:{pid}",
                "iotop",
            )
            full_command = f"{terminal_command} -e {htop_command}"
            try:
                self.run_cmd(full_command)
                return True
            except Exception as e:
                self.logger.error(f"Error launching terminal: {e}")
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
            try:
                fd, temp_path = tempfile.mkstemp(suffix=".py", text=True)
                os.write(fd, SELECT_EVENT_WATCH_SCRIPT.encode("utf-8"))
                os.close(fd)
                if is_installed("ipython"):
                    cmd = f"ipython {temp_path}"
                else:
                    cmd = f"python {temp_path}"
                full_bash_cmd = f"{cmd}; exec bash"
                self.run_cmd(f"kitty -e {full_bash_cmd}")
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

            python_cmd = (
                "from wayfire import WayfireSocket; "
                "from rich.pretty import pprint; "
                "from rich.console import Console; "
                "console = Console(); "
                "sock=WayfireSocket(); "
                "sock.watch(); "
                "console.print('[bold]Wayfire Events Monitor[/bold] (press Ctrl+C to exit)'); "
                "console.print('='*40); "
                "import itertools; "
                "[(pprint(sock.read_next_event(), console=console), print()) for _ in itertools.repeat(None)]"
            )

            full_cmd = f"ipython -c {shlex.quote(python_cmd)}"
            if terminal == "kitty":
                self.run_cmd(f"{terminal} -e {full_cmd}")
            else:
                self.run_cmd(f"{terminal}  -e {full_cmd}")

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
                self.run_cmd(f"{terminal} -e {cmd}")
            else:
                self.run_cmd(f"{terminal} -e {cmd}")

        def open_view_info_window(self, id):
            try:
                view = self.ipc.get_view(id)
                if not view:
                    raise ValueError(f"No view found with ID: {id}")
                window = self.gtk.Window(title=f"View Information (ID: {id})")
                window.set_default_size(600, 400)
                window.set_resizable(True)
                scrolled_window = self.gtk.ScrolledWindow()
                scrolled_window.set_vexpand(True)
                scrolled_window.set_hexpand(True)
                list_store = self.gtk.ListStore(str, str)  # pyright: ignore
                for key, value in view.items():
                    if isinstance(value, dict):
                        formatted_value = "\n".join(
                            f"{k}: {v}" for k, v in value.items()
                        )
                    elif isinstance(value, list):
                        formatted_value = "\n".join(str(item) for item in value)
                    else:
                        formatted_value = str(value)
                    list_store.append([key, formatted_value])
                tree_view = self.gtk.TreeView(model=list_store)
                key_renderer = self.gtk.CellRendererText()
                key_column = self.gtk.TreeViewColumn("Key", key_renderer, text=0)  # pyright: ignore
                key_column.set_resizable(True)
                key_column.set_min_width(150)
                key_column.set_sort_column_id(0)
                tree_view.append_column(key_column)
                value_renderer = self.gtk.CellRendererText()
                value_renderer.props.wrap_mode = self.pango.WrapMode.WORD_CHAR
                value_renderer.props.wrap_width = 400
                value_column = self.gtk.TreeViewColumn("Value", value_renderer, text=1)  # pyright: ignore
                value_column.set_resizable(True)
                value_column.set_expand(True)
                value_column.set_sort_column_id(1)
                tree_view.append_column(value_column)
                tree_view.set_activate_on_single_click(True)
                scrolled_window.set_child(tree_view)
                window.set_child(scrolled_window)
                window.present()
            except Exception as e:
                error_dialog = self.adw.MessageDialog(
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
                process = psutil.Process(pid)
                executable_path = process.exe()
                return executable_path
            except psutil.NoSuchProcess:
                self.logger.error(f"No process found with PID: {pid}")
                return None
            except psutil.AccessDenied:
                self.logger.error(f"Access denied for process with PID: {pid}")
                return None
            except Exception as e:
                self.logger.error(
                    f"Error retrieving executable path for PID {pid}: {e}"
                )
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
                self.popover_system.popup()  # pyright: ignore
                self.start_system_updates()

        def create_popover_system(self):
            """Create the system monitor popover and populate it with a ListBox."""
            self.popover_system = self.gtk.Popover.new()
            vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, spacing=10)
            vbox.set_margin_top(10)
            vbox.set_margin_bottom(10)
            vbox.set_margin_start(10)
            vbox.set_margin_end(10)
            vbox.set_size_request(250, -1)
            self.list_box = self.gtk.ListBox()
            self.list_box.set_selection_mode(self.gtk.SelectionMode.NONE)
            vbox.append(self.list_box)
            self.popover_system.set_child(vbox)
            self.popover_system.set_parent(self.menubutton_system)

        def last_toplevel_focused_view(self):
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

        def open_gnome_system_monitor(self, _):
            self.run_cmd("gnome-system-monitor")

        def create_gesture_for_cpu_usage(self, hbox):
            create_gesture = self.plugins["gestures_setup"].create_gesture
            create_gesture(
                hbox,
                1,
                self.open_gnome_system_monitor,
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
            create_gesture(
                hbox, 3, self.open_kitty_with_prompt_and_watch_selected_event
            )

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
            row = self.gtk.ListBoxRow()
            hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, spacing=10)
            if "APP PID" in name:
                self.create_gesture_for_focused_view_pid(hbox)
            if "APP ID" in name:
                self.create_gesture_for_focused_view_id(hbox)
            if "APP Disk" in name:
                self.create_iotop_gesture_for_focused_view_pid(hbox)
            if "CPU Usage" in name:
                self.create_gesture_for_cpu_usage(hbox)
            if "GPU" in name:
                self.create_gesture_for_amdgpu_top(hbox)
            if "Watch events" in name:
                self.create_watch_events_gesture(hbox)
            hbox.set_halign(self.gtk.Align.FILL)
            hbox.set_margin_top(5)
            hbox.set_margin_bottom(5)
            name_label = self.gtk.Label(label=name)
            name_label.set_halign(self.gtk.Align.START)
            name_label.set_hexpand(True)
            hbox.append(name_label)
            value_label = self.gtk.Label(label=value)
            value_label.set_halign(self.gtk.Align.END)
            hbox.append(value_label)
            row.set_child(hbox)
            self.list_box.append(row)
            return hbox

        def popover_is_open(self, *_):
            """Callback when the popover is opened."""

        def popover_is_closed(self, *_):
            """Callback when the popover is closed."""
            self.stop_system_updates()

        def about(self):
            """
            A plugin that displays a system monitor popover with real-time
            information on CPU, RAM, disk, network, and battery usage.
            """
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin provides a comprehensive system monitor, integrating
            with system tools and displaying data in a popover UI.
            Its core logic is centered on **data fetching, UI generation, and
            external tool integration**:
            1.  **Data Fetching**: It uses the `psutil` library to collect
                real-time metrics for CPU, memory, disk, and network usage.
                This data is refreshed periodically by a `self.glib.timeout_add_seconds`
                callback.
            2.  **Dynamic UI**: The plugin creates a `self.gtk.Popover` containing a
                dynamic `self.gtk.ListBox`. It populates this list box with the
                fetched system data and information about the currently
                focused window, including its PID.
            3.  **Tool Integration**: It provides powerful context-aware
                functionality by launching external applications like `htop`,
                `iotop`, and `amdgpu_top` to provide more detailed monitoring.
            4.  **Debugging Capabilities**: It includes gestures and handlers
                to monitor Wayfire compositor events and view properties,
                assisting with debugging and development.
            """
            return self.code_explanation.__doc__

    return SystemMonitorPlugin
