from __future__ import annotations
import psutil
import shutil
import os
import tempfile
import shlex
from typing import Any, Dict, List, Optional

from gi.repository import Adw, Gtk, Pango  # pyright: ignore
from src.shared.notify_send import Notifier

ALL_EVENTS: List[str] = [
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
SELECT_EVENT_WATCH_SCRIPT: str = f"""
import sys
import os
try:
    from wayfire import WayfireSocket
    from rich.pretty import pprint
    from rich.console import Console
    console = Console()
except ImportError as e:
    print(f"Missing dependency: {{e}}", file=sys.stderr)
    sys.exit(1)
ALL_EVENTS = {ALL_EVENTS!r}
console.print("[bold]Select an event to watch:[/bold]")
for i, event in enumerate(ALL_EVENTS, 1):
    console.print(f"{{i}}: {{event}}")
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
        pprint(event)
        console.print()
except KeyboardInterrupt:
    console.print("\\n\\nExiting...")
except Exception as e:
    console.print(f"[red]Error: {{e}}[/red]", file=sys.stderr)
    sys.exit(1)
    """


class SystemMonitorHelpers:
    def __init__(self, panel_instance: Any) -> None:
        self.panel_instance = panel_instance
        self.logger = panel_instance.logger
        self.gtk = Gtk
        self.adw = Adw
        self.pango = Pango
        self.ipc = panel_instance.ipc
        self.run_cmd = panel_instance.ipc.run_cmd
        self.notifier = Notifier()
        self.update_interval: int = 2
        self.prev_net_io: Any = psutil.net_io_counters()

    def get_ram_info(self) -> str:
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        used_gb = mem.used / (1024**3)
        percent = mem.percent
        return f"({percent}%) {used_gb:.1f} / {total_gb:.0f}GB"

    def get_cpu_usage(self) -> float:
        return psutil.cpu_percent(interval=None)

    def get_memory_usage(self) -> float:
        mem = psutil.virtual_memory()
        return mem.percent

    def get_disk_usages(self) -> List[Dict[str, str | float]]:
        disk_usages: List[Dict[str, str | float]] = []
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

    def get_network_usage(self) -> str:
        current_net_io = psutil.net_io_counters()
        upload_speed = (
            current_net_io.bytes_sent - self.prev_net_io.bytes_sent
        ) / self.update_interval
        download_speed = (
            current_net_io.bytes_recv - self.prev_net_io.bytes_recv
        ) / self.update_interval
        self.prev_net_io = current_net_io
        return f"Up: {self.format_bytes(upload_speed)}/s, Down: {self.format_bytes(download_speed)}/s"

    def get_battery_status(self) -> Optional[str]:
        battery = psutil.sensors_battery()
        if battery:
            plugged = "Plugged" if battery.power_plugged else "Not Plugged"
            percent = battery.percent
            return f"{percent}% ({plugged})"
        return None

    def get_process_disk_usage(self, pid: int) -> Optional[Dict[str, str | int]]:
        try:
            if not psutil.pid_exists(pid):
                self.logger.error(f"No process found with PID: {pid}")
                return None
            process = psutil.Process(pid)
            io_counters = process.io_counters()
            disk_usage: Dict[str, str | int] = {
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

    def get_process_usage(self, pid: int) -> Optional[Dict[str, str]]:
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

    def open_system_monitor(self) -> None:
        self.run_cmd("gnome-system-monitor")

    def open_terminal_with_amdgpu_top(self, *_: Any) -> bool:
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

    def open_terminal_with_htop(self, pid: int) -> bool:
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

    def open_terminal_with_iotop(self, pid: int) -> bool:
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

    def open_kitty_with_prompt_and_watch_selected_event(self, *_: Any) -> None:
        def is_installed(cmd: str) -> bool:
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

    def open_kitty_with_rich_events_view(self, *_: Any) -> None:
        def is_installed(cmd: str) -> bool:
            return shutil.which(cmd) is not None

        if not is_installed("python3"):
            self.logger.info("python3 is not installed.")
            return
        terminal: Optional[str] = None
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

    def open_kitty_with_ipython_view(self, view: Dict[str, Any]) -> None:
        def is_installed(cmd: str) -> bool:
            return shutil.which(cmd) is not None

        if not is_installed("ipython"):
            self.logger.info("ipython is not installed.")
            return
        terminal: Optional[str] = None
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

    def open_view_info_window(self, view_id: int) -> None:
        try:
            view = self.ipc.get_view(view_id)
            if not view:
                raise ValueError(f"No view found with ID: {view_id}")
            window = self.gtk.Window(title=f"View Information (ID: {view_id})")
            window.set_default_size(600, 400)
            window.set_resizable(True)
            scrolled_window = self.gtk.ScrolledWindow()
            scrolled_window.set_vexpand(True)
            scrolled_window.set_hexpand(True)
            list_store = self.gtk.ListStore(str, str)  # pyright: ignore
            for key, value in view.items():
                if isinstance(value, dict):
                    formatted_value = "\n".join(f"{k}: {v}" for k, v in value.items())
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
                heading="Error Retrieving View Information",
                body=str(e),
            )
            error_dialog.add_response("close", "_Close")
            error_dialog.set_default_response("close")
            error_dialog.set_close_response("close")
            error_dialog.present()

    def get_process_executable(self, pid: int) -> Optional[str]:
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
            self.logger.error(f"Error retrieving executable path for PID {pid}: {e}")
            return None

    def kill_process(self, pid: int) -> None:
        try:
            p = psutil.Process(pid)
            p.terminate()
            p.wait(3)
        except psutil.NoSuchProcess:
            pass

    def format_value(self, value: Any) -> str:
        if isinstance(value, dict):
            return "\n".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, bool):
            return "Yes" if value else "No"
        elif isinstance(value, int) and value == -1:
            return "N/A"
        return str(value)

    def format_bytes(self, bytes_count: float) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_count < 1024:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f} PB"
