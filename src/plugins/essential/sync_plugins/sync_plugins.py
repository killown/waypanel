def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.plugin_sync"
    return {
        "id": id,
        "name": "Plugin Synchronizer",
        "version": "1.5.2",
        "enabled": True,
        "container": "background",
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
    import hashlib
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

        def _generate_folder_hash(self, path):
            """
            Generates a composite hash of files only.
            Ignores directory mtimes to prevent jitter loops on metadata-heavy filesystems.
            """
            hasher = hashlib.md5()
            try:
                for root, dirs, files in os.walk(path):
                    if ".ignore_plugins" in files:
                        dirs[:] = []
                        continue

                    dirs.sort()
                    files.sort()

                    # Track directory names to detect new/deleted folders
                    for d in dirs:
                        hasher.update(f"dir:{d}".encode())

                    for f in files:
                        full_path = os.path.join(root, f)
                        try:
                            stat = os.stat(full_path)
                            hasher.update(f"file:{f}".encode())
                            hasher.update(str(stat.st_size).encode())
                            # Strictly file mtime only
                            hasher.update(str(int(stat.st_mtime)).encode())
                        except OSError:
                            continue
                return hasher.hexdigest()
            except OSError:
                return ""

        def run_sync(self):
            """
            Synchronizes sources into isolated subdirectories.
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
                except:
                    state = {}

            synced_any = False
            new_state = state.copy()

            for folder in source_folders:
                full_path = os.path.abspath(os.path.expanduser(folder)).rstrip("/")
                if not os.path.exists(full_path):
                    continue

                current_hash = self._generate_folder_hash(full_path)
                last_hash = state.get(folder, "")

                if force_sync or current_hash != last_hash:
                    folder_name = os.path.basename(full_path)
                    specific_dest = os.path.join(self.dest_root, folder_name)

                    try:
                        valid_subdirs = [
                            d
                            for d in os.listdir(full_path)
                            if os.path.isdir(os.path.join(full_path, d))
                            and not os.path.exists(
                                os.path.join(full_path, d, ".ignore_plugins")
                            )
                            and d not in [".git", "__pycache__", "examples"]
                        ]
                    except OSError:
                        continue

                    os.makedirs(specific_dest, exist_ok=True)

                    # Mirror valid subdirectories
                    for plugin_dir in valid_subdirs:
                        src_p = os.path.join(full_path, plugin_dir)
                        dst_p = os.path.join(specific_dest, plugin_dir)
                        os.makedirs(dst_p, exist_ok=True)

                        self.cmd.run(
                            f"rsync -auz --delete --exclude='.ignore_plugins' '{src_p}/' '{dst_p}/'"
                        )

                    # Cleanup
                    try:
                        for d in os.listdir(specific_dest):
                            if d not in valid_subdirs:
                                shutil.rmtree(os.path.join(specific_dest, d))
                    except OSError:
                        pass

                    new_state[folder] = current_hash
                    synced_any = True

            if synced_any:
                try:
                    with open(self.state_file, "w") as f:
                        json.dump(new_state, f)
                except OSError:
                    pass

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
