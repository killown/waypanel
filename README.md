## waypanel
<img width="1920" height="1080" alt="waypanel" src="https://github.com/user-attachments/assets/4ec4a102-108b-48c3-8f6a-79f5f12947cc" />


https://github.com/user-attachments/assets/af20b2fe-d821-48a8-957f-58733982a2df



##### _GTK4 panel for sway and wayfire_

Waypanel  is a lightweight, modular, and highly customizable status panel designed for the Sway and Wayfire. Built with Python and leveraging GTK 4/Adwaita , it mimics a shell-like interface while prioritizing efficiency and extensibility. Supports multiple panels (top, bottom, left, right) with customizable styling. Plugins can append widgets (e.g., system monitors, app launchers) or manage gestures for interactive workflows. 

How to Install `waypanel`
=========================

##### if using wayfire: configure wayfire.ini
Ensure the following plugins are enabled in your ~/.config/wayfire.ini: 
    
[core]

plugins = ipc ipc-rules


##### if using sway: 
install https://github.com/killown/pysway

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


