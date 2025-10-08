# About Waypanel, User Guide & Overview

**Waypanel** is a lightweight, modular, and highly-customizable GTK4/Libadwaita status panel built for Wayland compositors (primarily **Wayfire** and **Sway**). It aims to feel like a modern shell panel while staying fast and extensible through plugins and a single TOML-based configuration.

> This document is an expanded, user-focused **ABOUT** that extracts implementation details from the project sources and turns them into practical guidance for end users and power users. (Technical implementation references are cited inline.)

---

## Quick start (for most users)

1.  Clone & run (developer / source install):

        git clone https://github.com/killown/waypanel.git
        cd waypanel
        python run.py      # creates venv, copies defaults, installs deps, and starts the app

`run.py` will detect or copy default configs, look for the GTK4 Layer Shell library (preloads `libgtk4-layer-shell.so` if found), create a per-user venv (`~/.local/share/waypanel/venv`) and install `requirements.txt` there before launching `main.py`.

### Restarting / stopping:

    # stop running panel processes (dev)
    pkill -f waypanel/main.py

    # or simple restart from cloned repo
    python run.py

If you installed via packages (AUR, distro packages) follow the package instructions, but the `run.py` flow above is the safe manual path for first-run configuration.

---

## Architecture (high level)

- `run.py`, prepares runtime environment: finds installed package path or development path, ensures GTK layer-shell is available (exits if not), copies default config when needed, creates a user virtualenv and installs dependencies, then runs `main.py`.
- `main.py`, orchestrates app initialization: sets up logging, finds the active config (user/system/dev locations), ensures required Wayfire plugins (when running under Wayfire), starts an IPC server thread (`EventServer`) and then loads the Panel application. It also runs a config watcher (optional) for Wayfire-specific config reloads.
- `Panel` (`src/panel.py`), the central GTK application (inherits from `Adw.Application`). It:
  - Loads and watches `config.toml` (single source of truth).
  - Sets monitor/display dimensions and creates panel windows (top/bottom/left/right) using `CreatePanel`.
  - Initializes `PluginLoader` and loads plugins asynchronously (keeps UI responsive).
- `PluginLoader`, discovers, validates and initializes plugins. It requires plugins to expose \*\*`get_plugin_metadata()`\*\* and \*\*`get_plugin_class()`\*\*. It respects the config to enable/disable plugins and uses plugin metadata (placement, priority) to place widgets into panels. User plugins live under a user plugin path (e.g. `~/.local/share/waypanel/plugins`).
- `Control Center`, a small GTK/Adwaita GUI tool to edit `config.toml` without manually editing the file. It loads TOML, generates category pages and saves changes back to the config. (Useful for non-developers.)

---

## Where Waypanel stores / finds configuration & defaults

- **User config:** `~/.config/waypanel/config.toml` (the primary location). The project prefers this location for user data.
- **System/default config:** typical system paths (e.g. `/usr/lib/waypanel/...` or distro-specific locations). On NixOS there are additional fallback paths (`/run/current-system/...`). If no user config exists, Waypanel will try to copy default config from system or development locations.

## Logs & troubleshooting basics

- **Log file:** Waypanel writes a rotating log to:

      ~/.local/state/waypanel/waypanel.log

  with small rotation (1 MB, 2 backups) and console output using Rich. Use this file as the first step when diagnosing crashes or plugin load errors.

- **When things don't start:**
  - Check `run.py` stdout/stderr, it explicitly errors out if `libgtk4-layer-shell.so` cannot be found and exits. Make sure `gtk4-layer-shell` is installed or LD_PRELOAD path set.

---

## Panels & displays (how Waypanel draws windows)

Panel windows are created using `CreatePanel` which uses `Gtk4LayerShell` to anchor panels to screen edges. The layer shell namespace, monitor selection and exclusive zone behavior (making a panel reserve space) are set there. This is how Waypanel integrates with Wayland compositors to place top/bottom/left/right bars and optionally reserve screen space.

