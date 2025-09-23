import os
import subprocess
import gi
import toml

from gi.repository import Adw, Gdk, Gio, Gtk
from src.core.compositor.ipc import IPC
from typing import Dict, Optional, Tuple, List

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


class Utils(Adw.Application):
    def __init__(self, panel_instance):
        """Initialize utility class with shared resources and configuration paths.

        Sets up commonly used components like logging, icon themes, configuration paths,
        and process-related utilities for use across the application.

        Args:
            panel_instance: The main panel object providing access to shared resources
                            such as logger, config, and UI containers.
        """
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.psutil_store = {}
        self.icon_names = [icon for icon in Gtk.IconTheme().get_icon_names()]
        self.gio_icon_list = Gio.AppInfo.get_all()
        self.gestures = {}
        self.fd = None
        self.watch_id = None
        self.ipc = IPC()

        self.focused_view_id = None

        self.original_alpha_views_values = {
            view.get("id"): self.ipc.get_view_alpha(view.get("id"))["alpha"]
            for view in self.ipc.list_views()
        }

    def monitor_width_height(self, monitor_name: str) -> Optional[Tuple[int, int]]:
        focused_view = self.ipc.get_focused_view()
        if focused_view:
            output = self.get_monitor_info()
            output = output[monitor_name]
            monitor_width = output[0]
            monitor_height = output[1]
            return monitor_width, monitor_height

    def run_cmd(self, cmd: str) -> None:
        """
        Execute a shell command without blocking the main GTK thread.

        If the environment variable ``WAYFIRE_SOCKET`` is set, the command is sent
        through Wayfire’s IPC and detached automatically.
        If ``SWAYSOCK`` is set, the command is executed via ``subprocess.Popen`` in
        a new session to detach it from the panel process.

        Args:
            cmd (str): Shell command to execute.
        """
        try:
            if os.getenv("WAYFIRE_SOCKET"):
                pid = self.ipc.run_cmd(cmd)
                self.logger.info(f"Command started with PID: {pid['pid']}")

            if os.getenv("SWAYSOCK"):
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,  # Ensure output is returned as strings
                    start_new_session=True,  # Detach the process from the parent
                )
                self.logger.info(f"Command started with PID: {process.pid}")
        except Exception as e:
            self.logger.error(
                error=e, message=f"Error running command: {cmd}", level="error"
            )

    def get_monitor_info(self) -> Dict[str, List[int]]:
        """
        Retrieve information about the connected monitors.

        This function gathers details about each connected monitor,
        including their dimensions and names, and returns the data as a dictionary.

        Returns:
            dict: A dictionary where keys are monitor names (str), and values are lists
                  containing [width (int), height (int)].
                  If no monitors are detected or an error occurs, returns an empty dictionary.
        """
        try:
            display = Gdk.Display.get_default()
            if not display:
                self.logger.error("Failed to retrieve default display.")
                return {}

            monitors = display.get_monitors()
            if not monitors:
                self.logger.warning("No monitors detected.")
                return {}

            monitor_info: Dict[str, List[int]] = {}
            for monitor in monitors:
                try:
                    geometry = monitor.get_geometry()
                    name: Optional[str] = monitor.props.connector

                    if not isinstance(name, str) or not name.strip():
                        self.logger.warning(
                            f"Invalid or missing monitor name for monitor: {monitor}"
                        )
                        continue

                    monitor_info[name] = [geometry.width, geometry.height]
                    self.logger.debug(
                        f"Detected monitor: {name} ({geometry.width}x{geometry.height})"
                    )

                except Exception as e:
                    self.logger.error(
                        f"Error retrieving information for a monitor: {e}",
                        exc_info=True,
                    )

            return monitor_info

        except Exception as e:
            self.logger.error(
                f"Unexpected error while retrieving monitor information: {e}",
                exc_info=True,
            )
            return {}

    def get_default_monitor_name(self, config_file_path: str) -> Optional[str]:
        """
        Retrieve the default monitor name from a TOML configuration file.

        Args:
            config_file_path (str): The path to the configuration file.

        Returns:
            Optional[str]: The default monitor name if found, otherwise None.
        """
        try:
            if not os.path.exists(config_file_path):
                self.logger.error(f"Config file '{config_file_path}' not found.")
                return None

            try:
                with open(config_file_path, "r") as file:
                    config = toml.load(file)
            except toml.TomlDecodeError as e:
                self.logger.error(
                    f"Failed to parse TOML file: {config_file_path}", exc_info=True
                )
                return None

            # Extract the monitor name if the "monitor" section exists
            if "monitor" in config:
                monitor_name = config["monitor"].get("name")
                if monitor_name:
                    self.logger.debug(f"Default monitor name found: {monitor_name}")
                    return monitor_name
                else:
                    self.logger.info(
                        "Monitor name is missing in the 'monitor' section."
                    )
                    return None
            else:
                self.logger.info(
                    "'monitor' section not found in the configuration file."
                )
                return None

        except Exception as e:
            self.logger.error(
                f"Unexpected error while retrieving default monitor name from '{config_file_path} and {e}'.",
                exc_info=True,
            )
            return None
