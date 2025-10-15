import importlib.util
import sys
import subprocess
from typing import Optional, Any


class InstallHelpers:
    """
    Provides methods for the robust, run-time resolution (installation) of external
    Python module dependencies.
    This class strictly manages the provisioning stage using only synchronous,
    blocking operations, ensuring the application waits until the package is
    installed before continuing.
    """

    def __init__(self, panel_instance: Any) -> None:
        """
        Initializes the InstallHelpers, binding to the application's structured logger.
        Args:
            panel_instance: An object that exposes a 'logger' attribute for structured logging.
        """
        self.logger = panel_instance.logger

    def resolve_and_install(
        self, module_name: str, install_name: Optional[str] = None
    ) -> bool:
        """
        Checks for a module's existence and attempts to install it via pip if missing,
        using a synchronous, blocking subprocess call.
        Args:
            module_name: The name of the module to check (e.g., 'requests').
            install_name: The package name to pass to `pip install` (e.g., 'python-requests').
                          If None, defaults to `module_name`.
        Returns:
            True if the package is already installed or if installation succeeds,
            False otherwise.
        """
        pkg_name = install_name if install_name else module_name
        if importlib.util.find_spec(module_name) is not None:
            self.logger.info(
                f"Package for module '{module_name}' is already installed."
            )
            return True
        self.logger.warning(
            f"Package for module '{module_name}' not found. Attempting blocking installation of package '{pkg_name}'."
        )
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            pkg_name,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
            return_code = result.returncode
            stderr = result.stderr.strip()
            if return_code != 0:
                self.logger.error(
                    f"Installation of '{pkg_name}' failed with return code {return_code}. "
                    f"Error output: {stderr}"
                )
                return False
            self.logger.info(
                f"Successfully installed package '{pkg_name}'. Output: {result.stdout.splitlines()[-1] if result.stdout else 'No output.'}"
            )
            if importlib.util.find_spec(module_name) is None:
                self.logger.error(
                    f"Installation of '{pkg_name}' succeeded, but module '{module_name}' "
                    f"is not visible in sys.path. Requires application restart or environment check."
                )
                return False
            return True
        except FileNotFoundError:
            self.logger.error(
                f"Cannot execute Python interpreter at '{sys.executable}'. Check environment PATH configuration."
            )
            return False
        except subprocess.TimeoutExpired:
            self.logger.error(
                f"Installation of '{pkg_name}' timed out after 300 seconds."
            )
            return False
        except Exception as e:
            self.logger.error(
                f"System error during synchronous installation: {type(e).__name__}: {e}"
            )
            return False
