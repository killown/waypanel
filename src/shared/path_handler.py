import os
from pathlib import Path
from typing import List, Union, Tuple, Any, Optional


class PathHandler:
    """
    A class to handle various application paths based on the XDG Base Directory
    Specification, correctly implementing both user-writable HOME directories
    and system-wide read-only DIRS search paths for maximum distribution compatibility.
    """

    def __init__(self, panel_instance: Any):
        """
        Initializes the PathHandler with the application name and home directory.
        Args:
            panel_instance: The panel instance, used for accessing the logger.
        """
        self.app_name: str = "waypanel"
        self._home: Path = Path.home()
        self.logger: Any = panel_instance.logger
        self._default_config_dirs: Tuple[str, ...] = ("/etc/xdg",)
        self._default_data_dirs: Tuple[str, ...] = ("/usr/local/share", "/usr/share")
        self._package_root: Path = Path(__file__).resolve().parents[2]

    def _get_xdg_base_dir(self, env_var: str, default_path: Path) -> Path:
        """
        Helper to get a single XDG base directory (HOME) with environment variable
        fallback and path validation.
        """
        path_str: Optional[str] = os.getenv(env_var)
        if path_str:
            resolved_path = Path(path_str)
            if resolved_path.is_absolute():
                return resolved_path
        return default_path

    def _get_xdg_search_dirs(
        self, env_var: str, default_dirs: Tuple[str, ...]
    ) -> List[Path]:
        """
        Helper to get XDG search directories (DIRS) with environment variable fallback.
        Args:
            env_var: The XDG environment variable name (e.g., "XDG_CONFIG_DIRS").
            default_dirs: The default tuple of directory paths if the environment variable is not set.
        Returns:
            A list of valid Path objects for system search directories, in order of preference.
        """
        path_str: Optional[str] = os.getenv(env_var)
        if not path_str:
            return [Path(p) for p in default_dirs]
        paths: List[Path] = []
        for p in path_str.split(os.pathsep):
            resolved_path = Path(p)
            if resolved_path.is_absolute():
                paths.append(resolved_path)
        return paths

    def get_config_dir(self) -> Path:
        """
        Returns the user-specific, writable configuration directory:
        $XDG_CONFIG_HOME/waypanel or ~/.config/waypanel.
        Creates the directory if it does not exist.
        """
        config_home: Path = self._get_xdg_base_dir(
            "XDG_CONFIG_HOME", self._home / ".config"
        )
        config_dir: Path = config_home / self.app_name
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def get_data_dir(self) -> Path:
        """
        Returns the user-specific, writable data directory (Base Home):
        $XDG_DATA_HOME/waypanel or ~/.local/share/waypanel.
        Creates the directory if it does not exist.
        """
        data_home: Path = self._get_xdg_base_dir(
            "XDG_DATA_HOME", self._home / ".local" / "share"
        )
        data_dir: Path = data_home / self.app_name
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_data_path(self, *path_parts: Union[str, Path]) -> str:
        """
        Returns a path (as a string) inside the user's XDG data directory or
        falls back to the internal package root.

        Args:
            *path_parts: Components of the path.

        Returns:
            str: The resolved absolute path.
        """
        user_path: Path = self.get_data_dir().joinpath(*path_parts)
        if user_path.exists():
            return str(user_path)

        internal_path: Path = self._package_root.joinpath(*path_parts)
        if internal_path.exists():
            return str(internal_path)

        user_path.parent.mkdir(parents=True, exist_ok=True)
        return str(user_path)

    def get_cache_dir(self) -> Path:
        """
        Returns the user-specific, writable cache directory (Base Home):
        $XDG_CACHE_HOME/waypanel or ~/.cache/waypanel.
        Creates the directory if it does not exist.
        """
        cache_home: Path = self._get_xdg_base_dir(
            "XDG_CACHE_HOME", self._home / ".cache"
        )
        cache_dir: Path = cache_home / self.app_name
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_cache_path(self, *path_parts: Union[str, Path]) -> str:
        """
        Returns a path (as a string) inside the user's XDG cache directory.
        Ensures the immediate parent directory of the final resource exists.
        """
        path: Path = self.get_cache_dir().joinpath(*path_parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_config_search_paths(self) -> List[Path]:
        """
        Returns an ordered list of directories to search for read-only configuration
        files, from highest priority (user writable) to lowest (system defaults).
        Order of preference: [$XDG_CONFIG_HOME/app_name, $XDG_CONFIG_DIRS/app_name...]
        """
        user_config_path: Path = self.get_config_dir()
        system_search_paths: List[Path] = self._get_xdg_search_dirs(
            "XDG_CONFIG_DIRS", self._default_config_dirs
        )
        app_system_paths: List[Path] = [p / self.app_name for p in system_search_paths]
        return [user_config_path] + app_system_paths

    def get_data_search_paths(self) -> List[Path]:
        """
        Returns an ordered list of directories to search for read-only data files
        (e.g., icons, themes, installed plugin files).
        Order of preference: [$XDG_DATA_HOME/app_name, $XDG_DATA_DIRS/app_name...]
        """
        user_data_path: Path = self.get_data_dir()
        system_search_paths: List[Path] = self._get_xdg_search_dirs(
            "XDG_DATA_DIRS", self._default_data_dirs
        )
        app_system_paths: List[Path] = [p / self.app_name for p in system_search_paths]
        return [user_data_path] + app_system_paths
