#!/usr/bin/env bash
set -e

# Kill existing instance
pkill -f waypanel/main.py || true

APP_NAME="waypanel"
VENV_DIR="$HOME/.local/share/$APP_NAME/venv"
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
MAIN_PY="$SCRIPT_DIR/waypanel/main.py"

# ===== Smart system path detection =====
find_system_path() {
    local app_name="$1"
    
    # First, check if we're running from a Nix result directory or development environment
    if [ -f "$SCRIPT_DIR/requirements.txt" ] || [ -f "$SCRIPT_DIR/waypanel/main.py" ]; then
        echo "$SCRIPT_DIR"
        return 0
    fi
    
    # Traditional Linux paths
    local paths=(
        "/usr/lib/$app_name"
        "/usr/lib64/$app_name"
        "/usr/local/lib/$app_name"
        "/opt/$app_name"
    )
    
    # Nix store paths (both direct and result symlinks)
    if [ -d /nix/store ]; then
        # Check if we're in a nix-shell or nix-developed environment
        if [ -n "$IN_NIX_SHELL" ]; then
            echo "$SCRIPT_DIR"
            return 0
        fi
        
        # Look for the actual package in nix store
        nix_path=$(find /nix/store -maxdepth 2 -path "*/$app_name" -type d 2>/dev/null | head -n1)
        if [ -n "$nix_path" ]; then
            echo "$nix_path"
            return 0
        fi
        
        # Look for result symlinks that might point to the actual package
        result_paths=$(find . -maxdepth 1 -name "result" -type l 2>/dev/null)
        for result in $result_paths; do
            if resolved=$(readlink -f "$result" 2>/dev/null) && [ -d "$resolved" ]; then
                if [ -d "$resolved/lib/$app_name" ]; then
                    echo "$resolved/lib/$app_name"
                    return 0
                elif [ -d "$resolved" ]; then
                    echo "$resolved"
                    return 0
                fi
            fi
        done
    fi
    
    # Fallback for traditional installations
    for path in "${paths[@]}"; do
        if [ -d "$path" ]; then
            echo "$path"
            return 0
        fi
    done
    
    # Final fallback
    echo "/usr/lib/$app_name"
    return 1
}

SYSTEM_PATH=$(find_system_path "$APP_NAME")

# Debug info
echo "[DEBUG] Using system path: $SYSTEM_PATH"
echo "[DEBUG] Script dir: $SCRIPT_DIR"
echo "[DEBUG] Requirements file: $REQ_FILE"
echo "[DEBUG] Main py: $MAIN_PY"

# Fallback paths for dev/system installs
if [ ! -f "$REQ_FILE" ] && [ -f "$SYSTEM_PATH/requirements.txt" ]; then
    REQ_FILE="$SYSTEM_PATH/requirements.txt"
    echo "[INFO] Using requirements from: $REQ_FILE"
fi

if [ ! -f "$MAIN_PY" ] && [ -f "$SYSTEM_PATH/main.py" ]; then
    MAIN_PY="$SYSTEM_PATH/main.py"
    echo "[INFO] Using main.py from: $MAIN_PY"
fi

# Final check - if neither local nor system files exist, error out
if [ ! -f "$REQ_FILE" ]; then
    echo "[ERROR] Requirements file not found at $REQ_FILE or $SYSTEM_PATH/requirements.txt"
    exit 1
fi

if [ ! -f "$MAIN_PY" ]; then
    echo "[ERROR] Main script not found at $MAIN_PY or $SYSTEM_PATH/main.py"
    exit 1
fi

export PYTHONPATH="$SCRIPT_DIR:$SYSTEM_PATH"

# ===== GTK4 Layer Shell library detection =====
GTK_LIB=""

