#!/usr/bin/env python3
import logging
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
import tempfile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.ipc.ipc_async_server import EventServer
from src.core.compositor.ipc import IPC
from src.core.log_setup import setup_logging


sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sock = IPC()


# Constants
DEFAULT_CONFIG_PATH = "~/.config/waypanel"
GTK_LAYER_SHELL_INSTALL_PATH = "~/.local/lib/gtk4-layer-shell"
GTK_LAYER_SHELL_REPO = "https://github.com/wmww/gtk4-layer-shell.git"
WAYPANEL_REPO = "https://github.com/killown/waypanel.git"
TEMP_DIRS = {
    "gtk_layer_shell": "~/.cache/gtk4-layer-shell",
    "waypanel": "~/.cache/waypanel",
}
CONFIG_SUBDIR = "waypanel/config"


# use param logging.DEBUG for detailed output
logger = setup_logging(level=logging.INFO)


# FIXME: Clear registered bindings
# Prevents duplicate bindings when the panel restarts, avoiding multiple command calls
# Also removes any bindings registered by external scripts
# If you are sure you would disable this, grep the panel dir to look for register_bindings
# so you can disable those plugins using it and don't create any conflicts
# a wayfire PR is necessary to override existent bindings instead of duplicating it
sock.clear_bindings()


class ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, callback):
        """Initialize the handler to monitor configuration file changes.

        Sets up a file system event handler to detect modifications to the wayfire.ini
        configuration file, with a debounce mechanism to prevent rapid successive reloads.

        Args:
            callback: Function to be called when a valid config modification is detected.
        """
        super().__init__()
        self.callback = callback
        self.last_modified = time.time()

    def on_modified(self, event):
        """Handle the file modified event for wayfire.ini.

        If the modified file is wayfire.ini and the debounce delay has passed,
        triggers the reload callback.

        Args:
            event: The file system event object containing metadata about the change.
        """
        if event.src_path == os.path.expanduser(
            "~/.config/waypanel/wayfire/wayfire.toml"
        ):
            now = time.time()
            if now - self.last_modified > 1:  # 1 second debounce
                logger.info("wayfire.ini modified - triggering reload")
                self.last_modified = now
                self.callback()


def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions globally and log detailed error information.

    This function is intended to be used as a global exception handler to catch and log
    unhandled exceptions, providing detailed context including the thread name where
    the exception occurred. It ensures that KeyboardInterrupt exceptions are handled
    by the default handler.

    Args:
        exc_type: The type of the exception.
        exc_value: The exception instance.
        exc_traceback: A traceback object encapsulating the call stack at the point
                       where the exception was raised.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger = logging.getLogger("WaypanelLogger")
    logger.error(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
        extra={
            "thread_name": threading.current_thread().name
        },  # Renamed 'thread' to 'thread_name'
    )


sys.excepthook = global_exception_handler


def restart_application():
    """Fully restart the current process"""
    logger.info("Restarting waypanel...")
    python = sys.executable
    os.execl(python, python, *sys.argv)


def start_config_watcher():
    """Start watching wayfire.ini for changes"""
    if os.getenv("WAYFIRE_SOCKET"):
        wayfire_ini = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
        if not os.path.exists(wayfire_ini):
            logger.warning(
                f"wayfire.ini not found at {wayfire_ini} - config watching disabled"
            )
            return None

        event_handler = ConfigReloadHandler(restart_application)
        observer = Observer()
        observer.schedule(event_handler, path=os.path.dirname(wayfire_ini))
        # observer.start()
        return observer


def cleanup_resources():
    """Clean up resources before restart"""
    logger.info("Cleaning up resources before restart...")
    # Add any specific cleanup needed here
    pass


def ipc_server(logger):
    """Start the IPC server in an asyncio event loop."""
    logger.info("Starting IPC server")
    try:
        server = EventServer(logger)
        asyncio.run(server.main())
    except Exception as e:
        logger.error(f"IPC server crashed: {e}", exc_info=True)
        raise


def start_ipc_server(logger):
    """
    Launch the IPC server in a daemon thread and return the server instance.
    Args:
        logger: The logger instance for logging messages.
    Returns:
        WayfireEventServer: The instance of the IPC server.
    """
    logger.debug("Spawning IPC server thread")

    # Create a container to store the server instance
    server_container = {}

    def _ipc_server_wrapper():
        """Wrapper to start the IPC server and store its instance."""
        try:
            logger.info("Starting IPC server")
            server = EventServer(logger)
            server_container["instance"] = server
            asyncio.run(server.main())
        except Exception as e:
            logger.error(f"IPC server crashed: {e}", exc_info=True)
            raise

    # Start the IPC server in a daemon thread
    ipc_thread = threading.Thread(target=_ipc_server_wrapper, daemon=True)
    ipc_thread.start()
    logger.info("IPC server started in background thread")

    # Wait briefly to ensure the server instance is created
    while "instance" not in server_container:
        time.sleep(0.1)  # Poll until the server instance is available

    return server_container["instance"]


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
        "alpha",
    }

    enabled_plugins = sock.get_option_value("core/plugins")["value"].split()

    for plugin_name in required_plugins:
        if plugin_name not in enabled_plugins:
            enabled_plugins.append(plugin_name)

    # Update configuration
    sock.set_option_values({"core/plugins": " ".join(enabled_plugins)})
    logger.info("All required plugins are enabled.")


