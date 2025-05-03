## waypanel

![example1](https://github.com/user-attachments/assets/6f9bc597-4089-4ffb-b49f-5fcb2f446864)

##### _Gtk4/Adwaita panel made for wayfire_

The core of this panel lies in leveraging a shell overview, reminiscent of GNOME, to elegantly showcase all windows, dock bars, and more. Its primary goal is to optimize CPU usage exclusively during non-overview mode. The panel actively monitors command output, title changes, and widgets only when the overview is active in the background. This means that no unnecessary checks will occur, ensuring that CPU usage remains as low as possible.

How to Install `waypanel`
=========================

This guide provides step-by-step instructions to install `waypanel`, both using `pip` and via `git`. It also includes instructions for setting up a virtual environment.

#### archlinux
    
    pacman -S gtk4-layer-shell gobject-introspection vala playerctl python-gobject wayland-protocols ninja mesa playerctl libadwaita bluez-tools


Installing `waypanel` from github Source
-------------------------------------------------

### Step 1: Clone the `waypanel` Repository and copy the config

Clone the `waypanel` repository from GitHub:

    git clone https://github.com/killown/waypanel.git
    cd waypanel
    mkdir ~/.config/waypanel
    cp -r waypanel/config/* ~/.config/waypanel

### Step 2: Set Up a Virtual Environment (Recommended)

  **Create a virtual environment**:
    
      python3 -m venv waypanel-env
    
  **Activate the virtual environment**:
       
      source waypanel-env/bin/activate
      

### Step 3: Install `waypanel`

Once the virtual environment is activated, install `waypanel` using the following command:

    python3 -m pip install .

## run `waypanel`
~/.local/bin/waypanel


### Theme Compatibility

yay -S gruvbox-plus-icon-theme-git

gsettings set org.gnome.desktop.interface icon-theme 'Gruvbox-Plus-Dark'



### wayfire.ini

required plugins: stipc, scale, ipc, ipc-rules


```

## License
waypanel is licensed under the MIT license. [See LICENSE for more information](https://github.com/killown/waypanel/blob/main/LICENSE).

```

```
