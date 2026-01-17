def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.plugin_sync"
    default_container = "background"

    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Plugin Synchronizer",
        "version": "1.4.0",
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
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.dest_root = os.path.expanduser("~/.local/share/waypanel/plugins/")
            self.state_file = os.path.join(
                self.path_handler.get_data_dir(), "sync_plugins", "sync_state.json"
            )

        def on_start(self):
            self.get_plugin_setting_add_hint(
                ["source_folders"],
                ["~/Git/waypanel-plugins", "~/Git/waypanel-plugins-extra/"],
                "List of paths to plugins to be synced.",
            )

            if not shutil.which("rsync"):
                self.logger.warning("rsync not found.")
                return

            self.run_sync()

        def _get_folder_mtime(self, path):
            try:
                latest = os.path.getmtime(path)
                for root, _, files in os.walk(path):
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
            # Check if root destination exists
            if not os.path.exists(self.dest_root):
                os.makedirs(self.dest_root, exist_ok=True)
                if os.path.exists(self.state_file):
                    os.remove(self.state_file)

            source_folders = self.get_plugin_setting("source_folders", [])
            if not source_folders:
                return

            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

            state = {}
            if os.path.exists(self.state_file):
                try:
                    with open(self.state_file, "r") as f:
                        state = json.load(f)
                except:
                    state = {}

            synced_any = False
            new_state = state.copy()

            for folder in source_folders:
                full_path = os.path.expanduser(folder).rstrip("/")
                if not os.path.exists(full_path):
                    continue

                # Use the source folder name as a unique sub-directory in plugins/
                # This prevents Source A and Source B from overwriting each other.
                folder_name = os.path.basename(full_path)
                specific_dest = os.path.join(self.dest_root, folder_name)

                os.makedirs(specific_dest, exist_ok=True)

                current_mtime = self._get_folder_mtime(full_path)
                last_mtime = state.get(full_path, 0)

                if current_mtime != last_mtime:
                    self.logger.info(f"Isolated sync for: {folder_name}")
                    self.cmd.run(
                        f"rsync -auz --delete '{full_path}/' '{specific_dest}/'"
                    )
                    new_state[full_path] = current_mtime
                    synced_any = True

            if synced_any:
                with open(self.state_file, "w") as f:
                    json.dump(new_state, f)

                def notify():
                    self.notify_send(
                        "Waypanel Sync",
                        "Multi-source sync complete. Deletions isolated.",
                        "plugins",
                    )
                    return False

                self.glib.timeout_add_seconds(3, notify)

        def on_reload(self):
            self.run_sync()

    return PluginSync
