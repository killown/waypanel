#!/bin/bash
set -e

# Kill existing instance
pkill -f waypanel/main.py || true

APP_NAME="waypanel"
VENV_DIR="$HOME/.local/share/$APP_NAME/venv"
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
MAIN_PY="$SCRIPT_DIR/waypanel/main.py"
SYSTEM_PATH="/usr/lib/$APP_NAME"

# Fallback paths for dev/system installs
if [ ! -f "$REQ_FILE" ]; then
  REQ_FILE="$SYSTEM_PATH/requirements.txt"
fi
if [ ! -f "$MAIN_PY" ]; then
  MAIN_PY="$SYSTEM_PATH/main.py"
fi

export PYTHONPATH="$SCRIPT_DIR:$SYSTEM_PATH"

# ===== GTK4 Layer Shell library detection =====
GTK_LIB=""

# Common system + local paths
CANDIDATE_LIBS=(
  "/usr/lib/libgtk4-layer-shell.so"
  "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so"
  "/usr/lib64/libgtk4-layer-shell.so"
  "$HOME/.local/lib/gtk4-layer-shell/lib/libgtk4-layer-shell.so"
)

# Check candidate paths
for lib in "${CANDIDATE_LIBS[@]}"; do
  if [ -f "$lib" ]; then
    GTK_LIB="$lib"
    break
  fi
done

# NixOS support: search Nix store
if [ -z "$GTK_LIB" ] && [ -d /nix/store ]; then
  GTK_LIB=$(find /nix/store -name libgtk4-layer-shell.so | head -n1)
fi

if [ -z "$GTK_LIB" ]; then
  echo "[ERROR] libgtk4-layer-shell.so not found."
  echo "Install it system-wide, locally, or via nix-shell."
  exit 1
fi

export LD_PRELOAD="$GTK_LIB"
echo "[INFO] Using GTK4 Layer Shell: $GTK_LIB"

# ===== Config setup =====
CONFIG_DIR="$HOME/.config/$APP_NAME"
CONFIG_FILE="$CONFIG_DIR/config.toml"
SYSTEM_CONFIG="/usr/lib/$APP_NAME/config"
LOCAL_DEV_CONFIG="$SCRIPT_DIR/waypanel/config"
ALT_DEV_CONFIG="$SCRIPT_DIR/config"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[INFO] Config not found at $CONFIG_FILE. Attempting to copy defaults..."
  if [ -d "$SYSTEM_CONFIG" ]; then
    mkdir -p "$CONFIG_DIR"
    cp -r "$SYSTEM_CONFIG"/* "$CONFIG_DIR/"
    echo "[INFO] Default config copied from system: $SYSTEM_CONFIG"
  elif [ -d "$LOCAL_DEV_CONFIG" ]; then
    mkdir -p "$CONFIG_DIR"
    cp -r "$LOCAL_DEV_CONFIG"/* "$CONFIG_DIR/"
    echo "[INFO] Default config copied from dev path: $LOCAL_DEV_CONFIG"
  elif [ -d "$ALT_DEV_CONFIG" ]; then
    mkdir -p "$CONFIG_DIR"
    cp -r "$ALT_DEV_CONFIG"/* "$CONFIG_DIR/"
    echo "[INFO] Default config copied from alt dev path: $ALT_DEV_CONFIG"
  else
    echo "[ERROR] No default config found." >&2
    exit 1
  fi
fi

# ===== Virtual environment setup =====
if [ ! -d "$VENV_DIR" ]; then
  echo "[INFO] Creating virtual environment..."
  mkdir -p "$VENV_DIR"
  python3 -m venv --system-site-packages "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/.requirements_installed" ]; then
  echo "[INFO] Installing dependencies..."
  pip install --no-cache-dir -r "$REQ_FILE"
  touch "$VENV_DIR/.requirements_installed"
fi

# ===== Run the app =====
exec python "$MAIN_PY" "$@" >/tmp/waypanel.log 2>&1
