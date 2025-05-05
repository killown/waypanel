#!/bin/bash
set -e

pkill -f waypanel/main.py || true

APP_NAME="waypanel"
VENV_DIR="$HOME/.local/share/$APP_NAME/venv"

# Try local first, fallback to system install
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
MAIN_PY="$SCRIPT_DIR/waypanel/main.py"

# Fallback paths
SYSTEM_PATH="/usr/lib/$APP_NAME"
if [ ! -f "$REQ_FILE" ]; then
  REQ_FILE="$SYSTEM_PATH/requirements.txt"
fi

if [ ! -f "$MAIN_PY" ]; then
  MAIN_PY="$SYSTEM_PATH/main.py"
fi

export PYTHONPATH="$SCRIPT_DIR:$SYSTEM_PATH"

# Ensure Python exists
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found. Please install Python." >&2
  exit 1
fi

# === CONFIG SETUP ===
CONFIG_DIR="$HOME/.config/$APP_NAME"
CONFIG_FILE="$CONFIG_DIR/waypanel.toml"
SYSTEM_CONFIG="/usr/lib/$APP_NAME/config"      # System install path
LOCAL_DEV_CONFIG="$SCRIPT_DIR/waypanel/config" # Git clone dev path
ALT_DEV_CONFIG="$SCRIPT_DIR/config"            # Alternate dev path (flat structure)

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[INFO] Config not found at $CONFIG_FILE. Attempting to copy defaults..."

  # Try system install first
  if [ -d "$SYSTEM_CONFIG" ]; then
    mkdir -p "$CONFIG_DIR"
    cp -r "$SYSTEM_CONFIG"/* "$CONFIG_DIR/"
    echo "[INFO] Default config copied from system: $SYSTEM_CONFIG"

  # Then try local dev path (waypanel/config)
  elif [ -d "$LOCAL_DEV_CONFIG" ]; then
    mkdir -p "$CONFIG_DIR"
    cp -r "$LOCAL_DEV_CONFIG"/* "$CONFIG_DIR/"
    echo "[INFO] Default config copied from dev path: $LOCAL_DEV_CONFIG"

  # Fallback: alternate dev layout (config/)
  elif [ -d "$ALT_DEV_CONFIG" ]; then
    mkdir -p "$CONFIG_DIR"
    cp -r "$ALT_DEV_CONFIG"/* "$CONFIG_DIR/"
    echo "[INFO] Default config copied from alt dev path: $ALT_DEV_CONFIG"

  else
    echo "[ERROR] No default config found in any known location." >&2
    echo "Tried:" >&2
    echo " - $SYSTEM_CONFIG" >&2
    echo " - $LOCAL_DEV_CONFIG" >&2
    echo " - $ALT_DEV_CONFIG" >&2
    echo "Please ensure waypanel is installed properly or run from a valid git clone." >&2
    exit 1
  fi
fi

# Create virtual environment if not exists
if [ ! -d "$VENV_DIR" ]; then
  echo "[INFO] Creating virtual environment..."
  mkdir -p "$VENV_DIR"
  python3 -m venv --system-site-packages "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install dependencies if needed
if [ ! -f "$VENV_DIR/.requirements_installed" ]; then
  echo "[INFO] Installing dependencies..."
  pip install --no-cache-dir -r "$REQ_FILE"
  touch "$VENV_DIR/.requirements_installed"
fi

# Run the app — use fallback main.py if needed
exec python "$MAIN_PY" "$@"
