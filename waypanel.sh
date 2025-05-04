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