def load_panel(ipc_server):
    # FIXME: need refactor to work well any supported compositor
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

        from src.panel import Panel
        from wayfire import WayfireSocket
        from wayfire.extra.ipc_utils import WayfireUtils

        sock = None
        utils = None
        if os.getenv("WAYFIRE_SOCKET"):
            sock = WayfireSocket()
            utils = WayfireUtils(sock)
        if os.getenv("SWAYSOCK") and not os.getenv("WAYFIRE_SOCKET"):
            from pysway.ipc import SwayIPC

            sock = SwayIPC()

        config_path = find_config_path()
        config = load_config(config_path)["panel"]

        monitor_name = get_monitor_name(config, sock)
        if len(sys.argv) > 1:
            monitor_name = sys.argv[-1].strip()

        app_name = f"com.waypanel.{monitor_name}"
        panel = Panel(application_id=app_name, ipc_server=ipc_server, logger=logger)
        panel.set_panel_instance(panel)

        append_to_env("output_name", monitor_name)
        if utils:
            if os.getenv("WAYFIRE_SOCKET"):
                append_to_env("output_id", utils.get_output_id_by_name(monitor_name))
        if sock:
            if os.getenv("SWAYSOCK"):
                output = [i for i in sock.list_outputs() if i["name"] == monitor_name][
                    0
                ]
                append_to_env("output_id", output["id"])

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
    logger.info(f"Creating config directory at: {dest_dir}")

    # Create destination dir
    os.makedirs(dest_dir, exist_ok=True)

    # Create a secure temp dir
    temp_dir = tempfile.mkdtemp(prefix="waypanel_config_")
    logger.debug(f"Using temporary directory: {temp_dir}")

    try:
        # Clone repo
        logger.info(f"Cloning repository: {WAYPANEL_REPO}")
        result = subprocess.run(
            ["git", "clone", WAYPANEL_REPO, temp_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error(f"Git clone failed:\n{result.stdout}")
            raise RuntimeError("Failed to clone repository")

        # Determine source config path
        src_config_dir = os.path.join(temp_dir, CONFIG_SUBDIR)
        logger.debug(f"Looking for config in: {src_config_dir}")

        if not os.path.exists(src_config_dir):
            logger.warning(
                f"Config subdir '{CONFIG_SUBDIR}' not found. Creating empty one."
            )
            os.makedirs(src_config_dir)

        if not os.listdir(src_config_dir):
            logger.warning(f"Source config directory is empty: {src_config_dir}")

        # Copy files
        logger.info(f"Copying config files from {src_config_dir} to {dest_dir}")
        shutil.copytree(src_config_dir, dest_dir, dirs_exist_ok=True)
        logger.info("Configuration setup completed successfully")

    except Exception as e:
        logger.critical(f"Failed to create config: {e}", exc_info=True)
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
    """Update the specified environment variable with a JSON object mapping app_name to monitor_name.

    This function reads the current value of the environment variable (or starts with an empty object),
    adds or updates the entry for app_name with the provided monitor_name, and writes the updated
    JSON back to the environment variable.

    Args:
        app_name (str): The application name used as the key in the JSON object.
        monitor_name (str): The monitor name associated with the application.
        env_var (str, optional): The name of the environment variable to update. Defaults to "waypanel".
    """
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
    """Retrieve the name of the monitor based on configuration or default output.

    Determines which monitor name to use by first checking the command line arguments,
    then the configuration file, and finally falling back to a default monitor name
    from the compositor's list of outputs.

    Args:
        config (dict): Configuration dictionary potentially containing a "monitor" section.
        sock: Socket object used to interact with the compositor for retrieving outputs.

    Returns:
        str: The name of the selected monitor. Defaults to "-1" if no suitable monitor is found.
    """
    monitor = next(
        (output for output in sock.list_outputs() if "-1" in output["name"]),
        sock.list_outputs()[0],
    )
    monitor_name = monitor.get("name")
    return config.get("monitor", {}).get("name", monitor_name)


def find_config_path():
    """Determine the correct path to the config.toml configuration file.

    Checks two potential locations in order of preference:
    1. User-specific config in ~/.config/waypanel/
    2. Default config relative to the script's location

    Returns:
        str: Full path to the config.toml configuration file.
    """
    home_config_path = os.path.join(
        os.path.expanduser("~"), ".config/waypanel", "config.toml"
    )
    if os.path.exists(home_config_path):
        print(f"using {home_config_path}")
        return home_config_path

    config_dir = os.path.dirname(os.path.abspath(__file__))
    default_config_path = os.path.join(
        os.path.dirname(config_dir), "config/config.toml"
    )
    print(f"Using default config path: {default_config_path}")

    return default_config_path


def main():
    """Main application entry point."""
    config_observer = None
    try:
        logger.info("Starting Waypanel initialization")

        # Start config watcher first
        config_observer = None
        if os.getenv("WAYFIRE_SOCKET"):
            config_observer = start_config_watcher()
        if os.getenv("WAYFIRE_SOCKET"):
            verify_required_wayfire_plugins()
        layer_shell_check()
        check_config_path()
        ipc_server = start_ipc_server(logger)

        logger.info("Loading panel...")
        panel = load_panel(ipc_server)

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
