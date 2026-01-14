import os
import shutil
from typing import Optional, List


class PackageHelper:
    """Handles package identification, dependency checking, and uninstallation.

    Attributes:
        plugin (Any): Reference to the main plugin instance.
        logger (Any): Logger instance retrieved from the plugin.
        manager (Optional[str]): Absolute path to the pacman executable.
        terminals (List[str]): Priority list of terminal emulators.
    """

    def __init__(self, plugin_instance):
        """Initializes the package helper.

        Args:
            plugin_instance: The AppLauncher instance.
        """
        self.plugin = plugin_instance
        self.logger = plugin_instance.logger
        self.manager = shutil.which("pacman")
        self.terminals = ["kitty", "alacritty", "foot", "gnome-terminal", "xterm"]

    def is_supported(self) -> bool:
        """Checks if pacman is available.

        Returns:
            bool: True if pacman is found.
        """
        return self.manager is not None

    def _get_terminal(self) -> Optional[str]:
        """Finds an available terminal emulator."""
        for term in self.terminals:
            if shutil.which(term):
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
        """Launches a terminal with full package info and uninstallation options.

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

        pkg_fallback = desktop_id.removesuffix(".desktop")
        
        # Script logic:
        # 1. Identify package name using pacman -Qqo.
        # 2. Print full package information using pacman -Qi.
        # 3. Present options for different removal levels.
        inner_script = (
            f"PKG=\\$(pacman -Qqo '{file_path}' 2>/dev/null || echo '{pkg_fallback}'); "
            "echo -e '\\033[1;34m--- Full Package Information ---\\033[0m'; "
            "pacman -Qi \"\\$PKG\"; "
            "echo -e '\\n\\033[1;33mChoose Uninstallation Method for '\"\\$PKG\"':\\033[0m'; "
            "echo '1) Standard (-R)      : Remove only the package'; "
            "echo '2) Recursive (-Rs)     : Remove package and unneeded dependencies'; "
            "echo '3) Force/Cascade (-Rscd): Remove package, dependencies, and bypass checks'; "
            "echo 'q) Cancel'; "
            "echo -en '\\nSelection: '; read -r opt; "
            "case \\$opt in "
                "1) sudo pacman -R \"\\$PKG\" ;; "
                "2) sudo pacman -Rs \"\\$PKG\" ;; "
                "3) sudo pacman -Rscd \"\\$PKG\" ;; "
                "*) echo 'Aborted.' ;; "
            "esac; "
            "echo -e '\\nPress Enter to close...'; read -r"
        )

        flags = "--hold -e" if terminal in ["kitty", "alacritty"] else "-e"
        if terminal == "gnome-terminal":
            flags = "--"

        cmd = f"{terminal} {flags} sh -c \"{inner_script}\""

        self.logger.info(f"AppLauncher: Requesting uninstall menu with info: {cmd}")

        try:
            if hasattr(self.plugin, "cmd") and self.plugin.cmd:
                self.plugin.cmd.run(cmd)
            elif hasattr(self.plugin, "run_cmd"):
                self.plugin.run_cmd(cmd)
            else:
                os.system(f"{cmd} &")
        except Exception as e:
            self.logger.error(f"AppLauncher: Command execution failed: {e}")