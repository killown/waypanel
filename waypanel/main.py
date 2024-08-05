import os
import shutil
import subprocess

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


layer_shell_check()

from waypanel.src.panel import *



