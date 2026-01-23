def get_plugin_metadata(panel):
    """Define the plugin's properties.

    Returns:
        dict: Metadata containing id, name, description, version, and the
            background container type.
    """
    return {
        "id": "org.waypanel.path_example",
        "name": "Path Handler Example",
        "description": "Demonstrates usage of the PathHandler helper.",
        "version": "1.0.0",
        "author": "Waypanel",
        # "background" means a logic-only service. No UI, no GTK container,
        # and no dynamic layout resolution via config_handler.
        "container": "background",
    }


def get_plugin_class():
    """Returns the plugin class with deferred imports to prevent top-level execution."""
    from src.plugins.core._base import BasePlugin

    class PathExamplePlugin(BasePlugin):
        """Plugin demonstrating XDG path management using the PathHandler helper."""

        def on_enable(self):
            """Execute path resolution logic when the plugin is enabled."""
            # Accessing standard XDG-based directories
            # These methods automatically create the directory if missing.
            config_dir = self.path_handler.get_config_dir()
            data_dir = self.path_handler.get_data_dir()
            cache_dir = self.path_handler.get_cache_dir()

            self.logger.info(f"Config: {config_dir}")
            self.logger.info(f"Data: {data_dir}")
            self.logger.info(f"Cache: {cache_dir}")

            # Resolving a path (User Data -> Internal Package Fallback)
            # Useful for assets that users might want to override in ~/.local/share/waypanel
            asset_path = self.path_handler.get_data_path("assets", "logo.svg")
            self.logger.info(f"Resolved asset: {asset_path}")

            # Generating a safe cache path
            # get_cache_path ensures the immediate parent directory of the file exists.
            log_dump = self.path_handler.get_cache_path("debug", "trace.log")
            self.logger.info(f"Log dump location: {log_dump}")

            # Searching across all priority paths (User -> System)
            # Returns a list of Path objects from highest to lowest priority.
            search_paths = self.path_handler.get_data_search_paths()
            for p in search_paths:
                self.logger.debug(f"Searching in: {p}")

        def on_disable(self):
            """Clean up resources when the plugin is disabled."""
            self.logger.info("Path Example Plugin disabled.")

    return PathExamplePlugin
