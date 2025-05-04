#!/bin/bash
set -e

APP_NAME="waypanel"
VENV_DIR="$HOME/.local/share/$APP_NAME/venv"
REQUIREMENTS="$(dirname "$(readlink -f "$0")")/requirements.txt"

# Required for gi/Gtk in virtual environments
export GI_TYPELIB_PATH=/usr/lib/girepository-1.0
export GDK_PIXBUF_MODULE_FILE="$HOME/.cache/gdk-pixbuf-loaders.cache"
export PYTHONPATH="$(dirname "$(readlink -f "$0")")"

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
  pip install --no-cache-dir -r "$REQUIREMENTS"
  touch "$VENV_DIR/.requirements_installed"
fi

# Run the app
echo "[DEBUG] Using Python: $(which python)"
echo "[DEBUG] PYTHONPATH: $PYTHONPATH"
cd waypanel
exec python "$(dirname "$(readlink -f "$0")")/main.py" "$@"
