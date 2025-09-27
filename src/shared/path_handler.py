import os
from pathlib import Path


class PathHandler:
    """
    A class to handle various application paths based on the XDG Base Directory
    Specification and provide convenient methods for path management.
    """

    def __init__(self, panel_instance):
        """
        Initializes the PathHandler with a specific application name.
        Args:
            panel_instance: The panel instance, used for accessing the logger.
        """
        self.app_name = "waypanel"
        self._home = Path.home()
        self.logger = panel_instance.logger

    def _get_xdg_base_dir(self, env_var: str, default_path: Path) -> Path:
        """Helper to get XDG base directory with fallback."""
        path_str = os.getenv(env_var)
        if path_str:
            return Path(path_str)
        return default_path

    def get_config_dir(self) -> Path:
        """
        Returns the path to the application's configuration directory:
        $XDG_CONFIG_HOME/waypanel or ~/.config/waypanel.
        Creates the directory if it does not exist.
        """
        config_home = self._get_xdg_base_dir("XDG_CONFIG_HOME", self._home / ".config")
        config_dir = config_home / self.app_name
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def get_data_path(self, *path_parts) -> str:
        """
        Returns a path inside the user's XDG data directory and creates its
        parent directories if they do not exist.
        """
        data_home = self._get_xdg_base_dir(
            "XDG_DATA_HOME", self._home / ".local" / "share"
        )
        path = data_home / self.app_name / Path(*path_parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_cache_path(self, *path_parts) -> str:
        """
        Returns a path inside the user's XDG cache directory and creates its
        parent directories if they do not exist.
        """
        cache_home = self._get_xdg_base_dir("XDG_CACHE_HOME", self._home / ".cache")
        path = cache_home / self.app_name / Path(*path_parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
