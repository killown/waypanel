## waypanel

![test](https://github.com/user-attachments/assets/e0532323-8032-40d7-9dd4-e02ce41bd227)
![test](https://github.com/user-attachments/assets/d38345e3-9c26-4f26-b9c4-8e7261466b28)

##### _Gtk4/Adwaita panel made for wayfire_

The core of this panel lies in leveraging a shell overview, reminiscent of GNOME, to elegantly showcase all windows, dock bars, and more. Its primary goal is to optimize CPU usage exclusively during non-overview mode. The panel actively monitors command output, title changes, and widgets only when the overview is active in the background. This means that no unnecessary checks will occur, ensuring that CPU usage remains as low as possible.

How to Install `waypanel`
=========================

This guide provides step-by-step instructions to install `waypanel`, both using `pip` and via `git`. It also includes instructions for setting up a virtual environment.

#### archlinux
    
    pacman -S gtk4-layer-shell gobject-introspection vala playerctl python-gobject wayland-protocols ninja mesa playerctl libadwaita


Installing `waypanel` from github Source
-------------------------------------------------

### Step 1: Clone the `waypanel` Repository

Clone the `waypanel` repository from GitHub:

    git clone https://github.com/killown/waypanel.git
    cd waypanel

### Step 2: Set Up a Virtual Environment (Recommended)

  **Create a virtual environment**:
    
      python3 -m venv waypanel-env
    
  **Activate the virtual environment**:
       
      source waypanel-env/bin/activate
      

### Step 3: Install `waypanel`

Once the virtual environment is activated, install `waypanel` using the following command:

    python3 -m pip install .



### Theme Compatibility

yay -S gruvbox-plus-icon-theme-git

gsettings set org.gnome.desktop.interface icon-theme 'Gruvbox-Plus-Dark'




### wayfire.ini

required plugins: stipc, scale, ipc, ipc-rules

### minimal panel setup

panel.toml [monitor]

### Current features

- Dockbar
- Information panel with numerous features
- Top panel with a GNOME appearance
- Custom CSS customizations
- Panel for workspace navigation
- Easily create custom menus using TOML
- Configuration for custom gesture actions for mouse buttons and scrolling
- Configuration for custom gestures for the top left and top right panels, offering more command possibilities
- Lightweight with low CPU usage, as it doesn't monitor Bluetooth, network, and other functionalities
- Adjust sound volume using the mouse wheel in the top bar.

#### Create custom output in the top bar using toml

```

[some_name]
refresh = 1000 #in ms
position = "center" #left center right
cmd = "command" #command or script
css_class = "css_class" #to customize the widget look

```

#### Create new menus in the top bar using toml
```

[[MyMenu.item_1]]
cmd = "command"
name = "Menu Label"

[[MyMenu.item_2]]
cmd = "command"
name = "Menu Label"
submenu = "submenu_name"

```

## License
waypanel is licensed under the MIT license. [See LICENSE for more information](https://github.com/killown/hyprpybar/blob/main/LICENSE).

```

```
