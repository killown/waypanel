import os
import sys
import shutil
import glob
import subprocess
from datetime import datetime
import threading
import compileall


# =========================================================
# BACKUP AND RETENTION HELPER FUNCTIONS
# =========================================================


def _enforce_retention_policy(backup_base_dir, max_copies):
    """Removes the oldest backup folders if the maximum limit is exceeded."""
    try:
        # Get all backup folders. Sorting by os.path.basename uses the timestamp in the name,
        # which guarantees chronological order regardless of filesystem mtime quirks.
        all_backups = sorted(
            glob.glob(os.path.join(backup_base_dir, "backup_*")), key=os.path.basename
        )
        if len(all_backups) > max_copies:
            # Calculate how many folders to remove (e.g., if 11, remove 1)
            to_remove = all_backups[: len(all_backups) - max_copies]
            print(
                f"[INFO] Backup limit ({max_copies}) exceeded. Removing {len(to_remove)} oldest backup(s)."
            )
            for old_backup in to_remove:
                print(f"[INFO] Removing old backup: {os.path.basename(old_backup)}")
                shutil.rmtree(old_backup)
    except Exception as e:
        print(f"[ERROR] Failed to manage backup retention: {e}", file=sys.stderr)


def backup_waypanel_data(source_dirs, backup_base_dir, max_copies=10):
    """
    Copies multiple source directories (data and config) to a single timestamped backup folder.
    Excludes 'venv' from the 'data' directory.
    source_dirs: A dictionary mapping descriptive names (e.g., 'data', 'config') to source paths.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_target_root = os.path.join(backup_base_dir, f"backup_{timestamp}")
    print(f"[INFO] Creating comprehensive backup in {backup_target_root}")
    success = True

    # Callable to ignore the 'venv' folder when copying the data directory
    ignore_venv = shutil.ignore_patterns("venv")

    try:
        os.makedirs(backup_target_root, exist_ok=True)
        os.makedirs(backup_base_dir, exist_ok=True)

        for name, source_path in source_dirs.items():
            if not os.path.isdir(source_path):
                print(
                    f"[WARN] Backup source '{name}' directory not found: {source_path}. Skipping this path."
                )
                continue

            target_path = os.path.join(backup_target_root, name)

            # Use the ignore function only for the 'data' directory
            ignore_arg = ignore_venv if name == "data" else None

            try:
                shutil.copytree(
                    source_path, target_path, symlinks=False, ignore=ignore_arg
                )

                status_msg = " (venv excluded)" if name == "data" else ""
                print(f"[INFO] Backed up {name} to {target_path}{status_msg}")
            except Exception as e:
                print(
                    f"[ERROR] Failed to backup '{name}' ({source_path}): {e}",
                    file=sys.stderr,
                )
                success = False

        if success:
            print("[INFO] Comprehensive backup complete.")
            _enforce_retention_policy(backup_base_dir, max_copies)
        else:
            print(
                "[ERROR] Backup completed with errors. Retention management skipped.",
                file=sys.stderr,
            )

    except Exception as e:
        print(f"[FATAL] Failed to create backup root directory: {e}", file=sys.stderr)


# =========================================================
# MAIN APPLICATION BOOTSTRAP
# =========================================================


def main():
    APP_NAME = "waypanel"

    XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    XDG_CACHE_HOME = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

    # Define application paths
    WAYPANEL_DATA_DIR = os.path.join(XDG_DATA_HOME, APP_NAME)
    CONFIG_DIR = os.path.join(XDG_CONFIG_HOME, APP_NAME)
    BACKUP_BASE_DIR = os.path.join(XDG_CACHE_HOME, APP_NAME, "backups")
    VENV_DIR = os.path.join(WAYPANEL_DATA_DIR, "venv")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")

    # 1. RUN BACKUP IN A THREAD
    SOURCE_DIRS_TO_BACKUP = {"data": WAYPANEL_DATA_DIR, "config": CONFIG_DIR}
    print("[INFO] Starting asynchronous data and config backup...")
    backup_thread = threading.Thread(
        target=backup_waypanel_data,
        args=(SOURCE_DIRS_TO_BACKUP, BACKUP_BASE_DIR, 10),  # max_copies set to 10
        daemon=True,
    )
    backup_thread.start()

    # 2. APPLICATION SETUP AND RUN (continues immediately)

    def find_package_files():
        """Finds the installed Waypanel package path or falls back to development path."""
        candidate_patterns = [
            os.path.join(XDG_DATA_HOME, "lib/python*/site-packages"),
            os.path.expanduser("~/.local/lib/python*/site-packages"),
            "/usr/lib/python*/dist-packages",
            "/usr/lib/python*/site-packages",
            "/usr/local/lib/python*/dist-packages",
            "/usr/local/lib/python*/site-packages",
        ]
        for pattern in candidate_patterns:
            for path in glob.glob(pattern):
                pkg_path = os.path.join(path, APP_NAME)
                if os.path.isdir(pkg_path):
                    return pkg_path
        return None

    INSTALLED_PATH = find_package_files()
    if INSTALLED_PATH:
        REQ_FILE = os.path.join(INSTALLED_PATH, "requirements.txt")
        MAIN_PY_DIR = INSTALLED_PATH  # Directory where the main script resides
        MAIN_PY = os.path.join(INSTALLED_PATH, "main.py", "-O")
        print(f"[INFO] Using installed package from: {INSTALLED_PATH}")
        os.environ["PYTHONPATH"] = INSTALLED_PATH
    else:
        REQ_FILE = os.path.join(SCRIPT_DIR, "requirements.txt")
        MAIN_PY_DIR = SCRIPT_DIR
        MAIN_PY = os.path.join(SCRIPT_DIR, "main.py")
        print(f"[INFO] Using development path: {SCRIPT_DIR}")
        os.environ["PYTHONPATH"] = SCRIPT_DIR

    # ===== GTK4 Layer Shell detection =====
    def find_gtk_layer_shell():
        """Locates the required libgtk4-layer-shell.so file."""
        LOCAL_LIB_PATH = os.path.join(
            XDG_DATA_HOME, "lib", "gtk4-layer-shell", "lib", "libgtk4-layer-shell.so"
        )

        candidates = [
            "/usr/lib/libgtk4-layer-shell.so",
            "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",
            "/usr/lib64/libgtk4-layer-shell.so",
            LOCAL_LIB_PATH,
        ]

        for lib in candidates:
            if os.path.isfile(lib):
                return lib

        if os.path.isdir("/nix/store"):
            try:
                nix_libs = glob.glob(
                    "/nix/store/**/libgtk4-layer-shell.so", recursive=True
                )
                if nix_libs:
                    return nix_libs[0]
            except Exception:
                pass

        return None

    GTK_LIB = find_gtk_layer_shell()
    if GTK_LIB is None:
        print("[ERROR] libgtk4-layer-shell.so not found.", file=sys.stderr)
        sys.exit(1)
    os.environ["LD_PRELOAD"] = GTK_LIB
    print(f"[INFO] Using GTK4 Layer Shell: {GTK_LIB}")

    # ===== CONFIGURATION =====
    if not os.path.isfile(CONFIG_FILE):
        print(
            f"[INFO] Config not found at {CONFIG_FILE}. Attempting to copy defaults..."
        )

        for src_dir, desc in [
            (f"/usr/lib/{APP_NAME}/config", "system"),
            (os.path.join(SCRIPT_DIR, APP_NAME, "config"), "dev path"),
            (os.path.join(SCRIPT_DIR, "config"), "alt dev path"),
        ]:
            if os.path.isdir(src_dir):
                os.makedirs(CONFIG_DIR, exist_ok=True)
                for item in os.listdir(src_dir):
                    src = os.path.join(src_dir, item)
                    dst = os.path.join(CONFIG_DIR, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                print(f"[INFO] Default config copied from {desc}: {src_dir}")
                break
        else:
            print("[ERROR] No default config found.", file=sys.stderr)
            sys.exit(1)

    # ===== VIRTUAL ENVIRONMENT SETUP =====
    if not os.path.isdir(VENV_DIR):
        print("[INFO] Creating virtual environment...")
        os.makedirs(VENV_DIR, exist_ok=True)
        subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", VENV_DIR],
            check=True,
        )

    VENV_BIN = os.path.join(VENV_DIR, "bin")
    os.environ["PATH"] = f"{VENV_BIN}:{os.environ['PATH']}"

    # Install dependencies if needed
    REQUIREMENTS_INSTALLED_FLAG = os.path.join(VENV_DIR, ".requirements_installed")
    if not os.path.isfile(REQUIREMENTS_INSTALLED_FLAG):
        print("[INFO] Installing dependencies...")
        try:
            subprocess.run(
                [
                    os.path.join(VENV_BIN, "pip"),
                    "install",
                    "--no-cache-dir",
                    "-r",
                    REQ_FILE,
                ],
                check=True,
            )
            with open(REQUIREMENTS_INSTALLED_FLAG, "w") as f:
                f.write("Dependencies installed.")
        except subprocess.CalledProcessError:
            print("[ERROR] Failed to install dependencies.", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print(
                f"[ERROR] 'pip' not found in virtual environment at {os.path.join(VENV_BIN, 'pip')}.",
                file=sys.stderr,
            )
            sys.exit(1)

    # ===== COMPILE PYTHON FILES =====
    print("[INFO] Compiling Python source files to bytecode (.pyc) if necessary...")

    try:
        # Compile the application's source directory recursively
        # quiet=1 suppresses output unless an error occurs.
        compileall.compile_dir(MAIN_PY_DIR, quiet=1)

        # Compile the main script itself
        compileall.compile_file(MAIN_PY, quiet=1)
        print("[INFO] Compilation complete (skipped if already up-to-date).")

    except Exception as e:
        # This catches general compilation errors but ignores the common SyntaxWarnings from libs.
        print(
            f"[WARN] Non-critical error during Python file compilation: {e}",
            file=sys.stderr,
        )

    # ===== RUN THE APP =====
    print("[INFO] Starting application...")
    # Using python -B ensures the interpreter ignores the compilation step at runtime,
    # relying solely on the .pyc files we just generated (or falls back to .py if none).
    cmd = [os.path.join(VENV_BIN, "python"), MAIN_PY]
    # Optionally, you could add -W ignore::SyntaxWarning here to suppress the pulsectl warning:
    # cmd = [os.path.join(VENV_BIN, "python"), "-W", "ignore::SyntaxWarning", MAIN_PY]

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    try:
        # Attempt to kill any previous running instance of the app
        subprocess.run(
            "pkill -f waypanel/main.py".split(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        # Don't fail if pkill isn't found or an instance isn't running
        print(f"[WARN] Failed to run pkill (may be missing or harmless): {e}")
    main()
