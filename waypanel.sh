#!/usr/bin/env bash
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

# Function to find GTK4 Layer Shell library
find_gtk_layer_shell() {
  # Common system + local paths
  local candidate_libs=(
    "/usr/lib/libgtk4-layer-shell.so"
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so"
    "/usr/lib64/libgtk4-layer-shell.so"
    "$HOME/.local/lib/gtk4-layer-shell/lib/libgtk4-layer-shell.so"
  )

  # Check candidate paths
  for lib in "${candidate_libs[@]}"; do
    if [ -f "$lib" ]; then
      echo "$lib"
      return 0
    fi
  done

  # NixOS support: search Nix store
  if [ -d /nix/store ]; then
    local nix_lib=$(find /nix/store -name "libgtk4-layer-shell.so" 2>/dev/null | head -n1)
    if [ -n "$nix_lib" ]; then
      echo "$nix_lib"
      return 0
    fi
  fi

  return 1
}

GTK_LIB=$(find_gtk_layer_shell) || true

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

  # Try different config sources in order of preference
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
    # For NixOS, try to find config in nix store
    if [ -d /nix/store ]; then
      nix_config=$(find /nix/store -path "*/$APP_NAME/config" 2>/dev/null | head -n1)
      if [ -n "$nix_config" ] && [ -d "$nix_config" ]; then
        mkdir -p "$CONFIG_DIR"
        cp -r "$nix_config"/* "$CONFIG_DIR/"
        echo "[INFO] Default config copied from Nix store: $nix_config"
      else
        echo "[ERROR] No default config found." >&2
        exit 1
      fi
    else
      echo "[ERROR] No default config found." >&2
      exit 1
    fi
  fi
fi

# ===== Virtual environment setup =====
if [ ! -d "$VENV_DIR" ]; then
  echo "[INFO] Creating virtual environment..."
  mkdir -p "$VENV_DIR"
  python3 -m venv --system-site-packages "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Check if we need to install dependencies
if [ ! -d /nix/store ] && { [ ! -f "$VENV_DIR/.requirements_installed" ] || [ "$REQ_FILE" -nt "$VENV_DIR/.requirements_installed" ]; }; then
  echo "[INFO] Installing dependencies..."
  pip install --no-cache-dir -r "$REQ_FILE"
  touch "$VENV_DIR/.requirements_installed"
fi

# ===== Run the app =====
# For NixOS, we might need additional environment variables
if [ -d /nix/store ]; then
  # Set GI_TYPELIB_PATH for GObject introspection if not already set
  if [ -z "$GI_TYPELIB_PATH" ]; then
    # Try to find common typelib paths in nix store
    possible_typelib_paths=$(find /nix/store -name "*-typelib" -type d 2>/dev/null | tr '\n' ':')
    if [ -n "$possible_typelib_paths" ]; then
      export GI_TYPELIB_PATH="$possible_typelib_paths$GI_TYPELIB_PATH"
    fi
  fi

  # Set GDK_PIXBUF_MODULE_FILE if not already set
  if [ -z "$GDK_PIXBUF_MODULE_FILE" ]; then
    gdk_pixbuf_file=$(find /nix/store -name "loaders.cache" 2>/dev/null | head -n1)
    if [ -n "$gdk_pixbuf_file" ]; then
      export GDK_PIXBUF_MODULE_FILE="$gdk_pixbuf_file"
    fi
  fi
fi

exec python -m waypanel.main "$@"

