#!/usr/bin/env python3
import logging
from logging.handlers import RotatingFileHandler
import os
import asyncio
import threading
import shutil
import subprocess
from ctypes import CDLL
import toml
import orjson as json
import gi
import sys
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from waypanel.src.ipc.ipc_async_server import WayfireEventServer
from wayfire import WayfireSocket
from waypanel.src.core.log_setup import setup_logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sock = WayfireSocket()
# Constants
DEFAULT_CONFIG_PATH = "~/.config/waypanel"
GTK_LAYER_SHELL_INSTALL_PATH = "~/.local/lib/gtk4-layer-shell"
GTK_LAYER_SHELL_REPO = "https://github.com/wmww/gtk4-layer-shell.git"
WAYPANEL_REPO = "https://github.com/killown/waypanel.git"
TEMP_DIRS = {"gtk_layer_shell": "/tmp/gtk4-layer-shell", "waypanel": "/tmp/waypanel"}
CONFIG_SUBDIR = "waypanel/config"


# use param logging.DEBUG for detailed output
logger = setup_logging(level=logging.INFO)


class ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.last_modified = time.time()

    def on_modified(self, event):
        if event.src_path == os.path.expanduser(os.getenv("WAYFIRE_CONFIG_FILE")):
            now = time.time()
            if now - self.last_modified > 1:  # 1 second debounce
                logger.info("wayfire.ini modified - triggering reload")
                self.last_modified = now
                self.callback()


def restart_application():
    """Fully restart the current process"""
    logger.info("Restarting waypanel...")
    python = sys.executable
    os.execl(python, python, *sys.argv)


def start_config_watcher():
    """Start watching wayfire.ini for changes"""
    wayfire_ini = os.path.expanduser(os.getenv("WAYFIRE_CONFIG_FILE"))
    if not os.path.exists(wayfire_ini):
        logger.warning(
            f"wayfire.ini not found at {wayfire_ini} - config watching disabled"
        )
        return None

    event_handler = ConfigReloadHandler(restart_application)
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(wayfire_ini))
    observer.start()
    return observer


def cleanup_resources():
    """Clean up resources before restart"""
    logger.info("Cleaning up resources before restart...")
    # Add any specific cleanup needed here
    pass


def ipc_server():
    """Start the IPC server in an asyncio event loop."""
    logger.info("Starting IPC server")
    try:
        server = WayfireEventServer()
        asyncio.run(server.main())
    except Exception as e:
        logger.error(f"IPC server crashed: {e}", exc_info=True)
        raise


def start_ipc_server():
    """Launch the IPC server in a daemon thread."""
    logger.debug("Spawning IPC server thread")
    ipc_thread = threading.Thread(target=ipc_server, daemon=True)
    ipc_thread.start()
    logger.info("IPC server started in background thread")


def verify_required_wayfire_plugins():
    """
    Verify that all required plugins are enabled.
    Exit the application if any required plugins are missing.
    """
    logger.debug("Verifying required plugins...")

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
    }

    enabled_plugins = set(sock.get_option_value("core/plugins")["value"].split())
    missing_plugins = required_plugins - enabled_plugins

    if missing_plugins:
        logger.error(
            f"\n\033[91mERROR:\033[0m The following plugins are required to start the shell: {missing_plugins}"
        )
        logger.info(f"Required Plugin List: {required_plugins}")
        sys.exit()

    logger.info("All required plugins are enabled.")


def load_panel():
    """Load and configure the panel with proper typelib paths."""
    primary_path = os.path.expanduser(
        f"{GTK_LAYER_SHELL_INSTALL_PATH}/lib/girepository-1.0"
    )
    fallback_path = os.path.expanduser(
        f"{GTK_LAYER_SHELL_INSTALL_PATH}/lib64/girepository-1.0"
    )

    set_gi_typelib_path(primary_path, fallback_path)

    try:
        # Configure GI requirements
        gi.require_version("Gio", "2.0")
        CDLL("libgtk4-layer-shell.so")
        gi.require_version("Gtk4LayerShell", "1.0")
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("Playerctl", "2.0")
        gi.require_version("Adw", "1")

        from waypanel.src.panel import Panel
        from wayfire import WayfireSocket
        from wayfire.extra.ipc_utils import WayfireUtils

        sock = WayfireSocket()
        utils = WayfireUtils(sock)

        config_path = find_config_path()
        config = load_config(config_path)["panel"]

        monitor_name = get_monitor_name(config, sock)
        if len(sys.argv) > 1:
            monitor_name = sys.argv[-1].strip()

        app_name = f"com.waypanel.{monitor_name}"
        panel = Panel(application_id=app_name, logger=logger)
        panel.set_panel_instance(panel)

        append_to_env("output_name", monitor_name)
        append_to_env("output_id", utils.get_output_id_by_name(monitor_name))

        panel.run(None)
        # sock.watch(["event"])

        while True:
            msg = sock.read_message()
            if "output" in msg and monitor_name == msg["output-data"]["name"]:
                if msg["event"] == "output-added":
                    panel.run(None)
    except ImportError as e:
        logger.error(f"Failed to load panel: {e}", exc_info=True)
        raise


