import os


class PathHandler:
    """
    A class to handle various application paths based on the XDG Base Directory
    Specification and provide convenient methods for path management.
    """

    def __init__(self, panel_instance):
        """
        Initializes the PathHandler with a specific application name.

        Args:
            app_name (str): The name of the application.
        """
        self.app_name = "waypanel"
        self._home = os.path.expanduser("~")
        self.logger = panel_instance.logger

    def get_data_path(self, *path_parts):
        """
        Returns a path inside the user's XDG data directory and creates its
        parent directories if they do not exist.
        """
        data_home = os.environ.get(
            "XDG_DATA_HOME", os.path.join(self._home, ".local", "share")
        )
        path = os.path.join(data_home, self.app_name, *path_parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def get_cache_path(self, *path_parts):
        """
        Returns a path inside the user's XDG cache directory and creates its
        parent directories if they do not exist.
        """
        cache_home = os.environ.get(
            "XDG_CACHE_HOME", os.path.join(self._home, ".cache")
        )
        path = os.path.join(cache_home, self.app_name, *path_parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path
