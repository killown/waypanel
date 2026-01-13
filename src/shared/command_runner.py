import os
import subprocess
from gi.repository import GLib  # pyright: ignore


class CommandRunner:
    def __init__(self, panel_instance):
        self.logger = panel_instance.logger
        self.ipc = panel_instance.ipc
        self.is_flatpak = os.path.exists("/.flatpak-info")

    def run(self, cmd: str) -> None:
        """
        Execute a shell command without blocking the main GTK thread.
        """
        try:
            final_cmd = cmd
            if self.is_flatpak:
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
                self.logger.info(f"Command scheduled for execution: {final_cmd}")
        except Exception as e:
            self.logger.error(
                error=e, message=f"Error running command: {cmd}", level="error"
            )

    def open_url(self, url: str) -> None:
        """
        Opens a URL in the default web browser without blocking the UI.
        """
        try:
            self.run(f'xdg-open "{url}"')
            self.logger.info(f"Attempted to open URL: {url} with xdg-open.")
        except Exception as e:
            self.logger.error(
                error=e,
                message=f"Could not open URL with xdg-open: {url}",
                level="error",
            )
