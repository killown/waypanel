## waypanel

<img width="1920" height="1080" alt="output-DP-1" src="https://github.com/user-attachments/assets/c6b9fb3b-480f-4dd9-b13a-455d130bb155" />

<img width="1920" height="1080" alt="output-DP-1" src="https://github.com/user-attachments/assets/d01f5a80-aada-4f51-b004-1154c3665714" />


##### _GTK4 panel for sway and wayfire_

Waypanel is a lightweight, modular, and highly customizable status panel designed for the Sway and Wayfire. Built with Python and leveraging GTK 4/Adwaita , it mimics a shell-like interface while prioritizing efficiency and extensibility. Supports multiple panels (top, bottom, left, right) with customizable styling. Plugins can append widgets (e.g., system monitors, app launchers) or manage gestures for interactive workflows.

# How to Install `waypanel`

**_Latest Wayfire and Pywayfire is required_**

##### if using wayfire: configure wayfire.ini

Ensure the following plugins are enabled in your ~/.config/wayfire.ini:

[core]

plugins = ipc ipc-rules stipc

##### install pywayfire
    git clone https://github.com/WayfireWM/pywayfire
    cd pywayfire
    sh install

##### Archlinux deps:
    sudo pacman -S gtk4-layer-shell gobject-introspection vala playerctl python-gobject wayland-protocols ninja mesa playerctl libadwaita bluez-tools wl-clipboard

##### Fedora Deps:
    sudo dnf install gtk4 gtk4-layer-shell-devel.x86_64 gobject-introspection vala playerctl python3-gobject ninja libadwaita bluez-tools python3-uv.noarch python-devel wl-clipboard

##### Ubuntu Deps:
    sudo apt install libgtk-4-dev libgtk4-layer-shell-dev gobject-introspection valac playerctl python3-gi ninja-build libadwaita-1-dev bluez-tools python3-dev python3.13-venv wl-clipboard

## install `waypanel`
    git clone https://github.com/killown/waypanel.git
    cd waypanel
    python run.py # This will set up the venv automatically and run the panel


## License

waypanel is licensed under the MIT license. [See LICENSE for more information](https://github.com/killown/waypanel/blob/main/LICENSE).
