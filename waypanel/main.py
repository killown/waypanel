import os
import shutil
import subprocess

from gi import check_version

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


layer_shell_check()
check_config_path()

from waypanel.src.panel import *



