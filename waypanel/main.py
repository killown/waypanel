import logging
from logging.handlers import RotatingFileHandler
import os
import asyncio
import threading
import shutil
import subprocess
from ctypes import CDLL
import gi
from waypanel.src.ipc_server import ipc_async_server

# Constants
DEFAULT_CONFIG_PATH = "~/.config/waypanel"
GTK_LAYER_SHELL_INSTALL_PATH = "~/.local/lib/gtk4-layer-shell"
GTK_LAYER_SHELL_REPO = "https://github.com/wmww/gtk4-layer-shell.git"
WAYPANEL_REPO = "https://github.com/killown/waypanel.git"
TEMP_DIRS = {"gtk_layer_shell": "/tmp/gtk4-layer-shell", "waypanel": "/tmp/waypanel"}
CONFIG_SUBDIR = "waypanel/config"


# Logging Configuration
def setup_logging():
    """Configure logging with both file and console output."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file = os.path.expanduser("~/.config/waypanel/waypanel.log")

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            RotatingFileHandler(
                log_file,
                maxBytes=1024 * 1024,  # 1MB
                backupCount=3,
            ),
            logging.StreamHandler(),
        ],
    )


setup_logging()
logger = logging.getLogger(__name__)


def ipc_server():
    """Start the IPC server in an asyncio event loop."""
    logger.info("Starting IPC server")
    try:
        asyncio.run(ipc_async_server.main())
    except Exception as e:
        logger.error(f"IPC server crashed: {e}", exc_info=True)
        raise


def start_ipc_server():
    """Launch the IPC server in a daemon thread."""
    logger.debug("Spawning IPC server thread")
    ipc_thread = threading.Thread(target=ipc_server, daemon=True)
    ipc_thread.start()
    logger.info("IPC server started in background thread")


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

        from waypanel.src import panel

        return panel
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
        # Clean up existing temp dir
        if os.path.exists(temp_dir):
            logger.debug(f"Cleaning existing temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)

        # Clone and build
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
    except Exception as e:
        logger.error(f"Unexpected error during installation: {e}", exc_info=True)
        raise
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))


def create_first_config():
    """Initialize the configuration directory with default files."""
    dest_dir = os.path.expanduser(DEFAULT_CONFIG_PATH)
    temp_dir = TEMP_DIRS["waypanel"]

    try:
        # Ensure destination directory exists
        os.makedirs(dest_dir, exist_ok=True)

        # Clean up existing temp dir
        if os.path.exists(temp_dir):
            logger.debug(f"Cleaning existing temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)

        logger.info(f"Cloning repository: {WAYPANEL_REPO}")
        subprocess.run(["git", "clone", WAYPANEL_REPO, temp_dir], check=True)

        src_config_dir = os.path.join(temp_dir, CONFIG_SUBDIR)

        # Create config directory if it doesn't exist
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
            logger.debug(f"Cleaning up temporary directory: {temp_dir}")
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
    logger.debug("No typelib files found")
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

    error_msg = f"No .typelib files found in {primary_path} or {fallback_path}"
    logger.error(error_msg)
    raise FileNotFoundError(error_msg)


def main():
    """Main application entry point."""
    try:
        logger.info("Starting Waypanel initialization")

        layer_shell_check()
        check_config_path()
        start_ipc_server()

        logger.info("Loading panel...")
        panel = load_panel()

        logger.info("Starting panel...")
        panel.run()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
