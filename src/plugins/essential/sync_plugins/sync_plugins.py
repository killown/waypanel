def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.plugin_sync"
    default_container = "background"
    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Plugin Synchronizer",
        "version": "1.4.1",
        "enabled": True,
        "container": container,
        "description": (
            "A developer-centric sync engine that allows you to work on plugins in any "
            "local directory (like ~/Git) while automatically mirroring changes—including "
            "file deletions—to the Waypanel environment. Supports multiple source folders "
            "with isolated state tracking to ensure no file collisions."
        ),
    }


def get_plugin_class():
    import os
    import shutil
    import json
    from src.plugins.core._base import BasePlugin

    class PluginSync(BasePlugin):
        """
        Synchronizes external directories to isolated subfolders in the local plugins folder.
        Wipes state if the destination root is missing to ensure a fresh recovery sync.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.dest_root = os.path.expanduser("~/.local/share/waypanel/plugins/")
            self.state_file = os.path.join(
                self.path_handler.get_data_dir(), "sync_plugins", "sync_state.json"
            )
            self._is_syncing = False

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
            """Finds the latest modification time in a directory tree."""
            try:
                latest = os.path.getmtime(path)
                for root, dirs, files in os.walk(path):
                    if ".ignore_plugins" in files:
                        dirs[:] = []
                        continue
                    dir_mtime = os.path.getmtime(root)
                    if dir_mtime > latest:
                        latest = dir_mtime
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
            Synchronizes sources into isolated subdirectories.
            If the main plugins folder is missing, state is reset to force full sync.
            """
            if self._is_syncing:
                return
            self._is_syncing = True

            force_sync = False
            if not os.path.exists(self.dest_root):
                os.makedirs(self.dest_root, exist_ok=True)
                force_sync = True
                if os.path.exists(self.state_file):
                    try:
                        os.remove(self.state_file)
                        self.logger.info(
                            "Plugins folder missing; state reset for full recovery."
                        )
                    except OSError:
                        pass

            source_folders = self.get_plugin_setting("source_folders", [])
            if not source_folders or not isinstance(source_folders, list):
                self._is_syncing = False
                return

            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

            state = {}
            if not force_sync and os.path.exists(self.state_file):
                try:
                    with open(self.state_file, "r") as f:
                        state = json.load(f)
                except (json.JSONDecodeError, OSError):
                    state = {}

            synced_any = False
            new_state = state.copy()

            for folder in source_folders:
                full_path = os.path.abspath(os.path.expanduser(folder)).rstrip("/")
                if not os.path.exists(full_path):
                    continue

                folder_name = os.path.basename(full_path)
                specific_dest = os.path.join(self.dest_root, folder_name)
                os.makedirs(specific_dest, exist_ok=True)

                current_mtime = self._get_folder_mtime(full_path)
                last_mtime = state.get(folder, 0)

                if force_sync or current_mtime != last_mtime:
                    self.logger.info(f"Syncing {folder_name} to {specific_dest}")
                    self.cmd.run(
                        f"rsync -auz --delete --exclude='.ignore_plugins' '{full_path}/' '{specific_dest}/'"
                    )
                    new_state[folder] = current_mtime
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
                        "Plugins mirrored to isolated subfolders. Restart the panel.",
                        "plugins",
                    )
                    return False

                self.glib.timeout_add_seconds(3, notify)

            self._is_syncing = False

        def on_reload(self):
            """Triggered on config save in Control Center."""
            self.run_sync()

    return PluginSync
