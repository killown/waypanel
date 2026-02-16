import abc
import shutil
import re
import os


class UpdateProvider(abc.ABC):
    def __init__(self, custom_command: str | None = None):
        self._custom_command = custom_command

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        pass

    @abc.abstractmethod
    def get_default_command(self) -> str:
        pass

    def get_update_command(self) -> str:
        return (
            self._custom_command if self._custom_command else self.get_default_command()
        )

    @abc.abstractmethod
    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout: int) -> int:
        pass


class PacmanProvider(UpdateProvider):
    @property
    def name(self):
        return "Pacman"

    def is_available(self):
        if not shutil.which("pacman"):
            return False
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r") as f:
                    content = f.read().lower()
                    if "id=fedora" in content or "id_like=fedora" in content:
                        return False
        except Exception:
            pass
        return True

    def get_default_command(self):
        return "sudo pacman -Syu"

    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout):
        try:
            proc = await asyncio_lib.create_subprocess_exec(
                "checkupdates",
                stdout=subprocess_lib.PIPE,
                stderr=subprocess_lib.DEVNULL,
            )
            stdout, _ = await asyncio_lib.wait_for(proc.communicate(), timeout=timeout)
            return len(stdout.decode().strip().splitlines()) if stdout else 0
        except Exception:
            return 0


class DnfProvider(UpdateProvider):
    @property
    def name(self):
        return "DNF"

    def is_available(self):
        return bool(shutil.which("dnf"))

    def get_default_command(self):
        return "sudo dnf upgrade"

    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout):
        try:
            proc = await asyncio_lib.create_subprocess_exec(
                "dnf",
                "check-update",
                "-q",
                stdout=subprocess_lib.PIPE,
                stderr=subprocess_lib.DEVNULL,
            )
            stdout, _ = await asyncio_lib.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode == 100 and stdout:
                lines = stdout.decode().strip().splitlines()
                updates = [l for l in lines if l.strip()]
                return len(updates)
            return 0
        except Exception:
            return 0


class AptProvider(UpdateProvider):
    @property
    def name(self):
        return "APT"

    def is_available(self):
        return bool(shutil.which("apt"))

    def get_default_command(self):
        return "sudo apt update && sudo apt upgrade -y"

    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout):
        try:
            proc = await asyncio_lib.create_subprocess_exec(
                "apt-get",
                "-s",
                "upgrade",
                stdout=subprocess_lib.PIPE,
                stderr=subprocess_lib.DEVNULL,
            )
            stdout, _ = await asyncio_lib.wait_for(proc.communicate(), timeout=timeout)
            match = re.search(r"(\d+)\s+upgraded", stdout.decode())
            return int(match.group(1)) if match else 0
        except Exception:
            return 0


class ZypperProvider(UpdateProvider):
    @property
    def name(self):
        return "Zypper"

    def is_available(self):
        return bool(shutil.which("zypper"))

    def get_default_command(self):
        return "sudo zypper update"

    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout):
        try:
            proc = await asyncio_lib.create_subprocess_exec(
                "zypper",
                "-q",
                "lu",
                stdout=subprocess_lib.PIPE,
                stderr=subprocess_lib.DEVNULL,
            )
            stdout, _ = await asyncio_lib.wait_for(proc.communicate(), timeout=timeout)
            return (
                len([l for l in stdout.decode().splitlines() if l.startswith("v")])
                if stdout
                else 0
            )
        except Exception:
            return 0


class XbpsProvider(UpdateProvider):
    @property
    def name(self):
        return "XBPS"

    def is_available(self):
        return bool(shutil.which("xbps-install"))

    def get_default_command(self):
        return "sudo xbps-install -Su"

    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout):
        try:
            proc = await asyncio_lib.create_subprocess_exec(
                "xbps-install",
                "-un",
                stdout=subprocess_lib.PIPE,
                stderr=subprocess_lib.DEVNULL,
            )
            stdout, _ = await asyncio_lib.wait_for(proc.communicate(), timeout=timeout)
            return len(stdout.decode().strip().splitlines()) if stdout else 0
        except Exception:
            return 0


class ApkProvider(UpdateProvider):
    @property
    def name(self):
        return "APK"

    def is_available(self):
        return bool(shutil.which("apk"))

    def get_default_command(self):
        return "sudo apk update && sudo apk upgrade"

    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout):
        try:
            proc = await asyncio_lib.create_subprocess_exec(
                "apk",
                "version",
                "-l",
                "<",
                stdout=subprocess_lib.PIPE,
                stderr=subprocess_lib.DEVNULL,
            )
            stdout, _ = await asyncio_lib.wait_for(proc.communicate(), timeout=timeout)
            return len(stdout.decode().strip().splitlines()) if stdout else 0
        except Exception:
            return 0


class FlatpakProvider(UpdateProvider):
    @property
    def name(self):
        return "Flatpak"

    def is_available(self):
        return bool(shutil.which("flatpak"))

    def get_default_command(self):
        return "flatpak update -y"

    async def get_update_count(self, asyncio_lib, subprocess_lib, timeout):
        try:
            proc = await asyncio_lib.create_subprocess_exec(
                "flatpak",
                "remote-ls",
                "--updates",
                stdout=subprocess_lib.PIPE,
                stderr=subprocess_lib.DEVNULL,
            )
            stdout, _ = await asyncio_lib.wait_for(proc.communicate(), timeout=timeout)
            return len(stdout.decode().strip().splitlines()) if stdout else 0
        except Exception:
            return 0
