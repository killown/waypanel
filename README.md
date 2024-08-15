## waypanel

![output-DP-1](https://github.com/user-attachments/assets/5eb066b9-381b-4964-b941-0a1a115897f4)


##### _Gtk4/Adwaita panel made for wayfire_

The core of this panel lies in leveraging a shell overview, reminiscent of GNOME, to elegantly showcase all windows, dock bars, and more. Its primary goal is to optimize CPU usage exclusively during non-overview mode. The panel actively monitors command output, title changes, and widgets only when the overview is active in the background. This means that no unnecessary checks will occur, ensuring that CPU usage remains as low as possible.

How to Install `waypanel`
=========================

This guide provides step-by-step instructions to install `waypanel`, both using `pip` and via `git`. It also includes instructions for setting up a virtual environment.

Method 1: Installing `waypanel` using `pip`
-------------------------------------------


### Step 1: Set Up a Virtual Environment (Recommended)

  **Create a virtual environment**:
    
    python3 -m venv waypanel-env
    
  **Activate the virtual environment**:
        
    source waypanel-env/bin/activate
        
  **Install `waypanel`**:
    
    pip install waypanel
    

### Step 2: Run `waypanel`

After installation, you can run `waypanel` using:

    /path/to/waypanel-env/bin/waypanel


### Step 4:  Add Environment Activation to Shell Startup

To automatically activate the virtual environment when you navigate to your project directory, you can add the following lines to your `.bashrc`, `.zshrc`, or equivalent shell configuration file:

    source /path/to/waypanel-env/bin/activate

Method 2: Installing `waypanel` from github Source
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
- Bar with various positions: on top (exclusive) or in the background behind all windows
- Easily create custom menus using TOML
- Configuration for custom gesture actions for mouse buttons and scrolling
- Configuration for custom gestures for the top left and top right panels, offering more command possibilities
- Lightweight with low CPU usage, as it doesn't monitor Bluetooth, network, and other functionalities
- Adjust sound volume using the mouse wheel in the top bar.

#### Info from focused window

- CPU
- MEM
- Disk
- take notes of every window
- pid
- current workspace

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