find_gtk_layer_shell() {
    # Common system paths
    local candidate_libs=(
        "/usr/lib/libgtk4-layer-shell.so"
        "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so"
        "/usr/lib64/libgtk4-layer-shell.so"
        "$HOME/.local/lib/libgtk4-layer-shell.so"
    )
    
    # Nix store paths
    if [ -d /nix/store ]; then
        # First try to use nix-provided library if available
        if [ -n "$LD_LIBRARY_PATH" ]; then
            IFS=':' read -ra LIB_PATHS <<< "$LD_LIBRARY_PATH"
            for lib_path in "${LIB_PATHS[@]}"; do
                if [ -f "$lib_path/libgtk4-layer-shell.so" ]; then
                    echo "$lib_path/libgtk4-layer-shell.so"
                    return 0
                fi
            done
        fi
        
        # Fallback to searching nix store
        nix_lib=$(find /nix/store -name "libgtk4-layer-shell.so" 2>/dev/null | head -n1)
        if [ -n "$nix_lib" ]; then
            echo "$nix_lib"
            return 0
        fi
    fi
    
    # Check traditional paths
    for lib in "${candidate_libs[@]}"; do
        if [ -f "$lib" ]; then
            echo "$lib"
            return 0
        fi
    done
    
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

if [ ! -f "$CONFIG_FILE" ]; then
    echo "[INFO] Config not found at $CONFIG_FILE. Attempting to copy defaults..."
    
    # Try to find config in the detected system path first
    if [ -d "$SYSTEM_PATH/config" ]; then
        mkdir -p "$CONFIG_DIR"
        cp -r "$SYSTEM_PATH/config"/* "$CONFIG_DIR/"
        echo "[INFO] Default config copied from: $SYSTEM_PATH/config"
    else
        # Fallback to traditional paths
        local config_paths=(
            "/usr/lib/$APP_NAME/config"
            "/usr/share/$APP_NAME/config"
            "$SCRIPT_DIR/waypanel/config"
            "$SCRIPT_DIR/config"
        )
        
        for config_path in "${config_paths[@]}"; do
            if [ -d "$config_path" ]; then
                mkdir -p "$CONFIG_DIR"
                cp -r "$config_path"/* "$CONFIG_DIR/"
                echo "[INFO] Default config copied from: $config_path"
                break
            fi
        done
        
        if [ ! -f "$CONFIG_FILE" ]; then
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
if [ ! -f "$VENV_DIR/.requirements_installed" ] || [ "$REQ_FILE" -nt "$VENV_DIR/.requirements_installed" ]; then
    echo "[INFO] Installing dependencies from: $REQ_FILE"
    
    # For NixOS, use the environment's pip if in nix-shell
    if [ -n "$IN_NIX_SHELL" ]; then
        echo "[INFO] Using nix-shell environment for dependencies"
        pip install --no-cache-dir -r "$REQ_FILE"
    else
        pip install --no-cache-dir -r "$REQ_FILE"
    fi
    
    touch "$VENV_DIR/.requirements_installed"
fi

# ===== Run the app =====
# For Nix environments, use the environment's settings
if [ -d /nix/store ]; then
    # Use existing environment variables if in nix-shell
    if [ -z "$IN_NIX_SHELL" ]; then
        # Try to set common Nix environment variables if not already set
        if [ -z "$GI_TYPELIB_PATH" ]; then
            possible_typelib_paths=$(find /nix/store -name "*-typelib" -type d 2>/dev/null | head -n1)
            if [ -n "$possible_typelib_paths" ]; then
                export GI_TYPELIB_PATH="$possible_typelib_paths"
            fi
        fi
        
        if [ -z "$GDK_PIXBUF_MODULE_FILE" ]; then
            gdk_pixbuf_file=$(find /nix/store -name "loaders.cache" 2>/dev/null | head -n1)
            if [ -n "$gdk_pixbuf_file" ]; then
                export GDK_PIXBUF_MODULE_FILE="$gdk_pixbuf_file"
            fi
        fi
    fi
fi

echo "[INFO] Starting waypanel..."
exec python "$MAIN_PY" "$@"