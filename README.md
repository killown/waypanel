## waypanel


<img width="1920" height="1080" alt="output-DP-1" src="https://github.com/user-attachments/assets/c6b9fb3b-480f-4dd9-b13a-455d130bb155" />

<img width="1920" height="1080" alt="1" src="https://github.com/user-attachments/assets/46e81625-7d22-404f-8dec-361f98a2294a" />

<img width="1920" height="1080" alt="output-DP-1" src="https://github.com/user-attachments/assets/d01f5a80-aada-4f51-b004-1154c3665714" />


##### _GTK4 panel for sway and wayfire_

Waypanel is a lightweight, modular, and highly customizable status panel designed for the Sway and Wayfire. Built with Python and leveraging GTK 4/Adwaita , it mimics a shell-like interface while prioritizing efficiency and extensibility. Supports multiple panels (top, bottom, left, right) with customizable styling. Plugins can append widgets (e.g., system monitors, app launchers) or manage gestures for interactive workflows.

# How to Install `waypanel`

**_Latest Wayfire and Pywayfire is required_**

##### if using wayfire: configure wayfire.ini

Ensure the following plugins are enabled in your ~/.config/wayfire.ini:

[core]

plugins = ipc ipc-rules stipc

##### Option 1: aur (archlinux)

yay -S waypanel-git

##### Archlinux deps:
sudo pacman -S gtk4-layer-shell gobject-introspection vala playerctl python-gobject wayland-protocols ninja mesa playerctl libadwaita bluez-tools uv

##### Fedora Deps:
sudo dnf install gtk4 gtk4-layer-shell-devel.x86_64 gobject-introspection vala playerctl python3-gobject ninja libadwaita bluez-tools python3-uv.noarch python-devel

## Installing `waypanel` from github Source

### Clone the repository and run waypanel.sh

    git clone https://github.com/killown/waypanel.git
    cd waypanel
    python run.py # This will set up the venv automatically and run the panel

## License

waypanel is licensed under the MIT license. [See LICENSE for more information](https://github.com/killown/waypanel/blob/main/LICENSE).
