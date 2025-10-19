#!/usr/bin/env python3
"""
A robust application launcher for Waypanel.

This script prepares the runtime environment by setting up necessary
directories, managing a virtual environment with custom dependencies using 'uv',
and then executing the main application.
"""

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

APP_NAME = "waypanel"
PYWAYFIRE_REPO_URL = "https://github.com/WayfireWM/pywayfire.git"


@dataclass(frozen=True)
class AppConfig:
    """Encapsulates all configuration and path details for the application."""

    app_name: str
    xdg_data_home: Path = Path(
        os.getenv("XDG_DATA_HOME", "~/.local/share")
    ).expanduser()
    xdg_config_home: Path = Path(os.getenv("XDG_CONFIG_HOME", "~/.config")).expanduser()
    xdg_cache_home: Path = Path(os.getenv("XDG_CACHE_HOME", "~/.cache")).expanduser()

    @property
    def data_dir(self) -> Path:
        """The main data directory for the application."""
        return self.xdg_data_home / self.app_name

    @property
    def config_dir(self) -> Path:
        """The configuration directory for the application."""
        return self.xdg_config_home / self.app_name

    @property
    def backup_base_dir(self) -> Path:
        """The base directory for all backups."""
        return self.xdg_cache_home / self.app_name / "backups"

    @property
    def venv_dir(self) -> Path:
        """The path to the application's virtual environment."""
        return self.data_dir / "venv"

    @property
    def config_file(self) -> Path:
        """The path to the main configuration file."""
        return self.config_dir / "config.toml"

    @property
    def resources_dir(self) -> Path:
        """The path where user-facing resources are stored."""
        return self.data_dir / "resources"

    @property
    def venv_bin_dir(self) -> Path:
        """The 'bin' directory within the virtual environment."""
        return self.venv_dir / "bin"

    @property
    def venv_python(self) -> Path:
        """The path to the 'python' executable in the venv."""
        return self.venv_bin_dir / "python"

    @property
    def requirements_flag(self) -> Path:
        """A flag file to indicate that dependencies are installed."""
        return self.venv_dir / ".requirements_installed"


def setup_logging():
    """Configures a basic logger to print info to stdout and errors to stderr."""
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
        stream=sys.stdout,
    )
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    stderr_handler.setFormatter(formatter)
    logging.getLogger().addHandler(stderr_handler)


def _enforce_backup_retention(backup_dir: Path, max_copies: int):
    """
    Removes the oldest backup folders if the maximum limit is exceeded.

    Args:
        backup_dir: The directory containing backups.
        max_copies: The maximum number of backups to retain.
    """
    import shutil

    try:
        all_backups = sorted(backup_dir.glob("backup_*"), key=lambda p: p.name)
        if len(all_backups) > max_copies:
            to_remove = all_backups[: len(all_backups) - max_copies]
            logging.info(
                "Backup limit (%d) exceeded. Removing %d oldest backup(s).",
                max_copies,
                len(to_remove),
            )
            for old_backup in to_remove:
                logging.info("Removing old backup: %s", old_backup.name)
                shutil.rmtree(old_backup)
    except Exception as e:
        logging.error("Failed to manage backup retention: %s", e)


def run_backup(config: AppConfig, max_copies: int = 10):
    """
    Performs a comprehensive backup of data and config directories.

    This function is designed to be run in a separate thread.

    Args:
        config: The application configuration object.
        max_copies: The maximum number of backups to retain.
    """
    import shutil

    logging.info("Starting asynchronous data and config backup...")
    source_dirs = {"data": config.data_dir, "config": config.config_dir}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_target_root = config.backup_base_dir / f"backup_{timestamp}"
    success = True
    try:
        backup_target_root.mkdir(parents=True, exist_ok=True)
        for name, source_path in source_dirs.items():
            if not source_path.is_dir():
                logging.warning(
                    "Backup source '%s' directory not found: %s. Skipping.",
                    name,
                    source_path,
                )
                continue
            target_path = backup_target_root / name
            ignore = shutil.ignore_patterns("venv") if name == "data" else None
            try:
                shutil.copytree(source_path, target_path, symlinks=False, ignore=ignore)
                status_msg = " (venv excluded)" if name == "data" else ""
                logging.info("Backed up %s to %s%s", name, target_path, status_msg)
            except Exception as e:
                logging.error("Failed to backup '%s' (%s): %s", name, source_path, e)
                success = False
        if success:
            logging.info("Comprehensive backup complete.")
            _enforce_backup_retention(config.backup_base_dir, max_copies)
        else:
            logging.error("Backup completed with errors. Retention management skipped.")
    except Exception as e:
        logging.critical("Failed to create backup root directory: %s", e)


