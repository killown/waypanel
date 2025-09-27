import asyncio
import subprocess
import functools
from typing import Optional, Dict, Any, List, Tuple


class NetworkCLI:
    def __init__(self, logger: Any):
        self.logger = logger

    async def _connect_to_network_async(self, ssid: str):
        """
        Async implementation of connecting to a network using nmcli device wifi connect.
        (Completed from original source)
        """
        self.logger.info(f"CLI: Attempting to connect to network: {ssid}")
        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli",
                "device",
                "wifi",
                "connect",
                ssid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                self.logger.info(f"CLI: Successfully connected to {ssid}.")
            else:
                self.logger.error(
                    f"CLI: Failed to connect to {ssid}. nmcli error:\n{stderr.decode()}"
                )
        except Exception as e:
            self.logger.error(f"CLI: Error during network connection: {e}")

    async def run_nmcli_device_show_async(self) -> str:
        """Run 'nmcli device show' and return its output."""
        try:
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                "device",
                "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return stdout.decode()
            else:
                return f"Error running nmcli device show:\n{stderr.decode()}"
        except Exception as e:
            return f"Exception while running nmcli:\n{str(e)}"

    async def get_connected_wifi_ssid_async(self) -> Optional[str]:
        """Gets the SSID of the currently connected Wi-Fi network using nmcli."""
        try:
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                "-t",
                "-f",
                "DEVICE,TYPE,STATE,CONNECTION",
                "device",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            for line in stdout.decode().strip().split("\n"):
                parts = line.strip().split(":")
                if len(parts) >= 4:
                    device, type_, state, connection = parts
                    if type_ == "wifi" and state.lower() == "connected":
                        return connection
            return None
        except Exception:
            self.logger.error("Error: nmcli command failed to get connected SSID.")
            return None

    def get_connected_wifi_ssid_sync(self) -> Optional[str]:
        """Synchronous helper to get connected SSID."""
        try:
            result = subprocess.run(
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
            )
            for line in result.stdout.strip().split("\n"):
                parts = line.strip().split(":")
                if len(parts) >= 4:
                    device, type_, state, connection = parts
                    if type_ == "wifi" and state.lower() == "connected":
                        return connection
            return None
        except subprocess.CalledProcessError:
            self.logger.error("Error: nmcli command failed (sync).")
            return None

    async def _get_wifi_signal_strength_async(self, ssid: str) -> int:
        """Gets the signal strength of a given SSID using nmcli."""
        try:
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                "-g",
                "SSID,SIGNAL",
                "device",
                "wifi",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            output_lines = stdout.decode("utf-8").strip().split("\n")
            for line in output_lines:
                if ":" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        current_ssid = ":".join(parts[:-1]).replace("\\", "")
                        signal = parts[-1]
                        if current_ssid == ssid:
                            try:
                                return int(signal)
                            except (ValueError, TypeError):
                                return 0
            return 0
        except Exception as e:
            self.logger.error(f"Error getting signal strength: {e}")
            return 0

    def get_default_interface_sync(self) -> Optional[str]:
        """Synchronous version for a quick check, reads /proc/net/route."""
        try:
            with open("/proc/net/route") as f:
                for line in f.readlines():
                    parts = line.strip().split()
                    if parts[1] == "00000000":
                        return parts[0]
        except Exception as e:
            self.logger.error("Error reading default route:", e)
        return None

    async def get_default_interface_async(self) -> Optional[str]:
        """Get the name of the default network interface asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_default_interface_sync)

    def check_interface_carrier_sync(self, interface: str) -> bool:
        """Check if a network interface is physically connected (carrier is up) synchronously."""
        try:
            with open(f"/sys/class/net/{interface}/carrier", "r") as f:
                return f.read().strip() == "1"
        except FileNotFoundError:
            self.logger.error(f"Interface '{interface}' not found.")
            return False

    async def check_interface_carrier_async(self, interface: str) -> bool:
        """Check if a network interface is physically connected (carrier is up) asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, functools.partial(self.check_interface_carrier_sync, interface)
        )

    async def is_internet_connected_async(self) -> bool:
        """Check if internet is available (relies on default route and carrier)."""
        interface = await self.get_default_interface_async()
        if interface and await self.check_interface_carrier_async(interface):
            return True
        return False

    async def scan_networks_async(self) -> Tuple[int | None, str]:
        """
        Asynchronously run nmcli to scan for networks and return the raw output.
        Returns: (return_code, raw_output)
        """
        self.logger.info("CLI: Starting async nmcli scan...")
        try:
            rescan_process = await asyncio.create_subprocess_exec(
                "nmcli",
                "device",
                "wifi",
                "rescan",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await rescan_process.wait()
            list_process = await asyncio.create_subprocess_exec(
                "nmcli",
                "-g",
                "SSID,SIGNAL,BSSID",
                "device",
                "wifi",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await list_process.communicate()
            raw_output = stdout.decode("utf-8")
            return list_process.returncode, raw_output
        except Exception as e:
            self.logger.error(f"CLI: Error executing nmcli scan: {e}")
            return 1, ""

    async def _apply_config_autoconnect_settings_async(
        self, ssids_to_autoconnect: List[str]
    ):
        """Enforces autoconnect whitelist for Wi-Fi profiles using nmcli."""
        try:
            list_proc = await asyncio.create_subprocess_exec(
                "nmcli",
                "-t",
                "-f",
                "NAME,TYPE",
                "connection",
                "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await list_proc.communicate()
            all_wifi_connections: List[str] = [
                line.split(":")[0].strip()
                for line in stdout.decode().strip().split("\n")
                if ":802-11-wireless" in line and line.split(":")[0].strip()
            ]
        except Exception as e:
            self.logger.error(f"CLI: Error listing all connections: {e}")
            return
        for conn_name in all_wifi_connections:
            profile_ssid = conn_name
            try:
                ssid_proc = await asyncio.create_subprocess_exec(
                    "nmcli",
                    "-g",
                    "802-11-wireless.ssid",
                    "connection",
                    "show",
                    conn_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                ssid_out, _ = await ssid_proc.communicate()
                profile_ssid = ssid_out.decode().strip() or conn_name
            except Exception as e:
                self.logger.error(f"CLI: Failed to retrieve SSID for {conn_name}: {e}")
                pass
            if not ssids_to_autoconnect:
                return
            autoconnect_state = "yes" if profile_ssid in ssids_to_autoconnect else "no"
            try:
                modify_proc = await asyncio.create_subprocess_exec(
                    "nmcli",
                    "connection",
                    "modify",
                    conn_name,
                    "connection.autoconnect",
                    autoconnect_state,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await modify_proc.wait()
                if modify_proc.returncode != 0:
                    self.logger.warning(
                        f"CLI: Warning: Failed to set autoconnect={autoconnect_state} for profile '{conn_name}' (SSID: {profile_ssid})."
                    )
            except Exception as e:
                self.logger.error(
                    f"CLI: Error applying autoconnect modification for {conn_name}: {e}"
                )

    def parse_nmcli_output(self, raw_output: str) -> List[Dict[str, str]]:
        """Parse raw nmcli device show output into list of device sections."""
        devices = []
        current_device = {}
        lines = raw_output.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                if current_device:
                    if current_device.get("GENERAL.DEVICE") != "lo":
                        devices.append(current_device)
                    current_device = {}
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                current_device[key.strip()] = value.strip()
        if current_device:
            if current_device.get("GENERAL.DEVICE") != "lo":
                devices.append(current_device)
        return devices
