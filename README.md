## waypanel

<img width="1920" height="1080" alt="waypanel" src="https://github.com/user-attachments/assets/37513dee-b43a-4040-ad02-e5e007a7f3b8" />

##### _GTK4 panel for wayfire_

Waypanel is a lightweight, modular, and highly customizable status panel designed for the Sway and Wayfire. Built with Python and leveraging GTK 4/Adwaita , it mimics a shell-like interface while prioritizing efficiency and extensibility. Supports multiple panels (top, bottom, left, right) with customizable styling. Plugins can append widgets (e.g., system monitors, app launchers) or manage gestures for interactive workflows.

# How to Install `waypanel`

**_Latest Wayfire and Pywayfire is required_**

##### if using wayfire: configure wayfire.ini

Ensure the following plugins are enabled in your ~/.config/wayfire.ini:

    [core]

    plugins = ipc ipc-rules stipc scale

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

#### Remove any existing configuration from ~/.config/waypanel and ~/.local/share/waypanel for a fresh install.

    git clone https://github.com/killown/waypanel.git
    cd waypanel
    python run.py # This will set up the venv automatically and run the panel

## Recommended icon themes

- https://github.com/PapirusDevelopmentTeam/papirus-icon-theme
- https://github.com/SylEleuth/gruvbox-plus-icon-pack
- https://github.com/vinceliuice/Tela-icon-theme
- https://github.com/bikass/kora

## Basic usage

- Toggle scale to show all panels. The default activator can be found in /usr/share/wayfire/metadata/scale.xml

https://github.com/user-attachments/assets/8d1d3472-e9b1-4c03-a935-cf9f66c8748c

- To add icons to the dockbar, go to the first icon in the top-left (the app launcher), right-click the desired app icon, and select “Add to dockbar.”

https://github.com/user-attachments/assets/459a0581-047f-447c-8f50-8ce32adcb723

- To adjust panel settings, open the app-launcher and click in settings or edit ~/.config/waypanel/config directly.

https://github.com/user-attachments/assets/0902666a-2aa8-44aa-8969-fd6283a8de3d



## License

waypanel is licensed under the **AGPLv3 (GNU Affero General Public License version 3)**. [See LICENSE for more information](https://github.com/killown/waypanel/blob/main/LICENSE).
