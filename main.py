#!/usr/bin/env python3
import logging
import os
import asyncio
import threading
import shutil
import subprocess
import toml
import json as std_json
import gi
import sys
import time
import tempfile
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.ipc.ipc_async_server import EventServer
from src.core.compositor.ipc import IPC
from src.core.log_setup import setup_logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

XDG_CONFIG_HOME = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_CACHE_HOME = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
XDG_DATA_HOME = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))

DEFAULT_CONFIG_PATH = XDG_CONFIG_HOME / "waypanel"
GTK_LAYER_SHELL_INSTALL_PATH = Path(
    os.getenv("GTK_LAYER_SHELL_PATH", XDG_DATA_HOME / "lib" / "gtk4-layer-shell")
)
WAYPANEL_REPO = "https://github.com/killown/waypanel.git"
TEMP_DIRS = {
    "gtk_layer_shell": XDG_CACHE_HOME / "gtk4-layer-shell",
    "waypanel": XDG_CACHE_HOME / "waypanel",
}
CONFIG_SUBDIR = "waypanel/config"
DEFAULT_SYSTEM_CONFIG = Path(
    os.getenv("WAYPANEL_SYSTEM_CONFIG", "/usr/share/waypanel/default-config")
)

if os.path.exists("/nix/store") and not DEFAULT_SYSTEM_CONFIG.exists():
    # Try NixOS system path
    nix_system_config = Path("/run/current-system/sw/share/waypanel/default-config")
    if nix_system_config.exists():
        DEFAULT_SYSTEM_CONFIG = nix_system_config

logger = setup_logging(level=logging.INFO)
sock = IPC()
try:
    sock.clear_bindings()
except Exception:
    pass


class ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, callback, watched_path):
        super().__init__()
        self.callback = callback
        self.last = 0.0
        self._watched = Path(watched_path).resolve()

    def on_modified(self, event):
        try:
            p = Path(event.src_path).resolve()
        except Exception:
            return
        if p == self._watched:
            now = time.time()
            if now - self.last > 1.0:
                self.last = now
                try:
                    self.callback()
                except Exception:
                    logger.exception("reload callback failed")


def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger = logging.getLogger("WaypanelLogger")
    logger.error(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
        extra={"thread_name": threading.current_thread().name},
    )


sys.excepthook = global_exception_handler


def restart_application():
    logger.info("Restarting waypanel...")
    python = sys.executable
    os.execv(python, [python] + sys.argv)


def start_config_watcher():
    if not os.getenv("WAYFIRE_SOCKET"):
        return None
    wayfire_ini = DEFAULT_CONFIG_PATH / "wayfire" / "wayfire.toml"
    if not wayfire_ini.exists():
        logger.warning(f"wayfire.toml not found at {wayfire_ini}")
        return None
    handler = ConfigReloadHandler(restart_application, wayfire_ini)
    observer = Observer()
    observer.schedule(handler, str(wayfire_ini.parent), recursive=False)
    # Auto reload the panel on config saving,
    # observer.start()
    return observer


def cleanup_resources():
    logger.info("Cleaning up resources before restart...")


def _ipc_server_target(ready_event, container, logger):
    try:
        server = EventServer(logger)
        container["instance"] = server
        ready_event.set()
        try:
            asyncio.run(server.main())
        except Exception:
            logger.exception("IPC asyncio loop failed")
    except Exception:
        logger.exception("IPC server crashed")


def start_ipc_server(logger, timeout=5.0):
    server_container = {}
    ready_event = threading.Event()
    t = threading.Thread(
        target=_ipc_server_target,
        args=(ready_event, server_container, logger),
        daemon=True,
    )
    t.start()
    if not ready_event.wait(timeout=timeout):
        raise TimeoutError("IPC server failed to initialize")
    return server_container.get("instance")


def verify_required_wayfire_plugins():
    required_plugins = {
        "stipc",
        "ipc",
        "ipc-rules",
        "resize",
        "window-rules",
        "wsets",
        "session-lock",
        "wm-actions",
        "move",
        "vswitch",
        "grid",
        "place",
        "scale",
        "alpha",
    }
    try:
        val = sock.get_option_value("core/plugins")
        enabled = []
        if isinstance(val, dict) and "value" in val:
            enabled = str(val["value"]).split()
        elif isinstance(val, str):
            enabled = val.split()
        for p in required_plugins:
            if p not in enabled:
                enabled.append(p)
        sock.set_option_values({"core/plugins": " ".join(enabled)})
    except Exception:
        logger.exception("Failed to verify wayfire plugins")


def load_panel(ipc_server):
    try:
        for ver, ver_num in [
            ("Gio", "2.0"),
            ("Gtk4LayerShell", "1.0"),
            ("Gtk", "4.0"),
            ("Gdk", "4.0"),
            ("Playerctl", "2.0"),
            ("Adw", "1"),
        ]:
            try:
                gi.require_version(ver, ver_num)
            except Exception:
                logger.warning(f"GI binding {ver} not available")
    except Exception:
        logger.warning("Some GI bindings not available")

    try:
        from src.panel import Panel
    except Exception:
        logger.exception("Failed to import Panel")
        raise

    compositor_sock = None
    utils = None

    if os.getenv("WAYFIRE_SOCKET"):
        try:
            from wayfire import WayfireSocket
            from wayfire.extra.ipc_utils import WayfireUtils

            compositor_sock = WayfireSocket()
            utils = WayfireUtils(compositor_sock)
        except Exception:
            logger.exception("Failed to initialize Wayfire socket")
    elif os.getenv("SWAYSOCK"):
        try:
            from pysway.ipc import SwayIPC

            compositor_sock = SwayIPC()
        except Exception:
            logger.warning("SwayIPC not available")

    config_path = find_config_path()
    config = load_config(config_path)
    panel_conf = config.get("panel", {}) if isinstance(config, dict) else {}
    monitor_name = (
        sys.argv[-1].strip()
        if len(sys.argv) > 1
        else get_monitor_name(panel_conf, compositor_sock)
    )

    app_name = f"com.waypanel.{monitor_name}"
    panel = Panel(application_id=app_name, ipc_server=ipc_server, logger=logger)
    panel.set_panel_instance(panel)

    append_to_env("output_name", monitor_name)

    if utils and os.getenv("WAYFIRE_SOCKET"):
        try:
            append_to_env("output_id", utils.get_output_id_by_name(monitor_name))
        except Exception:
            logger.exception("Failed to append Wayfire output id")

    if compositor_sock and os.getenv("SWAYSOCK"):
        try:
            outputs = [
                o
                for o in compositor_sock.list_outputs()
                if o.get("name") == monitor_name
            ]
            if outputs:
                append_to_env("output_id", outputs[0].get("id"))
        except Exception:
            logger.exception("Failed to append Sway output id")

    return panel


