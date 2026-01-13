import asyncio
import subprocess
import functools
from typing import Optional, Dict, Any, List, Tuple
from src.shared.command_runner import CommandRunner

NmcliDeviceDict = Dict[str, str]


class NetworkCLI:
    """
    An asynchronous client for interacting with the NetworkManager CLI (nmcli).
    This class provides non-blocking wrappers around common nmcli commands,
    designed for use within an asyncio event loop.
    Attributes:
        logger (logging.Logger | Any): A logger instance for reporting operations and errors.
    """

    def __init__(self, panel_instance) -> None:
        """
        Initializes the NetworkCLI instance.
        Args:
            logger: The logger instance to use. Must support standard logging methods (e.g., info, error).
        """
        self.logger = panel_instance.logger
        self.cmd = CommandRunner(panel_instance)

    async def _connect_to_network_async(self, ssid: str) -> None:
        self.logger.info(f"CLI: Attempting to connect to network: {ssid}")
        code, stdout, stderr = await self.cmd.run_async(
            ["nmcli", "device", "wifi", "connect", ssid]
        )
        if code == 0:
            self.logger.info(f"CLI: Successfully connected to {ssid}.")
        else:
            self.logger.error(f"CLI: Failed to connect to {ssid}. Error: {stderr}")

    async def run_nmcli_device_show_async(self) -> str:
        """
        Asynchronously runs 'nmcli device show' and returns the raw output.
        Returns:
            The standard output of the command as a string, or an error message
            if the command fails to execute or returns a non-zero exit code.
        """
        try:
            command: List[str] = ["nmcli", "device", "show"]
            process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout: bytes
            stderr: bytes
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error running nmcli device show:\n{stderr.decode('utf-8').strip()}"
        except OSError as e:
            return f"Exception while running nmcli (OS Error - command not found?):\n{str(e)}"
        except Exception as e:
            return f"Exception while running nmcli:\n{str(e)}"

    async def get_connected_wifi_ssid_async(self) -> Optional[str]:
        """
        Gets the SSID of the currently connected Wi-Fi network using 'nmcli device status'.
        The output is parsed to find a device of type 'wifi' that is in the 'connected' state.
        Returns:
            The SSID (connection name) of the connected Wi-Fi network, or None if no
            Wi-Fi network is connected or an error occurs.
        """
        try:
            command: List[str] = [
                "nmcli",
                "-t",
                "-f",
                "DEVICE,TYPE,STATE,CONNECTION",
                "device",
                "status",
            ]
            process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout: bytes
            stdout, _ = await process.communicate()
            for line in stdout.decode("utf-8").strip().split("\n"):
                parts: List[str] = line.strip().split(":")
                if len(parts) >= 4:
                    device: str = parts[0]
                    type_: str = parts[1]
                    state: str = parts[2]
                    connection: str = parts[3]
                    if type_ == "wifi" and state.lower() == "connected":
                        return connection
            return None
        except Exception as e:
            self.logger.error(f"Error: nmcli command failed to get connected SSID: {e}")
            return None

    def get_connected_wifi_ssid_sync(self) -> Optional[str]:
        """
        Synchronous helper to get the SSID of the currently connected Wi-Fi network.
        This uses the blocking `subprocess.run` and should only be called from an
        executor to avoid blocking the event loop.
        Returns:
            The SSID (connection name) of the connected Wi-Fi network, or None.
        """
        try:
            result: subprocess.CompletedProcess = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "DEVICE,TYPE,STATE,CONNECTION",
                    "device",
                    "status",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                encoding="utf-8",
            )
            for line in result.stdout.strip().split("\n"):
                parts: List[str] = line.strip().split(":")
                if len(parts) >= 4:
                    device: str = parts[0]
                    type_: str = parts[1]
                    state: str = parts[2]
                    connection: str = parts[3]
                    if type_ == "wifi" and state.lower() == "connected":
                        return connection
            return None
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error: nmcli command failed (sync): {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error in synchronous SSID check: {e}")
            return None

    async def _get_wifi_signal_strength_async(self, ssid: str) -> int:
        """
        Asynchronously gets the signal strength (in percent) of a given SSID using 'nmcli device wifi list'.
        Args:
            ssid: The SSID of the Wi-Fi network to check.
        Returns:
            The signal strength as an integer percentage (0-100), or 0 if the
            network is not found or an error occurs.
        """
        try:
            command: List[str] = [
                "nmcli",
                "-g",
                "SSID,SIGNAL",
                "device",
                "wifi",
                "list",
            ]
            process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout: bytes
            stdout, _ = await process.communicate()
            output_lines: List[str] = stdout.decode("utf-8").strip().split("\n")
            for line in output_lines:
                if ":" in line:
                    parts: List[str] = line.split(":")
                    if len(parts) >= 2:
                        current_ssid: str = ":".join(parts[:-1]).replace("\\", "")
                        signal: str = parts[-1]
                        if current_ssid == ssid:
                            try:
                                return int(signal)
                            except (ValueError, TypeError):
                                self.logger.warning(
                                    f"Could not parse signal strength for SSID '{ssid}': {signal}"
                                )
                                return 0
            return 0
        except Exception as e:
            self.logger.error(f"Error getting signal strength: {e}")
            return 0

    def get_default_interface_sync(self) -> Optional[str]:
        """
        Synchronously determines the default network interface name (e.g., 'eth0', 'wlan0').
        It does this by reading the '/proc/net/route' file to find the interface
        associated with the default route ('00000000').
        Returns:
            The name of the default network interface as a string, or None if not found or an error occurs.
        """
        try:
            with open("/proc/net/route", "r", encoding="utf-8") as f:
                f.readline()
                for line in f.readlines():
                    parts: List[str] = line.strip().split()
                    if len(parts) > 1 and parts[1] == "00000000":
                        return parts[0]
        except FileNotFoundError:
            self.logger.warning(
                "File /proc/net/route not found. System may not support this method."
            )
        except Exception as e:
            self.logger.error(f"Error reading default route: {e}")
        return None

    async def get_default_interface_async(self) -> Optional[str]:
        """
        Asynchronously gets the name of the default network interface.
        The blocking synchronous function `get_default_interface_sync` is run
        in the event loop's default thread pool executor to prevent blocking.
        Returns:
            The name of the default network interface as a string, or None.
        """
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_default_interface_sync)

    def check_interface_carrier_sync(self, interface: str) -> bool:
        """
        Synchronously checks if a network interface's physical carrier is up (i.e., cable plugged in or Wi-Fi radio active).
        This is done by reading the 'carrier' file in the sysfs filesystem.
        Args:
            interface: The name of the network interface (e.g., 'eth0').
        Returns:
            True if the carrier is up (file contains '1'), False otherwise or on error.
        """
        try:
            with open(
                f"/sys/class/net/{interface}/carrier", "r", encoding="utf-8"
            ) as f:
                return f.read().strip() == "1"
        except FileNotFoundError:
            self.logger.error(f"Interface '{interface}' or carrier file not found.")
            return False
        except Exception as e:
            self.logger.error(f"Error checking carrier for interface {interface}: {e}")
            return False

    async def check_interface_carrier_async(self, interface: str) -> bool:
        """
        Asynchronously checks if a network interface is physically connected (carrier is up).
        Args:
            interface: The name of the network interface (e.g., 'eth0').
        Returns:
            True if the carrier is up, False otherwise.
        """
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, functools.partial(self.check_interface_carrier_sync, interface)
        )

    async def is_internet_connected_async(self) -> bool:
        """
        Asynchronously checks for general internet connectivity based on default route and carrier status.
        This is a lightweight check that relies on the operating system's routing table
        and physical link status, not an external ping.
        Returns:
            True if a default interface is found and its carrier is up, False otherwise.
        """
        interface: Optional[str] = await self.get_default_interface_async()
        if interface and await self.check_interface_carrier_async(interface):
            return True
        return False

    async def scan_networks_async(self) -> Tuple[Optional[int], str]:
        """
        Asynchronously triggers an 'nmcli device wifi rescan' followed by a 'nmcli device wifi list'.
        Returns:
            A tuple containing:
            - The return code of the final 'list' command (Optional[int]).
            - The raw standard output of the 'list' command (str).
        """
        self.logger.info("CLI: Starting async nmcli scan...")
        try:
            rescan_command: List[str] = ["nmcli", "device", "wifi", "rescan"]
            rescan_process: asyncio.subprocess.Process = (
                await asyncio.create_subprocess_exec(
                    *rescan_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            )
            await rescan_process.wait()
            list_command: List[str] = [
                "nmcli",
                "-g",
                "SSID,SIGNAL,BSSID",
                "device",
                "wifi",
                "list",
            ]
            list_process: asyncio.subprocess.Process = (
                await asyncio.create_subprocess_exec(
                    *list_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            )
            stdout: bytes
            stdout, _ = await list_process.communicate()
            raw_output: str = stdout.decode("utf-8")
            return list_process.returncode, raw_output
        except OSError as e:
            self.logger.error(
                f"CLI: OS Error executing nmcli scan (command not found?): {e}"
            )
            return None, ""
        except Exception as e:
            self.logger.error(f"CLI: Unexpected error executing nmcli scan: {e}")
            return None, ""

    async def _apply_config_autoconnect_settings_async(
        self, ssids_to_autoconnect: List[str]
    ) -> None:
        """
        Asynchronously enforces an autoconnect whitelist for all stored Wi-Fi connection profiles using nmcli.
        If a Wi-Fi profile's SSID is in `ssids_to_autoconnect`, its `connection.autoconnect` property is set to 'yes';
        otherwise, it is set to 'no'.
        Args:
            ssids_to_autoconnect: A list of SSIDs that should have autoconnect enabled.
        """
        all_wifi_connections: List[str] = []
        try:
            list_command: List[str] = [
                "nmcli",
                "-t",
                "-f",
                "NAME,TYPE",
                "connection",
                "show",
            ]
            list_proc: asyncio.subprocess.Process = (
                await asyncio.create_subprocess_exec(
                    *list_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            )
            stdout: bytes
            stdout, _ = await list_proc.communicate()
            all_wifi_connections = [
                line.split(":")[0].strip()
                for line in stdout.decode("utf-8").strip().split("\n")
                if ":802-11-wireless" in line and line.split(":")[0].strip()
            ]
        except Exception as e:
            self.logger.error(f"CLI: Error listing all connections: {e}")
            return
        if not ssids_to_autoconnect:
            self.logger.info(
                "CLI: Autoconnect whitelist is empty. All Wi-Fi profiles will be set to autoconnect=no."
            )
        for conn_name in all_wifi_connections:
            profile_ssid: str = conn_name
            try:
                ssid_command: List[str] = [
                    "nmcli",
                    "-g",
                    "802-11-wireless.ssid",
                    "connection",
                    "show",
                    conn_name,
                ]
                ssid_proc: asyncio.subprocess.Process = (
                    await asyncio.create_subprocess_exec(
                        *ssid_command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                )
                ssid_out: bytes
                ssid_out, _ = await ssid_proc.communicate()
                retrieved_ssid: str = ssid_out.decode("utf-8").strip()
                profile_ssid = retrieved_ssid if retrieved_ssid else conn_name
            except Exception as e:
                self.logger.warning(
                    f"CLI: Failed to reliably retrieve SSID for connection {conn_name}: {e}"
                )

            autoconnect_state = ""
            if profile_ssid and ssids_to_autoconnect:
                autoconnect_state: str = (
                    "yes" if profile_ssid in ssids_to_autoconnect else "no"
                )
            try:
                modify_command: List[str] = [
                    "nmcli",
                    "connection",
                    "modify",
                    conn_name,
                    "connection.autoconnect",
                    autoconnect_state,
                ]
                modify_proc: asyncio.subprocess.Process = (
                    await asyncio.create_subprocess_exec(
                        *modify_command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                )
                await modify_proc.wait()
                if modify_proc.returncode != 0:
                    self.logger.warning(
                        f"CLI: Warning: Failed to set autoconnect={autoconnect_state} for profile '{conn_name}' (SSID: {profile_ssid})."
                    )
                else:
                    self.logger.debug(
                        f"CLI: Set autoconnect={autoconnect_state} for profile '{conn_name}' (SSID: {profile_ssid})."
                    )
            except Exception as e:
                self.logger.error(
                    f"CLI: Error applying autoconnect modification for {conn_name}: {e}"
                )

    def parse_nmcli_output(self, raw_output: str) -> List[NmcliDeviceDict]:
        """
        Parses raw 'nmcli device show' output into a list of device dictionaries.
        The nmcli output is block-based, with each block representing a device,
        separated by empty lines. Each line is a key:value pair.
        Args:
            raw_output: The raw string output from the 'nmcli device show' command.
        Returns:
            A list of dictionaries, where each dictionary represents a network device
            and its properties (e.g., {'GENERAL.DEVICE': 'wlan0', 'GENERAL.TYPE': 'wifi', ...}).
            The loopback device ('lo') is explicitly excluded for typical use cases.
        Raises:
            None
        """
        devices: List[NmcliDeviceDict] = []
        current_device: NmcliDeviceDict = {}
        lines: List[str] = raw_output.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                if current_device:
                    if current_device.get("GENERAL.DEVICE") != "lo":
                        devices.append(current_device)
                    current_device = {}
                continue
            if ":" in line:
                key: str
                value: str
                key, value = line.split(":", 1)
                current_device[key.strip()] = value.strip()
        if current_device:
            if current_device.get("GENERAL.DEVICE") != "lo":
                devices.append(current_device)
        return devices
