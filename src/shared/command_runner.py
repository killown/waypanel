import os
import asyncio
import subprocess
from typing import List, Optional, Tuple
from gi.repository import GLib


class CommandRunner:
    """
    Handles command execution with Flatpak sandbox awareness.
    Supports both synchronous and asynchronous execution.
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

    def _get_flatpak_env_args(self) -> List[str]:
        """
        Returns the surgical environment cleaning arguments for flatpak-spawn.
        Dynamically detects the host's actual Wayland display socket from the filesystem.
        """
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"

        wayland_display = os.getenv("WAYLAND_DISPLAY", "wayland-0")
        display = os.getenv("DISPLAY", ":0")
        dbus_addr = os.getenv("DBUS_SESSION_BUS_ADDRESS", "")

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
            f"--env=XDG_DATA_DIRS={runtime_dir}/flatpak/exports/share:/usr/local/share:/usr/share",
            "--env=PYTHONPATH=",
            "--env=PYTHONHOME=",
            "--env=LD_LIBRARY_PATH=",
            "--env=LD_PRELOAD=",
        ]

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
        Uses the IPC run_cmd for Wayfire or subprocess for Sway.
        """
        try:
            final_cmd = cmd
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

            if os.getenv("WAYFIRE_SOCKET"):

                def run_wayfire():
                    if hasattr(self, "ipc") and self.ipc:
                        self.ipc.run_cmd(final_cmd)
                    return False

                GLib.idle_add(run_wayfire)

            elif os.getenv("SWAYSOCK"):
                GLib.idle_add(
                    lambda: subprocess.Popen(
                        final_cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        start_new_session=True,
                    )
                )
        except Exception as e:
            self.logger.error(
                error=e, message=f"Error running command: {cmd}", level="error"
            )

    async def run_async(self, cmd_list: List[str]) -> Tuple[int, str, str]:
        """
        Asynchronously executes a command and returns (returncode, stdout, stderr).
        Used for CLI tools like nmcli.
        """
        wrapped = self._wrap_cmd(cmd_list)
        try:
            proc = await asyncio.create_subprocess_exec(
                *wrapped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
        Synchronous execution for use in executors.
        """
        wrapped = self._wrap_cmd(cmd_list)
        try:
            result = subprocess.run(
                wrapped, capture_output=True, text=True, check=True, encoding="utf-8"
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