def layer_shell_check():
    """Verify and install gtk4-layer-shell if missing."""
    install_path = os.path.expanduser(GTK_LAYER_SHELL_INSTALL_PATH)
    temp_dir = TEMP_DIRS["gtk_layer_shell"]
    build_dir = "build"

    if os.path.exists(install_path):
        logger.info("gtk4-layer-shell is already installed")
        return

    logger.info("gtk4-layer-shell not found. Installing...")

    try:
        if os.path.exists(temp_dir):
            logger.debug(f"Cleaning existing temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)

        logger.info(f"Cloning repository: {GTK_LAYER_SHELL_REPO}")
        subprocess.run(["git", "clone", GTK_LAYER_SHELL_REPO, temp_dir], check=True)

        os.chdir(temp_dir)
        logger.info("Configuring build with Meson...")
        subprocess.run(
            [
                "meson",
                "setup",
                f"--prefix={install_path}",
                "-Dexamples=true",
                "-Ddocs=true",
                "-Dtests=true",
                build_dir,
            ],
            check=True,
        )

        logger.info("Building with Ninja...")
        subprocess.run(["ninja", "-C", build_dir], check=True)

        logger.info("Installing...")
        subprocess.run(["ninja", "-C", build_dir, "install"], check=True)

        logger.info("gtk4-layer-shell installation complete")
    except subprocess.CalledProcessError as e:
        logger.error(f"Installation failed: {e}", exc_info=True)
        raise
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))


def create_first_config():
    """Initialize the configuration directory with default files."""
    dest_dir = os.path.expanduser(DEFAULT_CONFIG_PATH)
    temp_dir = TEMP_DIRS["waypanel"]

    try:
        os.makedirs(dest_dir, exist_ok=True)

        if os.path.exists(temp_dir):
            logger.debug(f"Cleaning existing temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)

        logger.info(f"Cloning repository: {WAYPANEL_REPO}")
        subprocess.run(["git", "clone", WAYPANEL_REPO, temp_dir], check=True)

        src_config_dir = os.path.join(temp_dir, CONFIG_SUBDIR)
        if not os.path.exists(src_config_dir):
            logger.info(f"Creating missing config directory: {src_config_dir}")
            os.makedirs(src_config_dir)

        logger.info(f"Copying config files from {src_config_dir} to {dest_dir}")
        shutil.copytree(src_config_dir, dest_dir, dirs_exist_ok=True)

        logger.info("Configuration setup completed successfully")
    except Exception as e:
        logger.error(f"Failed to create config: {e}", exc_info=True)
        raise
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def check_config_path():
    """Check and initialize configuration if needed."""
    config_path = os.path.expanduser(DEFAULT_CONFIG_PATH)

    if os.path.exists(config_path):
        if not os.listdir(config_path):
            logger.info(f"Removing empty config directory: {config_path}")
            os.rmdir(config_path)

    if not os.path.exists(config_path):
        logger.info("Config directory not found, creating initial configuration")
        create_first_config()


def find_typelib_path(base_path):
    """Search for typelib files in the given directory tree."""
    logger.debug(f"Searching for typelib files in: {base_path}")
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith(".typelib"):
                logger.debug(f"Found typelib at: {root}")
                return root
    return None


def set_gi_typelib_path(primary_path, fallback_path):
    """Set GI_TYPELIB_PATH environment variable."""
    primary_typelib_path = find_typelib_path(primary_path)
    if primary_typelib_path:
        os.environ["GI_TYPELIB_PATH"] = primary_typelib_path
        logger.info(f"GI_TYPELIB_PATH set to: {primary_typelib_path}")
        return

    fallback_typelib_path = find_typelib_path(fallback_path)
    if fallback_typelib_path:
        os.environ["GI_TYPELIB_PATH"] = fallback_typelib_path
        logger.info(f"GI_TYPELIB_PATH set to fallback path: {fallback_typelib_path}")
        return

    raise FileNotFoundError(
        f"No .typelib files found in {primary_path} or {fallback_path}"
    )


def append_to_env(app_name, monitor_name, env_var="waypanel"):
    existing_env = os.getenv(env_var, "{}")
    env_dict = json.loads(existing_env)
    env_dict[app_name] = monitor_name
    os.environ[env_var] = json.dumps(env_dict).decode("utf-8")


def load_config(config_path):
    """
    Load the configuration file or exit the application with an error message.
    Args:
        config_path (str): Path to the configuration file.
    Returns:
        dict: Parsed TOML configuration.
    """
    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found at '{config_path}'.")
        print("The panel cannot run without a valid configuration file.")
        print("Please ensure the file exists or reinstall the application.")
        sys.exit(1)  # Exit with a non-zero status code to indicate failure

    try:
        with open(config_path, "r") as f:
            config = toml.load(f)
            if not config:
                raise ValueError("Configuration file is empty.")
            return config
    except toml.TomlDecodeError as e:
        print(f"Error: Failed to parse the configuration file at '{config_path}'.")
        print(f"Details: {e}")
        print("Please fix the file or replace it with a valid configuration.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error while loading the configuration file: {e}")
        sys.exit(1)


def get_monitor_name(config, sock):
    monitor = next(
        (output for output in sock.list_outputs() if "-1" in output["name"]),
        sock.list_outputs()[0],
    )
    monitor_name = monitor.get("name")
    return config.get("monitor", {}).get("name", monitor_name)


def find_config_path():
    home_config_path = os.path.join(
        os.path.expanduser("~"), ".config/waypanel", "waypanel.toml"
    )
    if os.path.exists(home_config_path):
        print(f"using {home_config_path}")
        return home_config_path

    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_config_path = os.path.join(
        os.path.dirname(script_dir), "config/waypanel.toml"
    )
    print(f"Using default config path: {default_config_path}")

    return default_config_path


def main():
    """Main application entry point."""
    config_observer = None
    try:
        logger.info("Starting Waypanel initialization")

        # Start config watcher first
        config_observer = start_config_watcher()
        verify_required_wayfire_plugins()
        layer_shell_check()
        check_config_path()
        start_ipc_server()

        logger.info("Loading panel...")
        panel = load_panel()

        logger.info("Starting panel...")
        panel.run(logger=logger)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        if config_observer:
            config_observer.stop()
            config_observer.join()
        cleanup_resources()


if __name__ == "__main__":
    main()
