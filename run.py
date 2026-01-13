#!/usr/bin/env python3
"""
A robust application launcher for Waypanel.
"""


def setup_logging() -> None:
    """Configures a basic logger to print info to stdout and errors to stderr."""
    import sys
    import logging

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


def get_config_class():
    """Defines and returns the AppConfig dataclass for path management."""
    import os
    from pathlib import Path
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class AppConfig:
        """
        Configuration container for application directory and file paths.

        Attributes:
            app_name: The internal name of the application.
            xdg_data_home: Base directory for user-specific data files.
            xdg_config_home: Base directory for user-specific configuration files.
            xdg_cache_home: Base directory for user-specific non-essential data files.
        """

        app_name: str
        xdg_data_home: Path = Path(
            os.getenv("XDG_DATA_HOME", "~/.local/share")
        ).expanduser()
        xdg_config_home: Path = Path(
            os.getenv("XDG_CONFIG_HOME", "~/.config")
        ).expanduser()
        xdg_cache_home: Path = Path(
            os.getenv("XDG_CACHE_HOME", "~/.cache")
        ).expanduser()

        @property
        def data_dir(self) -> Path:
            return self.xdg_data_home / self.app_name

        @property
        def config_dir(self) -> Path:
            return self.xdg_config_home / self.app_name

        @property
        def backup_base_dir(self) -> Path:
            return self.xdg_cache_home / self.app_name / "backups"

        @property
        def build_dir(self) -> Path:
            """Writeable build directory in cache."""
            return self.xdg_cache_home / self.app_name / "build"

        @property
        def venv_dir(self) -> Path:
            return self.data_dir / "venv"

        @property
        def config_file(self) -> Path:
            return self.config_dir / "config.toml"

        @property
        def resources_dir(self) -> Path:
            return self.data_dir / "resources"

        @property
        def venv_bin_dir(self) -> Path:
            return self.venv_dir / "bin"

        @property
        def venv_python(self) -> Path:
            for name in ("python", "python3"):
                binary = self.venv_bin_dir / name
                if binary.exists():
                    return binary
            return self.venv_bin_dir / "python"

        @property
        def requirements_flag(self) -> Path:
            return self.venv_dir / ".requirements_installed"

    return AppConfig


def run_backup(config, max_copies: int = 10) -> None:
    """Performs a comprehensive backup of data and config directories."""
    import shutil
    import logging
    from datetime import datetime

    logging.info("Starting asynchronous data and config backup...")
    source_dirs = {"data": config.data_dir, "config": config.config_dir}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_target_root = config.backup_base_dir / f"backup_{timestamp}"

    try:
        backup_target_root.mkdir(parents=True, exist_ok=True)
        for name, source_path in source_dirs.items():
            if not source_path.is_dir():
                continue
            target_path = backup_target_root / name
            ignore = shutil.ignore_patterns("venv") if name == "data" else None
            shutil.copytree(source_path, target_path, symlinks=False, ignore=ignore)

        all_backups = sorted(
            config.backup_base_dir.glob("backup_*"), key=lambda p: p.name
        )
        if len(all_backups) > max_copies:
            for old_backup in all_backups[: len(all_backups) - max_copies]:
                shutil.rmtree(old_backup)
        logging.info("Comprehensive backup complete.")
    except Exception as e:
        logging.error("Backup failed: %s", e)


def _find_system_library(lib_name: str) -> str:
    """Locates a system library using dynamic environment paths and system utilities."""
    import os
    import ctypes.util
    from pathlib import Path

    env_override = os.getenv("WAYPANEL_GTK_LAYER_SHELL_PATH")
    if env_override and Path(env_override).is_file():
        return env_override

    search_paths = [
        "/usr/lib/libgtk4-layer-shell.so",
        "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",
        "/app/lib/libgtk4-layer-shell.so",
    ]
    for path_str in search_paths:
        if Path(path_str).is_file():
            return path_str

    find_lib = ctypes.util.find_library(lib_name.replace("lib", "").replace(".so", ""))
    return find_lib if find_lib else ""


