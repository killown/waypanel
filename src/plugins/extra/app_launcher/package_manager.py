import os
import shutil
import subprocess
from typing import Optional, List


class PackageHelper:
    """
    Handles package identification, dependency checking, and uninstallation.
    Escapes Flatpak sandbox to interact with host pacman when necessary.

    Attributes:
        plugin (Any): Reference to the main plugin instance.
        logger (Any): Logger instance retrieved from the plugin.
        is_flatpak (bool): Flag indicating if running inside a Flatpak.
    """

    def __init__(self, plugin_instance):
        """
        Initializes the package helper and detects the environment.

        Args:
            plugin_instance: The AppLauncher plugin instance.
        """
        self.plugin = plugin_instance
        self.logger = plugin_instance.logger
        self.is_flatpak = os.path.exists("/.flatpak-info")
        self.terminals = ["kitty", "alacritty", "foot", "gnome-terminal", "xterm"]

    def is_supported(self) -> bool:
        """
        Checks if pacman is available on the host or local system.

        Returns:
            bool: True if pacman is found.
        """
        if self.is_flatpak:
            try:
                check = subprocess.run(
                    ["flatpak-spawn", "--host", "which", "pacman"],
                    capture_output=True,
                    text=True,
                )
                return check.returncode == 0
            except Exception:
                return False
        return shutil.which("pacman") is not None

    def _get_flatpak_env_args(self) -> List[str]:
        """
        Detects host display sockets and generates environment arguments.

        Returns:
            List[str]: Environment flags for flatpak-spawn.
        """
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        wayland_display = os.getenv("WAYLAND_DISPLAY", "wayland-0")
        display = os.getenv("DISPLAY", ":0")

        if os.path.exists(runtime_dir):
            try:
                sockets = [
                    f for f in os.listdir(runtime_dir) if f.startswith("wayland-")
                ]
                if sockets:
                    wayland_display = sorted(sockets)[-1]
            except Exception:
                pass

        return [
            f"--env=XDG_RUNTIME_DIR={runtime_dir}",
            f"--env=WAYLAND_DISPLAY={wayland_display}",
            f"--env=DISPLAY={display}",
            "--env=XDG_DATA_DIRS=/usr/local/share:/usr/share",
        ]

    def _get_terminal(self) -> Optional[str]:
        """
        Finds an available terminal emulator on the host or local system.

        Returns:
            Optional[str]: Terminal name or None.
        """
        for term in self.terminals:
            if self.is_flatpak:
                check = subprocess.run(
                    ["flatpak-spawn", "--host", "which", term],
                    capture_output=True,
                    text=True,
                )
                if check.returncode == 0:
                    return term
            elif shutil.which(term):
                return term
        return None

    def _get_desktop_file_path(self, desktop_id: str) -> Optional[str]:
        """
        Locates the absolute path of a desktop entry.

        Args:
            desktop_id: The identifier for the application.

        Returns:
            Optional[str]: Absolute path to the file.
        """
        paths = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/run/host/usr/share/applications",
        ]
        for p in paths:
            full = os.path.join(p, desktop_id)
            if os.path.exists(full):
                return full
        return None

    def uninstall(self, desktop_id: str) -> None:
        """
        Launches an interactive uninstallation menu in a terminal.

        Args:
            desktop_id: The identifier for the application to uninstall.
        """
        terminal = self._get_terminal()
        if not terminal:
            self.logger.error("AppLauncher: No terminal found for uninstall.")
            return

        file_path = self._get_desktop_file_path(desktop_id)
        if not file_path:
            self.logger.error(f"AppLauncher: Path not found for {desktop_id}")
            return

        host_path = file_path
        if self.is_flatpak and host_path.startswith("/run/host"):
            host_path = host_path.replace("/run/host", "", 1)

        app_id = desktop_id.removesuffix(".desktop")

        inner_script = (
            f"app_id='{app_id}'; host_path='{host_path}'; "
            'if flatpak info "\\$app_id" &>/dev/null; then '
            "echo -e '\\033[1;34m--- Flatpak Application Detected ---\\033[0m'; "
            'flatpak info "\\$app_id"; '
            "echo -en '\\n\\033[1;31mUninstall '\"\\$app_id\"'? (y/N):\\033[0m '; "
            "read -r resp; "
            'if [[ "\\$resp" =~ ^[yY]$ ]]; then flatpak uninstall "\\$app_id"; '
            "else echo 'Aborted.'; fi; "
            "else "
            'PKG=\\$(pacman -Qqo "\\$host_path" 2>/dev/null || echo "\\$app_id"); '
            "echo -e '\\033[1;34m--- Full Package Information ---\\033[0m'; "
            'pacman -Qi "\\$PKG"; '
            "echo -e '\\n\\033[1;33mChoose Uninstallation Method for '\"\\$PKG\"':\\033[0m'; "
            "echo '1) Standard (-R)      : Remove only the package'; "
            "echo '2) Recursive (-Rs)     : Remove package and unneeded dependencies'; "
            "echo '3) Force/Cascade (-Rscd): Remove package, dependencies, and bypass checks'; "
            "echo 'q) Cancel'; "
            "echo -en '\\nSelection: '; read -r opt; "
            "case \\$opt in "
            '1) sudo pacman -R "\\$PKG" ;; '
            '2) sudo pacman -Rs "\\$PKG" ;; '
            '3) sudo pacman -Rscd "\\$PKG" ;; '
            "*) echo 'Aborted.' ;; "
            "esac; fi; "
            "echo -e '\\nPress Enter to close...'; read -r"
        )

        escaped_inner = inner_script.replace('"', '\\"')

        flags = "--hold -e" if terminal in ["kitty", "alacritty"] else "-e"
        if terminal == "gnome-terminal":
            flags = "--"

        base_cmd = f'{terminal} {flags} sh -c "{escaped_inner}"'

        if self.is_flatpak:
            env_args = " ".join(self._get_flatpak_env_args())
            final_cmd = f"flatpak-spawn --host {env_args} {base_cmd}"
        else:
            final_cmd = base_cmd

        self.logger.info(f"AppLauncher: Executing: {final_cmd}")

        try:
            if hasattr(self.plugin, "cmd") and self.plugin.cmd:
                self.plugin.cmd.run(final_cmd)
            elif hasattr(self.plugin, "run_cmd"):
                self.plugin.run_cmd(final_cmd)
            else:
                os.system(f"{final_cmd} &")
        except Exception as e:
            self.logger.error(f"AppLauncher: Command failed: {e}")
