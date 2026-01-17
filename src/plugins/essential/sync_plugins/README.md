# Plugin Synchronizer

A background utility for **Waypanel** designed to bridge the gap between plugin development and live deployment. It automates the mirroring of external directories into the local Waypanel environment using smart state tracking.

---

## Why This Plugin Exists

In a standard setup, Waypanel expects active plugins to reside in `~/.local/share/waypanel/plugins/`. For developers and power users, this creates several friction points:

- **Version Control Conflict:** Keeping source code in a Git workspace (e.g., `~/Git/my-plugins`) while the panel expects it in a hidden system folder.
- **Symlink Fragility:** Symbolic links can be difficult to manage, especially when moving folders or handling multiple plugin sources.
- **Deployment Overhead:** Manually copying files after every code change is tedious and prone to human error.

The **Plugin Synchronizer** acts as a bridge, allowing you to **develop anywhere and deploy automatically.**

---

## Key Benefits

- **Smart Syncing (Performance):** It scans the modification timestamps (`mtime`) of your source folders and only triggers an `rsync` if a change is detected.
- **Self-Healing State:** If you delete your local plugins folder to "reset" your environment, the plugin detects the missing directory, wipes its internal state, and re-provisions everything automatically.
- **Non-Blocking Logic:** Uses Waypanel’s internal background thread pool for all system calls via `self.cmd.run`. Your UI will never freeze or stutter during synchronization.
- **Centralized Config:** Manage all your source directories directly from the **Waypanel Control Center**.
- **Desktop Notifications:** Alerts you when a sync has occurred so you know exactly when to restart the panel to apply your changes.

---

## Technical Overview

The plugin utilizes a stateful JSON architecture to track the "last known" state of your external repositories.

| Feature             | Implementation                                              |
| :------------------ | :---------------------------------------------------------- |
| **Engine**          | `rsync` (Archive mode with update tracking)                 |
| **State Storage**   | `~/.local/share/waypanel/data/sync_plugins/sync_state.json` |
| **Deployment Path** | `~/.local/share/waypanel/plugins/`                          |
| **Logic Type**      | Background / Asynchronous                                   |

---

## Installation & Requirements

1.  **Rsync:** Ensure `rsync` is installed on your system.
    ```bash
    # Arch Linux
    sudo pacman -S rsync
    # Fedora
    sudo dnf install rsync
    ```
2.  **Placement:** Place `sync_plugins.py` in your `src/plugins/essential/` folder.
3.  **Restart:** Restart Waypanel to enable the synchronizer.

## Configuration

Once enabled, open the **Waypanel Control Center**. You will find a **Plugin Synchronizer** section where you can define a list of source folders.

**Example entries:**

- `~/Git/waypanel-plugins-extra/`
- `/home/user/Work/experimental-widgets/`

> **Warning:** Always treat your source folders as the **Source of Truth**. Files manually added to the deployment folder that do not exist in the source may be overwritten or deleted depending on sync flags.
