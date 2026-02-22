import os
import asyncio
import subprocess
import psutil
from typing import List, Optional, Tuple
from gi.repository import GLib


class CommandRunner:
    """
    Handles command execution with Flatpak sandbox awareness.
    Supports both synchronous and asynchronous execution with GTK theme enforcement.
    """

    def __init__(self, panel_instance):
        """
        Initializes the CommandRunner.

        Args:
            panel_instance: The main panel instance containing logger and ipc.
        """
        self.logger = panel_instance.logger
        self.ipc = panel_instance.ipc
        self.is_flatpak = os.path.exists("/.flatpak-info")

    def _get_active_display(self) -> str:
        current_display = os.getenv("DISPLAY")
        if current_display:
            print(current_display)
            return current_display

        for proc in psutil.process_iter(["name"]):
            try:
                if "xwayland-satellite" in (proc.info["name"] or ""):
                    return ":1"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return ":0"

    def _get_flatpak_env_args(self) -> List[str]:
        """
        Returns the surgical environment cleaning arguments for flatpak-spawn.
        Dynamically detects the host's actual Wayland display socket from the filesystem.
        """
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"

        wayland_display = os.getenv("WAYLAND_DISPLAY", "wayland-0")
        display = self._get_active_display()
        dbus_addr = os.getenv("DBUS_SESSION_BUS_ADDRESS", "")
        gtk_theme = os.getenv("GTK_THEME")

        try:
            if os.path.exists(runtime_dir):
                sockets = [
                    f for f in os.listdir(runtime_dir) if f.startswith("wayland-")
                ]
                if sockets:
                    wayland_display = sorted(sockets)[-1]
        except Exception as e:
            self.logger.error(f"Error detecting host wayland socket: {e}")

        args = [
            f"--env=XDG_RUNTIME_DIR={runtime_dir}",
            f"--env=WAYLAND_DISPLAY={wayland_display}",
            f"--env=DISPLAY={display}",
            f"--env=XDG_DATA_DIRS={runtime_dir}/flatpak/exports/share:/usr/share",
            "--env=PYTHONPATH=",
            "--env=PYTHONHOME=",
            "--env=LD_LIBRARY_PATH=",
            "--env=LD_PRELOAD=",
        ]

        if gtk_theme:
            args.append(f"--env=GTK_THEME={gtk_theme}")

        if dbus_addr:
            args.append(f"--env=DBUS_SESSION_BUS_ADDRESS={dbus_addr}")

        return args

    def _wrap_cmd(self, cmd: List[str]) -> List[str]:
        """
        Prefixes a command list with flatpak-spawn if inside a sandbox.
        """
        if self.is_flatpak:
            return ["flatpak-spawn", "--host"] + self._get_flatpak_env_args() + cmd
        return cmd

    def run(self, cmd: str) -> None:
        """
        Execute a shell command without blocking the main GTK thread.
        Appends PATH environment variable to the shell command to ensure
        local binaries are resolved correctly on the host.
        """
        try:
            host_path = os.getenv("PATH", "/usr/bin:/bin")
            display = self._get_active_display()
            gtk_theme = os.getenv("GTK_THEME", "")

            if self.is_flatpak:
                env_args = self._get_flatpak_env_args()
                spawn_cmd = ["flatpak-spawn", "--host"] + env_args + ["sh", "-c", cmd]

                def run_flatpak():
                    subprocess.Popen(
                        spawn_cmd,
                        start_new_session=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return False

                GLib.idle_add(run_flatpak)
                return

            def run_host():
                final_cmd = f"DISPLAY='{display}' PATH='{host_path}' GTK_THEME='{gtk_theme}' {cmd}"

                if hasattr(self, "ipc") and self.ipc:
                    self.ipc.run_cmd(final_cmd)

                return False

            GLib.idle_add(run_host)

        except Exception as e:
            self.logger.error(
                error=e, message=f"Error running command: {cmd}", level="error"
            )

    async def run_async(self, cmd_list: List[str]) -> Tuple[int, str, str]:
        """
        Asynchronously executes a command with GTK_THEME environment set.
        """
        env = os.environ.copy()
        env["DISPLAY"] = self._get_active_display()
        env["GTK_THEME"] = os.getenv("GTK_THEME", "")

        wrapped = self._wrap_cmd(cmd_list)
        try:
            proc = await asyncio.create_subprocess_exec(
                *wrapped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env if not self.is_flatpak else None,
            )
            stdout, stderr = await proc.communicate()
            return (
                proc.returncode or 0,
                stdout.decode("utf-8").strip(),
                stderr.decode("utf-8").strip(),
            )
        except Exception as e:
            self.logger.error(f"Async execution failed: {wrapped} - Error: {e}")
            return (1, "", str(e))

    def run_sync(self, cmd_list: List[str]) -> Optional[str]:
        """
        Synchronous execution with GTK_THEME environment set.
        """
        env = os.environ.copy()
        env["DISPLAY"] = self._get_active_display()
        env["GTK_THEME"] = os.getenv("GTK_THEME", "")

        wrapped = self._wrap_cmd(cmd_list)
        try:
            result = subprocess.run(
                wrapped,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                env=env if not self.is_flatpak else None,
            )
            return result.stdout.strip()
        except Exception as e:
            self.logger.error(f"Sync execution failed: {wrapped} - Error: {e}")
            return None

    def open_url(self, url: str) -> None:
        """
        Opens a URL in the default web browser without blocking the UI.
        """
        try:
            self.run(f"xdg-open '{url}'")
        except Exception as e:
            self.logger.error(
                error=e,
                message=f"Could not open URL with xdg-open: {url}",
                level="error",
            )
