import os
import subprocess
from gi.repository import GLib


class CommandRunner:
    def __init__(self, panel_instance):
        self.logger = panel_instance.logger
        self.ipc = panel_instance.ipc

    def run(self, cmd: str) -> None:
        """
        Execute a shell command without blocking the main GTK thread.
        """
        try:
            if os.getenv("WAYFIRE_SOCKET"):
                pid = self.ipc.run_cmd(cmd)
                self.logger.info(f"Command started with PID: {pid['pid']}")

            if os.getenv("SWAYSOCK"):
                GLib.idle_add(
                    lambda: subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        start_new_session=True,
                    )
                )
                self.logger.info("Command scheduled for execution.")

        except Exception as e:
            self.logger.error(
                error=e, message=f"Error running command: {cmd}", level="error"
            )