def _find_system_library(lib_name: str, search_paths: List[str]) -> Optional[Path]:
    """Finds a library file in a list of predefined paths, including Nix store."""
    candidates = [Path(p) for p in search_paths]
    for lib_path in candidates:
        if lib_path.is_file():
            return lib_path
    nix_store = Path("/nix/store")
    if nix_store.is_dir():
        try:
            nix_libs = nix_store.glob(f"**/{lib_name}")
            return next(nix_libs, None)
        except Exception:
            pass
    return None


def _find_package_path(app_name: str, xdg_data_home: Path) -> Optional[Path]:
    """
    Finds the installed package path using absolute glob patterns.
    """
    import glob

    home = Path.home()
    candidate_patterns = [
        f"{xdg_data_home}/lib/python*/site-packages",
        f"{home}/.local/lib/python*/site-packages",
        "/usr/lib/python*/dist-packages",
        "/usr/lib/python*/site-packages",
        "/usr/local/lib/python*/dist-packages",
        "/usr/local/lib/python*/site-packages",
    ]
    for pattern in candidate_patterns:
        for path_str in glob.glob(pattern):
            path = Path(path_str)
            pkg_path = path / app_name
            if pkg_path.is_dir():
                return pkg_path
    return None


def _install_pywayfire_from_source(config: AppConfig) -> None:
    """
    Uninstalls wayfire and installs pywayfire from its GitHub repository using uv.

    Args:
        config: The application configuration object.

    Raises:
        subprocess.CalledProcessError: If any command fails.
        FileNotFoundError: If 'git' or 'uv' command is not found.
    """
    import subprocess
    import tempfile

    logging.info("Performing custom pywayfire installation...")
    logging.info("Uninstalling any existing 'wayfire' package...")
    subprocess.run(
        [
            "uv",
            "pip",
            "uninstall",
            "-y",
            "wayfire",
            f"--python={config.venv_python}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = Path(tmpdir) / "pywayfire"
        logging.info("Cloning %s into temporary directory...", PYWAYFIRE_REPO_URL)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                PYWAYFIRE_REPO_URL,
                str(clone_dir),
            ],
            check=True,
        )
        logging.info("Installing pywayfire from source using uv...")
        subprocess.run(
            ["uv", "pip", "install", ".", f"--python={config.venv_python}"],
            cwd=clone_dir,
            check=True,
        )
    logging.info("Custom pywayfire installation successful.")


def manage_virtual_environment(config: AppConfig, req_file: Path):
    """
    Ensures the venv exists and all dependencies are installed using uv.

    Args:
        config: The application configuration object.
        req_file: Path to the requirements.txt file.
    """
    import subprocess

    if not config.venv_dir.is_dir():
        logging.info("Creating virtual environment...")
        config.venv_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "venv",
                "--system-site-packages",
                str(config.venv_dir),
            ],
            check=True,
        )
    os.environ["PATH"] = f"{config.venv_bin_dir}{os.pathsep}{os.environ['PATH']}"
    if not config.requirements_flag.is_file():
        logging.info("Installing dependencies...")
        try:
            _install_pywayfire_from_source(config)
            logging.info("Installing dependencies from %s using uv...", req_file)
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--no-cache-dir",
                    "-r",
                    str(req_file),
                    f"--python={config.venv_python}",
                ],
                check=True,
            )
            config.requirements_flag.touch()
            logging.info("All dependencies installed successfully.")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logging.critical("Failed to install dependencies: %s", e)
            if isinstance(e, FileNotFoundError):
                logging.critical(
                    "Ensure 'git' and 'uv' are installed and in your PATH."
                )
            sys.exit(1)


