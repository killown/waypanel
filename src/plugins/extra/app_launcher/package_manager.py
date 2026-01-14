import os
import shutil
import subprocess
from typing import Optional, List


class PackageHelper:
    """Handles package identification and uninstallation with Flatpak host awareness.

    Attributes:
        plugin (Any): Reference to the main plugin instance.
        logger (Any): Logger instance retrieved from the plugin.
        is_flatpak (bool): Whether the plugin is running inside a Flatpak sandbox.
        terminals (List[str]): Priority list of terminal emulators.
    """

    def __init__(self, plugin_instance):
        """Initializes the package helper and detects environment state.

        Args:
            plugin_instance: The AppLauncher instance.
        """
        self.plugin = plugin_instance
        self.logger = plugin_instance.logger
        self.is_flatpak = os.path.exists("/.flatpak-info")
        self.terminals = ["kitty", "alacritty", "foot", "gnome-terminal", "xterm"]
        self.manager_name = "pacman"

    def is_supported(self) -> bool:
        """Checks if pacman is available on the host or in the sandbox.

        Returns:
            bool: True if pacman is found.
        """
        if self.is_flatpak:
            try:
                check = subprocess.run(
                    ["flatpak-spawn", "--host", "which", self.manager_name],
                    capture_output=True,
                    text=True,
                )
                return check.returncode == 0
            except Exception:
                return False
        return shutil.which(self.manager_name) is not None

    def _get_flatpak_env_args(self) -> List[str]:
        """Detects host Wayland/X11 sockets and returns environment flags for flatpak-spawn.

        Returns:
            List[str]: List of --env arguments for flatpak-spawn.
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
        ]

    def _get_terminal(self) -> Optional[str]:
        """Finds an available terminal emulator on the host or sandbox."""
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
        """Resolves the full filesystem path for a desktop entry."""
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
        """Launches a terminal to perform uninstallation, escaping the Flatpak sandbox if needed.

        Args:
            desktop_id: The identifier for the application.
        """
        terminal = self._get_terminal()
        if not terminal:
            self.logger.error("AppLauncher: No terminal found for uninstall task.")
            return

        file_path = self._get_desktop_file_path(desktop_id)
        if not file_path:
            self.logger.error(f"AppLauncher: Could not locate path for {desktop_id}")
            return

        # If in Flatpak, we must strip /run/host because the host shell won't recognize it
        host_file_path = file_path
        if self.is_flatpak and host_file_path.startswith("/run/host"):
            host_file_path = host_file_path.replace("/run/host", "", 1)

        pkg_fallback = desktop_id.removesuffix(".desktop")

        inner_script = (
            f"PKG=\\$(pacman -Qqo '{host_file_path}' 2>/dev/null || echo '{pkg_fallback}'); "
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
            "esac; "
            "echo -e '\\nPress Enter to close...'; read -r"
        )

        flags = "--hold -e" if terminal in ["kitty", "alacritty"] else "-e"
        if terminal == "gnome-terminal":
            flags = "--"

        # Construct the host-escape command if necessary
        base_cmd = f'{terminal} {flags} sh -c "{inner_script}"'

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
            self.logger.error(f"AppLauncher: Command execution failed: {e}")

