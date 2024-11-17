import os
import pkg_resources
import shutil
import subprocess
from ctypes import CDLL
import gi

subprocess.call(['pkill', '-f', 'waypanel/src/ipc_server/ipc-async-server.py'])

current_dir = os.path.dirname(os.path.abspath(__file__))
script_path = pkg_resources.resource_filename('waypanel', 'src/ipc_server/ipc-async-server.py')
subprocess.Popen(['python', script_path], start_new_session=True)

def layer_shell_check():
    """Check if gtk4-layer-shell is installed, and install it if not."""
    # Define paths
    install_path = os.path.expanduser('~/.local/lib/gtk4-layer-shell')
    temp_dir = '/tmp/gtk4-layer-shell'
    repo_url = 'https://github.com/wmww/gtk4-layer-shell.git'
    build_dir = 'build'
    
    # Check if the library is installed
    if os.path.exists(install_path):
        print("gtk4-layer-shell is already installed.")
        return
    
    # Proceed with installation if not installed
    print("gtk4-layer-shell is not installed. Installing...")
    
    # Remove the temporary directory if it exists
    if os.path.exists(temp_dir):
        print("Removing existing temporary directory...")
        shutil.rmtree(temp_dir)
    
    # Clone the repository
    print("Cloning the repository...")
    subprocess.run(['git', 'clone', repo_url, temp_dir], check=True)
    
    # Change to the repository directory
    os.chdir(temp_dir)
    
    # Set up the build directory with Meson
    print("Configuring the build environment...")
    subprocess.run(['meson', 'setup', f'--prefix={os.path.expanduser(install_path)}', '-Dexamples=true', '-Ddocs=true', '-Dtests=true', build_dir], check=True)
    
    # Build the project
    print("Building the project...")
    subprocess.run(['ninja', '-C', build_dir], check=True)
    
    # Install the project
    print("Installing the project...")
    subprocess.run(['ninja', '-C', build_dir, 'install'], check=True)
    
    print("Installation complete.")


def create_first_config():
    dest_dir = os.path.expanduser('~/.config/waypanel')
    
    # Ensure the destination directory exists
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    temp_dir = '/tmp/waypanel'
    repo_url = 'https://github.com/killown/waypanel.git'
    config_dir = 'waypanel/config'  # Updated config directory path

    try:
        # Clone the repository
        print("Cloning the repository...")
        subprocess.run(['git', 'clone', repo_url, temp_dir], check=True)

        # Path to the config directory in the cloned repo
        src_config_dir = os.path.join(temp_dir, config_dir)
        
        # Ensure the config directory exists; create it if not
        if not os.path.exists(src_config_dir):
            print(f"Config directory {src_config_dir} does not exist. Creating it...")
            os.makedirs(src_config_dir)

        # Copy the config directory to the destination
        print(f"Copying config files from {src_config_dir} to {dest_dir}...")
        shutil.copytree(src_config_dir, dest_dir, dirs_exist_ok=True)
        
    finally:
        # Clean up the temporary directory
        if os.path.exists(temp_dir):
            print(f"Cleaning up temporary directory {temp_dir}...")
            shutil.rmtree(temp_dir)

    print("Configuration setup is complete.")
 
def check_config_path():
    config_path =  os.path.expanduser('~/.config/waypanel')
    
    if os.path.exists(config_path) and not os.listdir(config_path):
        print(f"{config_path} is empty. Removing it...")
        os.rmdir(config_path)
 
    if not os.path.exists(config_path):
        create_first_config()


def find_typelib_path(base_path):
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.typelib'):
                return root
    return None

def set_gi_typelib_path(primary_path, fallback_path):
    primary_typelib_path = find_typelib_path(primary_path)
    if primary_typelib_path:
        os.environ["GI_TYPELIB_PATH"] = primary_typelib_path
        print(f"GI_TYPELIB_PATH set to: {primary_typelib_path}")
    else:
        fallback_typelib_path = find_typelib_path(fallback_path)
        if fallback_typelib_path:
            os.environ["GI_TYPELIB_PATH"] = fallback_typelib_path
            print(f"GI_TYPELIB_PATH set to fallback path: {fallback_typelib_path}")
        else:
            print(f"Error: Neither the primary path '{primary_path}' nor the fallback path '{fallback_path}' contain any '.typelib' files. Please install the required library.")

layer_shell_check()
check_config_path()

# custom env because most distros don't have "gtk4" layer shell package, plain and simple :)
primary_path = os.path.expanduser('~/.local/lib/gtk4-layer-shell/lib/girepository-1.0')
fallback_path = os.path.expanduser('~/.local/lib/gtk4-layer-shell/lib64/girepository-1.0')

set_gi_typelib_path(primary_path, fallback_path)

gi.require_version('Gio', '2.0')
CDLL("libgtk4-layer-shell.so")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Playerctl', '2.0')
gi.require_version('Adw', '1')
from waypanel.src.panel import start_panel 
start_panel()



