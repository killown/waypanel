#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import glob


def main():
    APP_NAME = "waypanel"
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    VENV_DIR = os.path.expanduser(f"~/.local/share/{APP_NAME}/venv")
    CONFIG_DIR = os.path.expanduser(f"~/.config/{APP_NAME}")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")
    SYSTEM_CONFIG = f"/usr/lib/{APP_NAME}/config"
    LOCAL_DEV_CONFIG = os.path.join(SCRIPT_DIR, "waypanel", "config")
    ALT_DEV_CONFIG = os.path.join(SCRIPT_DIR, "config")

    # Add a function to find the system package path
    def find_package_files():
        candidate_patterns = [
            os.path.expanduser("~/.local/lib/python*/site-packages"),
            "/usr/lib/python*/dist-packages",
            "/usr/lib/python*/site-packages",
            "/usr/local/lib/python*/dist-packages",
            "/usr/local/lib/python*/site-packages",
        ]
        for pattern in candidate_patterns:
            for path in glob.glob(pattern):
                # Look for the 'waypanel' directory, which should contain the source files
                pkg_path = os.path.join(path, APP_NAME)
                if os.path.isdir(pkg_path):
                    return pkg_path
        return None

    # Find the installed package path
    INSTALLED_PATH = find_package_files()
    if INSTALLED_PATH:
        # Use the installed package paths if found
        REQ_FILE = os.path.join(INSTALLED_PATH, "requirements.txt")
        MAIN_PY = os.path.join(INSTALLED_PATH, "main.py")
        print(f"[INFO] Using installed package from: {INSTALLED_PATH}")
        os.environ["PYTHONPATH"] = INSTALLED_PATH
    else:
        # Fallback to the original development paths
        REQ_FILE = os.path.join(SCRIPT_DIR, "requirements.txt")
        MAIN_PY = os.path.join(SCRIPT_DIR, "main.py")
        print(f"[INFO] Using development path: {SCRIPT_DIR}")
        os.environ["PYTHONPATH"] = SCRIPT_DIR

    # ===== GTK4 Layer Shell detection =====
    def find_gtk_layer_shell():
        candidates = [
            "/usr/lib/libgtk4-layer-shell.so",
            "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",
            "/usr/lib64/libgtk4-layer-shell.so",
            os.path.expanduser(
                "~/.local/lib/gtk4-layer-shell/lib/libgtk4-layer-shell.so"
            ),
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
            (SYSTEM_CONFIG, "system"),
            (LOCAL_DEV_CONFIG, "dev path"),
            (ALT_DEV_CONFIG, "alt dev path"),
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

    # ===== RUN THE APP =====
    print("[INFO] Starting application...")
    cmd = [os.path.join(VENV_BIN, "python"), MAIN_PY]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    try:
        subprocess.run("pkill -f waypanel/main.py".split())
    except Exception as e:
        print(e)
    main()
