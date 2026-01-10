ALL_EVENTS: list[str] = [
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
    """
    Helper class providing system stats and terminal-based monitoring utilities.
    """

    def __init__(self, panel_instance: any) -> None:
        """
        Initializes the helper with panel context and initial I/O state.

        Args:
            panel_instance: The parent plugin or panel instance providing IPC.
        """
        import psutil
        from gi.repository import Adw, Gtk, Pango

        self.panel_instance = panel_instance
        self.logger = panel_instance.logger
        self.gtk = Gtk
        self.adw = Adw
        self.pango = Pango
        self.ipc = panel_instance.ipc
        self.run_cmd = panel_instance.ipc.run_cmd
        self.update_interval: int = 2
        self.prev_net_io: any = psutil.net_io_counters()

    def _get_terminal_env(self) -> tuple[str, str] | tuple[None, None]:
        """
        Detects an installed terminal emulator and its execution flag.

        Returns:
            tuple: (terminal_binary, exec_flag) or (None, None).
        """
        import shutil

        terminals = [
            ("kitty", "-e"),
            ("alacritty", "-e"),
            ("foot", "-e"),
            ("gnome-terminal", "--"),
            ("xfce4-terminal", "-e"),
            ("konsole", "-e"),
            ("wezterm", "start --"),
            ("xterm", "-e"),
        ]
        for term, flag in terminals:
            path = shutil.which(term)
            if path:
                return path, flag
        return None, None

    def get_ram_info(self) -> str:
        """
        Returns a formatted RAM usage string.
        """
        import psutil

        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        used_gb = mem.used / (1024**3)
        return f"({mem.percent}%) {used_gb:.1f} / {total_gb:.0f}GB"

    def get_cpu_usage(self) -> float:
        """
        Returns the current global CPU load.
        """
        import psutil

        return psutil.cpu_percent(interval=None)

    def get_disk_usages(self) -> list[dict[str, str | float]]:
        """
        Returns a list of usage statistics for physical disk partitions.
        """
        import psutil

        disk_usages = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_usages.append(
                    {
                        "mountpoint": part.mountpoint,
                        "total": round(usage.total / (1024**3), 1),
                        "used": round(usage.used / (1024**3), 1),
                        "percent": round(usage.percent, 1),
                    }
                )
            except (PermissionError, psutil.AccessDenied):
                continue
        return disk_usages

    def get_network_usage(self) -> str:
        """
        Calculates Up/Down speed based on historical I/O counters.
        """
        import psutil

        current_net_io = psutil.net_io_counters()
        up = (
            current_net_io.bytes_sent - self.prev_net_io.bytes_sent
        ) / self.update_interval
        down = (
            current_net_io.bytes_recv - self.prev_net_io.bytes_recv
        ) / self.update_interval
        self.prev_net_io = current_net_io
        return f"Up: {self.format_bytes(up)}/s, Down: {self.format_bytes(down)}/s"

    def get_battery_status(self) -> str | None:
        """
        Returns battery percentage and charging state if a battery is detected.
        """
        import psutil

        battery = psutil.sensors_battery()
        if battery:
            plugged = "Plugged" if battery.power_plugged else "Not Plugged"
            return f"{battery.percent}% ({plugged})"
        return None

    def get_process_disk_usage(self, pid: int) -> dict[str, str | int] | None:
        """
        Fetches disk I/O metrics for a specific process ID.
        """
        import psutil

        try:
            process = psutil.Process(pid)
            io = process.io_counters()
            return {
                "read_bytes": self.format_bytes(io.read_bytes),
                "write_bytes": self.format_bytes(io.write_bytes),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            return None

    def get_process_usage(self, pid: int) -> dict[str, str] | None:
        """
        Fetches RSS memory usage for a specific process ID.
        """
        import psutil

        try:
            process = psutil.Process(pid)
            usage = process.memory_info().rss / (1024 * 1024)
            return {"memory_usage": f"{usage:.2f} MB"}
        except (psutil.NoSuchProcess, Exception):
            return None

    def open_system_monitor(self) -> None:
        """
        Launches the GNOME System Monitor.
        """
        self.run_cmd("gnome-system-monitor")

    def open_terminal_with_amdgpu_top(self, *_) -> bool:
        """
        Launches amdgpu_top in an available terminal.
        """
        import shutil

        term, flag = self._get_terminal_env()
        if not term or not shutil.which("amdgpu_top"):
            return False
        try:
            self.run_cmd(f"{term} {flag} amdgpu_top")
            return True
        except Exception:
            return False

    def open_terminal_with_htop(self, pid: int) -> bool:
        """
        Launches htop focused on a specific PID.
        """
        term, flag = self._get_terminal_env()
        if not term:
            return False
        try:
            self.run_cmd(f"{term} {flag} htop -p {pid}")
            return True
        except Exception:
            return False

    def open_terminal_with_iotop(self, pid: int) -> bool:
        """
        Launches iotop for a PID with a user notification for sudo requirements.
        """
        from src.shared.notify_send import Notifier

        term, flag = self._get_terminal_env()
        if not term:
            return False
        Notifier().notify_send(
            "iotop command",
            f"iotop requires permissions to monitor disk usage for PID: {pid}",
            "iotop",
        )
        try:
            self.run_cmd(f"{term} {flag} sudo iotop -p {pid}")
            return True
        except Exception:
            return False

    def open_kitty_with_prompt_and_watch_selected_event(self, *_) -> None:
        """
        Runs an event selection script in a detected terminal.
        """
        import os
        import tempfile
        import shutil
        import shlex

        term, flag = self._get_terminal_env()
        if not term:
            return

        py_bin = "ipython" if shutil.which("ipython") else "python3"
        try:
            fd, path = tempfile.mkstemp(suffix=".py", text=True)
            os.write(fd, SELECT_EVENT_WATCH_SCRIPT.encode("utf-8"))
            os.close(fd)
            cmd = f"{py_bin} {path}; exec bash"
            self.run_cmd(f"{term} {flag} bash -c {shlex.quote(cmd)}")
        except Exception as e:
            self.logger.error(f"Script launch failed: {e}")

    def open_kitty_with_rich_events_view(self, *_) -> None:
        """
        Launches a live event monitor using rich and WayfireSocket.
        """
        import shlex

        term, flag = self._get_terminal_env()
        if not term:
            return

        code = (
            "from wayfire import WayfireSocket; "
            "from rich.pretty import pprint; "
            "from rich.console import Console; "
            "console = Console(); sock=WayfireSocket(); sock.watch(); "
            "import itertools; "
            "[(pprint(sock.read_next_event(), console=console), print()) for _ in itertools.repeat(None)]"
        )
        self.run_cmd(f"{term} {flag} ipython -c {shlex.quote(code)}")

    def open_kitty_with_ipython_view(self, view: dict[str, any]) -> None:
        """
        Opens an interactive session to inspect a specific Wayfire view.

        Args:
            view: Dictionary containing view metadata (specifically 'id').
        """
        import shlex
        import shutil

        term, flag = self._get_terminal_env()
        if not term or not shutil.which("ipython"):
            return

        view_id = view["id"]
        code = (
            "from wayfire import WayfireSocket; "
            "sock = WayfireSocket(); "
            f"view = sock.get_view({view_id}); "
        )
        self.run_cmd(f"{term} {flag} ipython -i -c {shlex.quote(code)}")

    def open_view_info_window(self, view_id: int) -> None:
        """
        Builds a GTK window to display detailed view properties.

        Args:
            view_id: The ID of the view to inspect via IPC.
        """
        try:
            view = self.ipc.get_view(view_id)
            if not view:
                return
            window = self.gtk.Window(title=f"View Information (ID: {view_id})")
            window.set_default_size(500, 400)
            scrolled = self.gtk.ScrolledWindow()
            store = self.gtk.ListStore(str, str)
            for k, v in view.items():
                store.append([str(k), self.format_value(v)])
            tree = self.gtk.TreeView(model=store)
            tree.append_column(
                self.gtk.TreeViewColumn("Key", self.gtk.CellRendererText(), text=0)
            )
            val_renderer = self.gtk.CellRendererText()
            val_renderer.props.wrap_mode = self.pango.WrapMode.WORD_CHAR
            tree.append_column(self.gtk.TreeViewColumn("Value", val_renderer, text=1))
            scrolled.set_child(tree)
            window.set_child(scrolled)
            window.present()
        except Exception as e:
            self.logger.error(f"Info window failed: {e}")

    def get_process_executable(self, pid: int) -> str | None:
        """
        Returns the absolute path to the process binary.
        """
        import psutil

        try:
            return psutil.Process(pid).exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def kill_process(self, pid: int) -> None:
        """
        Sends a termination signal to a specific PID.
        """
        import psutil

        try:
            p = psutil.Process(pid)
            p.terminate()
            p.wait(3)
        except (psutil.NoSuchProcess, Exception):
            pass

    def format_value(self, value: any) -> str:
        """
        Converts data types into human-readable strings for UI display.
        """
        if isinstance(value, dict):
            return "\n".join(f"{k}: {v}" for k, v in value.items())
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return "N/A" if value == -1 else str(value)

    def format_bytes(self, bytes_count: float) -> str:
        """
        Scales bytes into a human-readable size string.
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_count < 1024:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f} PB"
