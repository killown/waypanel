import os
import asyncio
import subprocess
from typing import List, Optional, Tuple
from gi.repository import GLib  # pyright: ignore


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

    def _wrap_cmd(self, cmd: List[str]) -> List[str]:
        """
        Prefixes a command list with flatpak-spawn if inside a sandbox.
        """
        if self.is_flatpak:
            return ["flatpak-spawn", "--host"] + cmd
        return cmd

    def run(self, cmd: str) -> None:
        """
        Execute a shell command without blocking the main GTK thread.
        Uses the IPC run_cmd for Wayfire or subprocess for Sway.
        """
        try:
            final_cmd = cmd
            if self.is_flatpak:
                # For string-based shell execution, we wrap the whole string
                final_cmd = f"flatpak-spawn --host {cmd}"

            if os.getenv("WAYFIRE_SOCKET"):

                def run_wayfire():
                    self.ipc.run_cmd(final_cmd)
                    return False

                GLib.idle_add(run_wayfire)

            if os.getenv("SWAYSOCK"):
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
                self.logger.info(f"Command scheduled: {final_cmd}")
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
            # Uses the run method which already handles flatpak-spawn wrapping
            self.run(f'xdg-open "{url}"')
            self.logger.info(f"Attempted to open URL: {url} with xdg-open.")
        except Exception as e:
            self.logger.error(
                error=e,
                message=f"Could not open URL with xdg-open: {url}",
                level="error",
            )