- **Monitor selection:** Waypanel reads `panel.primary_output` (or `monitor.name` in config) and has a helper to choose a monitor (with fallbacks to compositor-reported outputs). You can pass a monitor name on the command line or let Waypanel auto-detect.

**Event system:** The project includes a central `event_manager` plugin that other plugins can use to subscribe to compositor events (view focus, mapping, title change, etc.), it dispatches events to subscribers safely on the GTK main thread using `GLib.idle_add`. This is how plugins can react to workspace/window changes in real time.

---

## IPC & compositor integration

Waypanel starts an asynchronous IPC server (`EventServer`) in a separate thread to receive commands/events from external scripts/tools. This server is launched early so plugins and the panel can use IPC-based workflows. If the IPC server fails to initialize, `main.py` will raise a `TimeoutError`.

Waypanel detects the active compositor (Wayfire via `WAYFIRE_SOCKET` or Sway via `SWAYSOCK`) and adapts, for example, it attempts to enable required Wayfire plugins automatically (when running under Wayfire). If you run Waypanel under Wayfire you should ensure the compositor has `ipc` and related plugins configured (instructions live in the repo README).

---

## Control Center (GUI configuration)

The `ControlCenter` app (a GTK4/Adwaita GUI) reads `~/.config/waypanel/config.toml`, builds a sidebar of categories and an editable content area that maps TOML types to appropriate GTK widgets (entries, switches, spinboxes). Use it if you prefer a GUI editor instead of hand-editing `config.toml`. Saved changes will write back to your user `config.toml`.

---

## Useful commands & tips for regular users

- **Recreate defaults** (if you accidentally deleted `~/.config/waypanel`):

  If your distro provides system defaults, `run.py` or `main.py` will copy them on missing config; otherwise clone the repo and run `python run.py`. See `create_first_config()` logic, it may also git clone defaults when `WAYPANEL_ALLOW_GIT_INIT=1`.

- **Check logs for errors:**

      less ~/.config/waypanel/waypanel.log

- **If panels are invisible or mis-positioned:**
  - Confirm `libgtk4-layer-shell` is installed and accessible (run-time error if not found).
  - Check `config.toml` panel entries (enabled/size/position/exclusive).

---

## Common troubleshooting checklist

- **No panel shows up**, Check `~/.config/waypanel/waypanel.log` for fatal errors (missing GTK bindings, import errors). Confirm `libgtk4-layer-shell` installed.
- **Plugins not loaded**, Look for plugin import exceptions in logs; confirm `ENABLE_PLUGIN = True` and plugin exposes required functions. Also confirm plugin directory and file permissions.
- **Wrong monitor / multi-monitor issues**, Check `monitor / primary_output` fields in config; Waypanel will fall back to compositor outputs if not specified.
- **Wayfire-specific integration problems**, Ensure the Wayfire core plugins (`ipc`, `ipc-rules`, `stipc`, and other recommended ones) are enabled in your `~/.config/wayfire.ini`.

---

## For power users / developers

- **Dev mode:** When developing, `run.py` prefers installed package paths but can run from the repo (dev path). It sets `PYTHONPATH` accordingly so your local `src/` is used if running from the cloned repo. This makes iterative development simple.
- **Logging & debugging:**

  The project uses `structlog` + a `RotatingFileHandler`; change the log level in `src/core/log_setup.py` if you need more verbosity. The default file path is `~/.config/waypanel/waypanel.log`.

- **Plugin lifecycle: (Updated for Asynchronous API)**

  Use `BasePlugin` as a superclass for common helpers (`logger`, `gtk`, `ipc_server`). The modern lifecycle is \*\*asynchronous\*\* and requires three key components:
  1.  **`def get_plugin_metadata()`:** Defines placement and dependencies.
  2.  **`def get_plugin_class()`:** The main entry point where \*\*ALL imports\*\* (e.g., `gi.repository.Gtk`, `BasePlugin`) \*\*must be deferred\*\*.
  3.  **`async def on_start()`:** The primary activation method (replaces `enable()`).
  4.  **`async def on_stop()`:** The primary deactivation method (replaces `disable()`).

  The BasePlugin still provides safe widget removal helpers.

---