def _install_pywayfire_from_source(config) -> None:
    """Uninstalls wayfire and installs pywayfire from GitHub into a writeable build dir."""
    import subprocess
    import shutil
    import logging

    logging.info("Performing custom pywayfire installation...")
    subprocess.run(
        [str(config.venv_python), "-m", "pip", "uninstall", "-y", "wayfire"],
        check=False,
        capture_output=True,
    )

    clone_dir = config.build_dir / "pywayfire"
    if config.build_dir.exists():
        shutil.rmtree(config.build_dir)
    config.build_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Cloning pywayfire into %s...", clone_dir)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/WayfireWM/pywayfire.git",
            str(clone_dir),
        ],
        check=True,
    )
    subprocess.run(
        [str(config.venv_python), "-m", "pip", "install", "."],
        cwd=clone_dir,
        check=True,
    )


def manage_virtual_environment(config, req_file) -> None:
    """Ensures the venv exists and all dependencies are installed."""
    import os
    import sys
    import subprocess
    import logging

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
        try:
            pip_check = subprocess.run(
                [str(config.venv_python), "-m", "pip", "--version"], capture_output=True
            )

            if pip_check.returncode != 0:
                logging.info("Bootstrapping pip into venv...")
                subprocess.run(
                    [str(config.venv_python), "-m", "ensurepip", "--upgrade"],
                    check=True,
                )

            _install_pywayfire_from_source(config)

            if req_file.is_file():
                subprocess.run(
                    [
                        str(config.venv_python),
                        "-m",
                        "pip",
                        "install",
                        "--no-cache-dir",
                        "-r",
                        str(req_file),
                    ],
                    check=True,
                )
            config.requirements_flag.touch()
        except Exception as e:
            logging.critical("Failed to install dependencies: %s", e)
            sys.exit(1)


def ensure_initial_setup(config) -> None:
    """Ensures config files and resources exist before launch."""
    import shutil
    import os
    from pathlib import Path

    if not config.config_file.is_file():
        config.config_dir.mkdir(parents=True, exist_ok=True)
        config.config_file.touch()

    if not config.resources_dir.is_dir() or not any(config.resources_dir.iterdir()):
        search_locations = [
            Path(__file__).parent.resolve() / "resources",
            Path("/app/waypanel/resources"),
            Path("/app/share/waypanel/resources"),
            Path("/usr/share/waypanel/resources"),
            Path(os.getenv("WAYPANEL_RESOURCES_PATH", "")),
        ]
        res_src = next((p for p in search_locations if p.is_dir()), None)

        if res_src:
            config.data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(res_src, config.resources_dir, dirs_exist_ok=True)


def exist_process() -> None:
    """Terminates any existing instances of the main application."""
    import subprocess
    import contextlib

    with contextlib.suppress(Exception):
        subprocess.run(
            ["pkill", "-f", "waypanel/main.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> None:
    """Main execution flow for the Waypanel launcher."""
    import os
    import sys
    import logging
    import threading
    import compileall
    import subprocess
    from pathlib import Path

    wayfire_socket_env = os.environ.get("WAYFIRE_SOCKET")

    setup_logging()
    ConfigClass = get_config_class()
    config = ConfigClass(app_name="waypanel")

    install_root = Path(__file__).parent.resolve()

    threading.Thread(target=run_backup, args=(config,), daemon=True).start()

    gtk_lib = _find_system_library("libgtk4-layer-shell.so")
    if not gtk_lib:
        logging.critical("libgtk4-layer-shell.so not found. Cannot start.")
        sys.exit(1)

    if not wayfire_socket_env:
        logging.critical(
            "Critical Failure: Environment variable 'WAYFIRE_SOCKET' is empty or unset. "
            "This prevents connection to the compositor. Ensure that the 'ipc' and 'ipc-rules' "
            "Wayfire plugins are enabled in your configuration."
        )
        sys.exit(1)

    os.environ["LD_PRELOAD"] = str(gtk_lib)
    os.environ["PYTHONPATH"] = str(install_root)

    ensure_initial_setup(config)
    manage_virtual_environment(config, install_root / "requirements.txt")

    if os.access(str(install_root), os.W_OK):
        compileall.compile_dir(str(install_root), quiet=1)

    main_py = install_root / "main.py"
    cmd = [str(config.venv_python), "-O", str(main_py)]

    while True:
        exist_process()
        try:
            result = subprocess.run(cmd, check=False)
            if result.returncode == 0 or abs(result.returncode) in {2, 15}:
                logging.info("Application session ended.")
                break
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
