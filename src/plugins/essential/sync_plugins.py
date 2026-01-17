def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.plugin_sync"
    default_container = "background"

    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Plugin Synchronizer",
        "version": "1.3.3",
        "enabled": True,
        "container": container,
        "description": (
            "Automates management of external plugin collections. "
            "Features self-healing: if the local plugins folder is deleted, "
            "the state is reset and folders are re-synced automatically."
        ),
    }


def get_plugin_class():
    """
    Provides the plugin's main class with deferred imports.
    """
    import os
    import shutil
    import json
    from src.plugins.core._base import BasePlugin

    class PluginSync(BasePlugin):
        """
        Synchronizes external directories to the local plugins folder.
        Wipes state if the destination folder is missing to ensure a fresh sync.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.dest_folder = os.path.expanduser("~/.local/share/waypanel/plugins/")
            self.state_file = os.path.join(
                self.path_handler.get_data_dir(), "sync_plugins", "sync_state.json"
            )

        def on_start(self):
            """
            Registers settings and triggers sync.
            """
            self.get_plugin_setting_add_hint(
                ["source_folders"],
                ["~/Git/waypanel-plugins", "~/Git/waypanel-plugins-extra/"],
                "List of absolute paths to folders containing plugins to be synced.",
            )

            if not shutil.which("rsync"):
                self.logger.warning("rsync not found. Synchronizer disabled.")
                return

            self.run_sync()

        def _get_folder_mtime(self, path):
            """Finds the latest modification time in a directory."""
            try:
                latest = os.path.getmtime(path)
                for root, _, files in os.walk(path):
                    for f in files:
                        try:
                            m = os.path.getmtime(os.path.join(root, f))
                            if m > latest:
                                latest = m
                        except OSError:
                            continue
                return latest
            except OSError:
                return 0

        def run_sync(self):
            """
            Synchronizes sources if the source is newer than state.
            Wipes state file first if dest_folder is missing.
            """
            # 1. Check if the destination exists. If not, kill the state file.
            if not os.path.exists(self.dest_folder):
                if os.path.exists(self.state_file):
                    try:
                        os.remove(self.state_file)
                        self.logger.info(
                            "Destination folder missing. Resetting sync state."
                        )
                    except OSError:
                        pass
                os.makedirs(self.dest_folder, exist_ok=True)

            source_folders = self.get_plugin_setting("source_folders", [])
            if not source_folders or not isinstance(source_folders, list):
                return

            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

            state = {}
            if os.path.exists(self.state_file):
                try:
                    with open(self.state_file, "r") as f:
                        state = json.load(f)
                except (json.JSONDecodeError, OSError):
                    state = {}

            synced_any = False
            new_state = state.copy()

            for folder in source_folders:
                full_path = os.path.expanduser(folder)
                if not os.path.exists(full_path):
                    continue

                current_mtime = self._get_folder_mtime(full_path)
                last_mtime = state.get(full_path, 0)

                # Sync if source is newer OR if it's a first-time sync (last_mtime is 0)
                if current_mtime > last_mtime:
                    self.logger.info(f"Syncing changes from: {full_path}")
                    self.cmd.run(f"rsync -auz '{full_path}/' '{self.dest_folder}'")
                    new_state[full_path] = current_mtime
                    synced_any = True

            if synced_any:
                try:
                    with open(self.state_file, "w") as f:
                        json.dump(new_state, f)
                except OSError as e:
                    self.logger.error(f"Failed to save sync state: {e}")

                def notify():
                    self.notify_send(
                        "Waypanel Sync",
                        "Plugins synchronized from custom folders. Restart the panel.",
                        "plugins",
                    )
                    return False

                self.glib.timeout_add_seconds(3, notify)

        def on_reload(self):
            """Triggered on config save in Control Center."""
            self.run_sync()

    return PluginSync
