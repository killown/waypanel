## waypanel

![test](https://github.com/user-attachments/assets/a4179a9a-4916-4939-af2b-3dd8e63e383d)
![test1](https://github.com/user-attachments/assets/a57d691f-989c-4ff2-a858-107f8d646920)


##### _Wayfire GTK4 panel_

Waypanel  is a lightweight, modular, and highly customizable status panel designed for the Wayfire  compositor. Built with Python and leveraging GTK 4/Adwaita , it mimics a shell-like interface while prioritizing efficiency and extensibility. Supports multiple panels (top, bottom, left, right) with customizable styling. Plugins can append widgets (e.g., system monitors, app launchers) or manage gestures for interactive workflows. 

How to Install `waypanel`
=========================

##### configure wayfire.ini
Ensure the following plugins are enabled in your ~/.config/wayfire.ini: 
    
[core]

plugins = ipc ipc-rules

##### Option 1: aur (archlinux)
yay -S waypanel-git 

##### Option 2: manual install (archlinux): 
pacman -S gtk4-layer-shell gobject-introspection vala playerctl python-gobject wayland-protocols ninja mesa playerctl libadwaita bluez-tools

Installing `waypanel` from github Source
-------------------------------------------------

### Clone the repository and run waypanel.sh
    git clone https://github.com/killown/waypanel.git
    cd waypanel
    sh waypanel.sh # This will set up the venv automatically and run the panel


### Theme Compatibility

yay -S gruvbox-plus-icon-theme-git

gsettings set org.gnome.desktop.interface icon-theme 'Gruvbox-Plus-Dark'



## License
waypanel is licensed under the MIT license. [See LICENSE for more information](https://github.com/killown/waypanel/blob/main/LICENSE).