def create_first_config():
    dest = DEFAULT_CONFIG_PATH
    dest.mkdir(parents=True, exist_ok=True)
    if DEFAULT_SYSTEM_CONFIG.exists():
        try:
            shutil.copytree(DEFAULT_SYSTEM_CONFIG, dest, dirs_exist_ok=True)
            return
        except Exception:
            logger.exception("Failed copying system default config")
    if os.getenv("WAYPANEL_ALLOW_GIT_INIT", "0") != "1":
        return
    tmp = Path(tempfile.mkdtemp(prefix="waypanel_config_"))
    try:
        res = subprocess.run(
            ["git", "clone", WAYPANEL_REPO, str(tmp)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if res.returncode != 0:
            logger.error("git clone failed")
            return
        src = tmp / CONFIG_SUBDIR
        if not src.exists():
            return
        shutil.copytree(src, dest, dirs_exist_ok=True)
    finally:
        try:
            shutil.rmtree(tmp)
        except Exception:
            pass


def check_config_path():
    p = DEFAULT_CONFIG_PATH
    try:
        if p.exists() and not any(p.iterdir()):
            p.rmdir()
    except Exception:
        pass
    if not p.exists():
        create_first_config()


def append_to_env(app_name, monitor_name, env_var="waypanel"):
    existing = os.getenv(env_var, "{}")
    try:
        d = std_json.loads(existing)
    except Exception:
        d = {}
    d[app_name] = monitor_name
    os.environ[env_var] = std_json.dumps(d)


def load_config(config_path):
    p = Path(config_path)
    if not p.exists():
        logger.critical("Configuration file not found: %s", config_path)
        sys.exit(1)
    try:
        with p.open("r") as f:
            cfg = toml.load(f)
            return cfg
    except toml.TomlDecodeError as e:
        logger.critical("Failed to parse TOML: %s", e)
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected error loading config")
        sys.exit(1)


def get_monitor_name(config, sock_obj):
    conf_name = None
    try:
        if isinstance(config, dict):
            conf_name = config.get("monitor", {}).get("name")
    except Exception:
        pass
    if conf_name:
        return conf_name
    if not sock_obj:
        return "-1"
    try:
        outs = sock_obj.list_outputs()
        if not outs:
            return "-1"
        for o in outs:
            name = o.get("name") if isinstance(o, dict) else None
            if name and "-1" in name:
                return name
        first = outs[0].get("name") if isinstance(outs[0], dict) else "-1"
        return first
    except Exception:
        logger.exception("Failed to get outputs from compositor")
        return "-1"


def find_config_path():
    # First check user config directory
    home_config = DEFAULT_CONFIG_PATH / "config.toml"
    if home_config.exists():
        return str(home_config)

    # Check system-wide config locations (for NixOS and traditional distros)
    system_config_paths = [
        "/usr/lib/waypanel/waypanel/config/config.toml",
    ]

    # NixOS-specific paths
    if os.path.exists("/nix/store"):
        # Look for config in nix store (common locations)
        nix_config_paths = [
            "/run/current-system/sw/share/waypanel/config.toml",
            "/nix/var/nix/profiles/system/sw/share/waypanel/config.toml",
        ]
        system_config_paths.extend(nix_config_paths)

        # Also search in nix store for any waypanel config
        try:
            nix_configs = list(Path("/nix/store").glob("*/share/waypanel/config.toml"))
            if nix_configs:
                system_config_paths.extend(str(p) for p in nix_configs)
        except Exception:
            pass

    # Check system config paths
    for config_path in system_config_paths:
        if os.path.exists(config_path):
            return config_path

    # Fallback: check relative to script (for development)
    script_dir = Path(__file__).resolve().parent
    dev_config = script_dir.parent / "config" / "config.toml"
    if dev_config.exists():
        return str(dev_config)

    # Final fallback: use environment variable or default
    env_config = os.getenv("WAYPANEL_CONFIG_PATH")
    if env_config and os.path.exists(env_config):
        return env_config

    # If nothing found, return the user config path (will trigger create_first_config)
    return str(home_config)


def main():
    observer = None
    try:
        if os.getenv("WAYFIRE_SOCKET"):
            observer = start_config_watcher()
            try:
                verify_required_wayfire_plugins()
            except Exception:
                pass
        check_config_path()
        ipc_server = start_ipc_server(logger)
        panel = load_panel(ipc_server)
        panel.run(["waypanel"])
    except Exception:
        logger.critical("Fatal error during initialization", exc_info=True)
        raise
    finally:
        if observer:
            try:
                observer.stop()
                observer.join(timeout=1.0)
            except Exception:
                pass
        cleanup_resources()


if __name__ == "__main__":
    main()