def ensure_initial_setup(config: AppConfig, installed_path: Optional[Path]):
    """
    Ensures config files and resources exist before launch.

    Args:
        config: The application configuration object.
        installed_path: The discovered path of the installed package, if any.
    """
    import shutil

    if not config.config_file.is_file():
        logging.info(
            "Config file not found. Creating empty config at %s", config.config_file
        )
        config.config_dir.mkdir(parents=True, exist_ok=True)
        config.config_file.touch()
    if not config.resources_dir.is_dir():
        logging.info(
            "Resources not found at %s. Attempting to copy defaults...",
            config.resources_dir,
        )
        script_dir = Path(__file__).parent.resolve()
        search_paths = [
            (script_dir / "resources", "dev path (flat)"),
            (script_dir / APP_NAME / "resources", "dev path (nested)"),
            (Path(f"/usr/lib/{APP_NAME}/resources"), "system path"),
        ]
        if installed_path:
            search_paths.insert(2, (installed_path / "resources", "installed path"))
        for src, desc in search_paths:
            if src.is_dir():
                try:
                    shutil.copytree(src, config.resources_dir)
                    logging.info("Default resources copied from %s: %s", desc, src)
                    return
                except Exception as e:
                    logging.critical("Failed to copy resources from %s: %s", src, e)
                    sys.exit(1)
        logging.warning("No default resources found. Proceeding without them.")


def exist_process():
    """Terminates any existing instances of the main application."""
    import contextlib
    import subprocess

    with contextlib.suppress(Exception):
        subprocess.run(
            ["pkill", "-f", f"{APP_NAME}/main.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main():
    """
    Main execution flow for the Waypanel launcher.

    Handles initial setup, environment management, and launches the application
    with a retry mechanism for transient startup failures.
    """
    import compileall
    import contextlib
    import subprocess
    import threading

    setup_logging()
    config = AppConfig(app_name=APP_NAME)
    script_dir = Path(__file__).parent.resolve()

    threading.Thread(target=run_backup, args=(config,), daemon=True).start()

    installed_path: Optional[Path] = _find_package_path(
        config.app_name, config.xdg_data_home
    )
    if installed_path and installed_path.is_dir():
        main_py_dir: Path = installed_path
        logging.info("Using installed package from: %s", main_py_dir)
    else:
        main_py_dir = script_dir
        logging.info("Using development path: %s", main_py_dir)

    req_file: Path = main_py_dir / "requirements.txt"
    main_py_file: Path = main_py_dir / "main.py"
    os.environ["PYTHONPATH"] = str(main_py_dir)

    # Environment setup for libgtk4-layer-shell.
    gtk_lib: Optional[Path] = _find_system_library(
        lib_name="libgtk4-layer-shell.so",
        search_paths=[
            "/usr/lib/libgtk4-layer-shell.so",
            "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",
            "/usr/lib64/libgtk4-layer-shell.so",
            str(
                config.xdg_data_home / "lib/gtk4-layer-shell/lib/libgtk4-layer-shell.so"
            ),
        ],
    )
    if not gtk_lib:
        logging.critical("libgtk4-layer-shell.so not found. Cannot start.")
        sys.exit(1)

    os.environ["LD_PRELOAD"] = str(gtk_lib)
    logging.info("Using GTK4 Layer Shell: %s", gtk_lib)

    ensure_initial_setup(config, installed_path)
    manage_virtual_environment(config, req_file)

    logging.info("Compiling Python source files to bytecode (.pyc)...")
    with contextlib.suppress(Exception):
        compileall.compile_dir(str(main_py_dir), quiet=1, force=False)
        logging.info("Compilation complete (skipped if up-to-date).")

    SUCCESS_EXIT_CODE: int = 0

    cmd: List[str] = [str(config.venv_python), "-O", str(main_py_file)]

    while True:
        exist_process()
        try:
            result: subprocess.CompletedProcess = subprocess.run(
                cmd,
                check=False,  # Important: Do not raise exception on non-zero exit
            )

            if result.returncode == SUCCESS_EXIT_CODE:
                logging.info(
                    "Application exited successfully (code 0)."
                    " Assuming user-initiated exit or success."
                )
                return
            is_user_kill_signal: bool = result.returncode < 0 and abs(
                result.returncode
            ) in {2, 15}  # 2=SIGINT, 15=SIGTERM

            if is_user_kill_signal:
                logging.info(
                    "Application terminated by user signal (exit code %d)."
                    " Aborting retry loop.",
                    result.returncode,
                )
                sys.exit(result.returncode)

        except FileNotFoundError:
            logging.critical(
                "Could not find the main application script at %s or venv Python."
                " Aborting launch.",
                main_py_file,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
