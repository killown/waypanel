from wayfire import WayfireSocket

socket = WayfireSocket()
outputs = socket.list_outputs()
if outputs:
    first_output_geometry = outputs[0]["geometry"]
    screen_width = first_output_geometry["width"]
else:
    screen_width = 1920
FIXED_DIMENSION = 32.0
default_config = {
    "_section_hint": (
        "General configuration settings for Waypanel, a panel "
        "for Wayland compositors like Wayfire and Sway."
    ),
    "plugins": {
        "_section_hint": ("Configuration for loading and managing Waypanel plugins."),
        "list": "",
        "list_hint": (
            "A comma-separated list of enabled plugins (e.g., 'taskbar, calendar'). "
            "If left empty, all discovered plugins will be loaded, unless disabled."
        ),
        "disabled": "",
        "disabled_hint": (
            "A comma-separated list of disabled plugins (e.g., 'tile, weather'). "
            "These plugins will be skipped during the loading process."
        ),
        "custom_path": "~/.local/share/waypanel/plugins",
        "custom_path_hint": (
            "Absolute path to search for user-defined or custom plugins."
        ),
    },
    "hardware": {
        "_section_hint": "Configuration for core system hardware and peripherals.",
        "primary_output": {
            "_section_hint": "Settings for the main display output/monitor.",
            "name": "DP-1",
            "name_hint": (
                "The name of your main display output, as recognized "
                "by the Wayland compositor (e.g., DP-1, HDMI-A-1). "
                "This output determines where Waypanel is placed by default."
            ),
        },
        "soundcard": {
            "_section_hint": "Soundcard and system volume control settings.",
            "blacklist": "Navi",
            "blacklist_hint": (
                "A comma-separated list of keywords (e.g., 'HDMI', 'Navi') "
                "used to filter out specific audio devices from the "
                "volume control/selector."
            ),
            "max_name_lenght": 35,
            "max_name_lenght_hint": (
                "Maximum number of characters to display for the audio "
                "device's name in the panel widget."
            ),
        },
        "microphone": {
            "_section_hint": "Microphone input device settings.",
            "blacklist": "Navi",
            "blacklist_hint": (
                "A comma-separated list of keywords used to filter out "
                "specific microphone devices from the input selector."
            ),
            "max_name_lenght": 35,
            "max_name_lenght_hint": (
                "Maximum number of characters to display for the microphone "
                "device's name in the panel widget."
            ),
        },
        "bluetooth": {
            "_section_hint": "Bluetooth device connection settings.",
            "connect_devices": ["", "", ""],
            "connect_devices_hint": (
                "A list of **Bluetooth MAC addresses** (e.g., "
                "['00:1A:7D:XX:XX:XX']) for devices Waypanel should "
                "automatically attempt to connect to when it starts."
            ),
        },
        "network": {
            "_section_hint": "auto connect network",
            "auto_connect_ssid": [""],
            "auto_connect_ssid_hint": (
                "List of Wi-Fi SSIDs to automatically connect to on "
                "startup (whitelist). All other saved Wi-Fi connections "
                "will be set to manual connect (autoconnect=no)."
            ),
        },
    },
    "taskbar": {
        "_section_hint": (
            "Configuration for the Taskbar plugin (shows running applications)."
        ),
        "panel": {
            "_section_hint": "Base panel settings for the taskbar's container.",
            "name": "bottom-panel",
            "name_hint": (
                "The unique **Layer-shell name** for this panel (e.g., "
                "'bottom-panel'). Used by Wayland compositors to identify "
                "and manage the panel's layer."
            ),
            "exclusive_zone": True,
            "exclusive_zone_hint": (
                "If **True**, the panel requests an **exclusive zone**, "
                "preventing other maximized windows from covering it and "
                "resizing the available desktop area."
            ),
            "width": 100,
            "width_hint": (
                "The width of the taskbar panel, expressed as a "
                "**percentage** (0 to 100) of the total screen width."
            ),
        },
        "layout": {
            "_section_hint": "Layout and display settings for taskbar items.",
            "icon_size": 32,
            "icon_size_hint": "Size of the application icons in pixels.",
            "spacing": 5,
            "spacing_hint": (
                "Spacing (in pixels) between application icons and labels."
            ),
            "show_label": True,
            "show_label_hint": (
                "Whether to display the application window title next to the icon."
            ),
            "max_title_lenght": 25,
            "max_title_lenght_hint": (
                "Maximum number of characters for the application window "
                "title displayed in the taskbar."
            ),
        },
    },
    "dockbar": {
        "_section_hint": (
            "Configuration for the Dockbar plugin (for favorite/pinned applications)."
        ),
        "panel": {
            "_section_hint": "Base panel settings for the dockbar's container.",
            "name": "left-panel",
            "name_hint": (
                "The unique **Layer-shell name** for this panel (e.g., 'left-panel')."
            ),
            "orientation": "v",
            "orientation_hint": (
                "The display orientation for the dockbar: **'v'** for "
                "vertical (side) or **'h'** for horizontal (top/bottom)."
            ),
            "class_style": "dockbar-buttons",
            "class_style_hint": (
                "The custom **GTK CSS class name** applied to the dock "
                "buttons for theme customization."
            ),
        },
        "app": {
            "_section_hint": (
                "Definitions for pinned applications in the dockbar. "
                "Each key is a unique ID."
            ),
            "firefox-developer-edition": {
                "_section_hint": (
                    "Settings for the Firefox Developer Edition pinned app."
                ),
                "cmd": "gtk-launch firefox-developer-edition.desktop",
                "cmd_hint": (
                    "The **shell command** used to launch the application "
                    "(often using `gtk-launch` for .desktop files)."
                ),
                "icon": "firefox-developer-edition",
                "icon_hint": (
                    "The application's **icon name** (from your icon theme) "
                    "or the absolute path to an icon file."
                ),
                "wclass": "firefox-developer-edition",
                "wclass_hint": (
                    "The **Wayland window class (or app ID)** used by the "
                    "compositor to identify and group windows belonging "
                    "to this application."
                ),
                "desktop_file": "firefox-developer-edition.desktop",
                "desktop_file_hint": (
                    "The name of the corresponding **.desktop file** "
                    "(e.g., 'firefox.desktop') found in your system's "
                    "application directories."
                ),
                "name": "Firefox Developer Edition",
                "name_hint": ("The human-readable display name of the application."),
                "initial_title": "Firefox Developer Edition",
                "initial_title_hint": (
                    "The expected window title when the application first "
                    "launches, used to identify the initial window instance."
                ),
            },
            "chromium": {
                "_section_hint": "Settings for the Chromium pinned app.",
                "cmd": "gtk-launch chromium.desktop",
                "cmd_hint": (
                    "The **shell command** used to launch the application "
                    "(often using `gtk-launch` for .desktop files)."
                ),
                "icon": "chromium",
                "icon_hint": (
                    "The application's **icon name** (from your icon theme) "
                    "or the absolute path to an icon file."
                ),
                "wclass": "chromium",
                "wclass_hint": (
                    "The **Wayland window class (or app ID)** used by the "
                    "compositor to identify and group windows belonging "
                    "to this application."
                ),
                "desktop_file": "chromium.desktop",
                "desktop_file_hint": (
                    "The name of the corresponding **.desktop file** "
                    "(e.g., 'chromium.desktop')."
                ),
                "name": "Chromium",
                "name_hint": ("The human-readable display name of the application."),
                "initial_title": "Chromium",
                "initial_title_hint": (
                    "The expected window title when the application first "
                    "launches, used to identify the initial window instance."
                ),
            },
            "org.gnome.Nautilus": {
                "_section_hint": ("Settings for the Nautilus file manager pinned app."),
                "cmd": "gtk-launch org.gnome.Nautilus.desktop",
                "cmd_hint": (
                    "The **shell command** used to launch the application "
                    "(often using `gtk-launch` for .desktop files)."
                ),
                "icon": "org.gnome.Nautilus",
                "icon_hint": (
                    "The application's **icon name** (from your icon theme) "
                    "or the absolute path to an icon file."
                ),
                "wclass": "org.gnome.Nautilus",
                "wclass_hint": (
                    "The **Wayland window class (or app ID)** used by the "
                    "compositor to identify and group windows belonging "
                    "to this application."
                ),
                "desktop_file": "org.gnome.Nautilus.desktop",
                "desktop_file_hint": ("Name of the corresponding **.desktop file**."),
                "name": "Arquivos",
                "name_hint": ("The human-readable display name of the application."),
                "initial_title": "Arquivos",
                "initial_title_hint": (
                    "The expected window title when the application first "
                    "launches, used to identify the initial window instance."
                ),
            },
            "steam": {
                "_section_hint": "Settings for the Steam pinned app.",
                "cmd": "gtk-launch steam.desktop",
                "cmd_hint": ("The **shell command** used to launch the application."),
                "icon": "steam",
                "icon_hint": (
                    "The application's **icon name** or path to an icon file."
                ),
                "wclass": "steam",
                "wclass_hint": ("The **Wayland window class (or app ID)**."),
                "desktop_file": "steam.desktop",
                "desktop_file_hint": ("Name of the corresponding **.desktop file**."),
                "name": "Steam",
                "name_hint": ("The human-readable display name of the application."),
                "initial_title": "Steam",
                "initial_title_hint": (
                    "The expected window title when the application first launches."
                ),
            },
            "cinny": {
                "_section_hint": "Settings for the Cinny chat client pinned app.",
                "cmd": "gtk-launch cinny.desktop",
                "cmd_hint": ("The **shell command** used to launch the application."),
                "icon": "cinny",
                "icon_hint": (
                    "The application's **icon name** or path to an icon file."
                ),
                "wclass": "cinny",
                "wclass_hint": ("The **Wayland window class (or app ID)**."),
                "desktop_file": "cinny.desktop",
                "desktop_file_hint": ("Name of the corresponding **.desktop file**."),
                "name": "Cinny",
                "name_hint": ("The human-readable display name of the application."),
                "initial_title": "Cinny",
                "initial_title_hint": (
                    "The expected window title when the application first launches."
                ),
            },
            "io.github.Hexchat": {
                "_section_hint": ("Settings for the HexChat IRC client pinned app."),
                "cmd": "gtk-launch io.github.Hexchat.desktop",
                "cmd_hint": ("The **shell command** used to launch the application."),
                "icon": "hexchat",
                "icon_hint": (
                    "The application's **icon name** or path to an icon file."
                ),
                "wclass": "io.github.Hexchat",
                "wclass_hint": ("The **Wayland window class (or app ID)**."),
                "desktop_file": "io.github.Hexchat.desktop",
                "desktop_file_hint": ("Name of the corresponding **.desktop file**."),
                "name": "HexChat",
                "name_hint": ("The human-readable display name of the application."),
                "initial_title": "HexChat",
                "initial_title_hint": (
                    "The expected window title when the application first launches."
                ),
            },
            "org.mozilla.Thunderbird": {
                "_section_hint": (
                    "Settings for the Thunderbird email client pinned app."
                ),
                "cmd": "gtk-launch org.mozilla.Thunderbird.desktop",
                "cmd_hint": ("The **shell command** used to launch the application."),
                "icon": "org.mozilla.Thunderbird",
                "icon_hint": (
                    "The application's **icon name** or path to an icon file."
                ),
                "wclass": "org.mozilla.Thunderbird",
                "wclass_hint": ("The **Wayland window class (or app ID)**."),
                "desktop_file": "org.mozilla.Thunderbird.desktop",
                "desktop_file_hint": ("Name of the corresponding **.desktop file**."),
                "name": "Thunderbird",
                "name_hint": ("The human-readable display name of the application."),
                "initial_title": "Thunderbird",
                "initial_title_hint": (
                    "The expected window title when the application first launches."
                ),
            },
        },
    },
    "calendar": {
        "_section_hint": (
            "Configuration for the Calendar plugin, which displays the date/time "
            "and serves as a host for other widgets (like weather) within its popover."
        ),
        "weather": {
            "_section_hint": (
                "Settings for the Weather sub-plugin, which attaches to the Calendar popover. "
            ),
            "coordinates": ("-23.5505", "-46.6333"),
            "coordinates_hint": (
                "The geographical coordinates for weather lookups (latitude, longitude) "
                "as a tuple of strings (e.g., '34.0522', '-118.2437')."
            ),
        },
    },
    "clipboard": {
        "_section_hint": (
            "Settings for the Clipboard Manager plugin, which tracks "
            "copy/paste history."
        ),
        "server": {
            "_section_hint": (
                "Backend (server) settings for monitoring the clipboard."
            ),
            "log_enabled": False,
            "log_enabled_hint": (
                "If **True**, enables logging of clipboard activity for **debugging only**."
            ),
            "max_items": 100,
            "max_items_hint": (
                "Maximum number of items to keep in the clipboard history cache."
            ),
            "monitor_interval": 0.5,
            "monitor_interval_hint": (
                "The time interval (in seconds) the clipboard manager waits "
                "before checking for new content."
            ),
        },
        "client": {
            "_section_hint": (
                "Frontend (client/UI) settings for the clipboard popover window."
            ),
            "popover_min_width": 500,
            "popover_min_width_hint": (
                "The minimum width (in pixels) for the clipboard "
                "history popover window."
            ),
            "popover_max_height": 600,
            "popover_max_height_hint": (
                "The maximum height (in pixels) for the clipboard "
                "history popover window."
            ),
            "thumbnail_size": 128,
            "thumbnail_size_hint": (
                "Size (in pixels) for image thumbnails displayed in the history list."
            ),
            "preview_text_length": 50,
            "preview_text_length_hint": (
                "Maximum number of characters to show for a plain text item preview."
            ),
            "image_row_height": 60,
            "image_row_height_hint": (
                "The fixed height (in pixels) for history rows that contain image data."
            ),
            "text_row_height": 38,
            "text_row_height_hint": (
                "The fixed height (in pixels) for history rows that contain plain text."
            ),
            "item_spacing": 5,
            "item_spacing_hint": (
                "Spacing (in pixels) between clipboard items in the popover's list."
            ),
        },
    },
    "notify": {
        "_section_hint": (
            "Settings for the Notification Daemon, which handles system notifications."
        ),
        "client": {
            "_section_hint": (
                "Client (popover/display) settings for how notifications are shown."
            ),
            "max_notifications": 5.0,
            "max_notifications_hint": (
                "Maximum number of concurrent pop-up notifications that "
                "will be displayed on the screen at one time."
            ),
            "body_max_width_chars": 80.0,
            "body_max_width_chars_hint": (
                "Maximum number of characters allowed per line before the "
                "notification body text wraps."
            ),
            "notification_icon_size": 64.0,
            "notification_icon_size_hint": (
                "Size (in pixels) of the application icon shown within "
                "the notification pop-up."
            ),
            "popover_width": 500.0,
            "popover_width_hint": (
                "The width (in pixels) of the notification popover window."
            ),
            "popover_height": 600.0,
            "popover_height_hint": (
                "The height (in pixels) of the notification popover window."
            ),
        },
        "server": {
            "_section_hint": "Backend (server) settings.",
            "show_messages": True,
            "show_messages_hint": (
                "If **True**, prints incoming notification messages to the "
                "console/log file for **debugging only**."
            ),
        },
    },
    "notes": {
        "_section_hint": "Icon settings used by the Notes plugin.",
        "notes_icon": "stock_notes",
        "notes_icon_hint": "The icon name for the quick notes button.",
        "notes_icon_delete": "edit-delete",
        "notes_icon_delete_hint": (
            "The icon name for the delete note button within the notes interface."
        ),
    },
    "panel": {
        "_section_hint": (
            "Global settings for Waypanel's layer-shell panels "
            "(top, bottom, left, right)."
        ),
        "bottom": {
            "_section_hint": (
                "Bottom panel configuration. Often used for the Taskbar plugin."
            ),
            "enabled": 1.0,
            "enabled_hint": (
                "Set to **1.0 (enabled)** or **0.0 (disabled)** to show "
                "or hide this entire panel layer."
            ),
            "layer_position": "BACKGROUND",
            "layer_position_hint": (
                "The **stacking order layer** this panel will be placed on. "
                "Use 'BACKGROUND' (behind windows) or 'TOP' (above windows)."
            ),
            "Exclusive": 0,
            "Exclusive_hint": (
                "Set to **1.0 (exclusive)** if the panel should permanently "
                "reserve screen space, preventing maximized windows "
                "from covering it."
            ),
            "width": screen_width,
            "width_hint": "The width (in pixels) of this horizontal panel, matched to the primary output width.",
            "height": FIXED_DIMENSION,
            "height_hint": "The fixed height (in pixels) of this horizontal panel.",
        },
        "left": {
            "_section_hint": (
                "Left panel configuration. Often used for the Dockbar plugin."
            ),
            "enabled": 1.0,
            "enabled_hint": (
                "Set to **1.0 (enabled)** or **0.0 (disabled)** to show "
                "or hide this entire panel layer."
            ),
            "layer_position": "BACKGROUND",
            "layer_position_hint": (
                "The **stacking order layer** this panel will be placed on. "
                "Use 'BACKGROUND' (behind windows) or 'TOP' (above windows)."
            ),
            "Exclusive": 0,
            "Exclusive_hint": (
                "Set to **1.0 (exclusive)** if the panel should permanently "
                "reserve screen space."
            ),
            "height": 0.0,
            "height_hint": "The height (in pixels) of this vertical panel. Set to 0.0 to allow the dockbar to center vertically.",
            "width": FIXED_DIMENSION,
            "width_hint": "The fixed width (in pixels) of this vertical panel.",
        },
        "right": {
            "_section_hint": (
                "Right panel configuration. Reserved for future plugins."
            ),
            "enabled": 1.0,
            "enabled_hint": (
                "Set to **1.0 (enabled)** or **0.0 (disabled)** to show "
                "or hide this entire panel layer."
            ),
            "layer_position": "BACKGROUND",
            "layer_position_hint": (
                "The **stacking order layer** this panel will be placed on. "
                "Use 'BACKGROUND' (behind windows) or 'TOP' (above windows)."
            ),
            "Exclusive": 0,
            "Exclusive_hint": (
                "Set to **1.0 (exclusive)** if the panel should permanently "
                "reserve screen space."
            ),
            "height": 0.0,
            "height_hint": "The height (in pixels) of this vertical panel. Set to 0.0 to allow the dockbar to center vertically.",
            "width": FIXED_DIMENSION,
            "width_hint": "The fixed width (in pixels) of this vertical panel.",
        },
        "top": {
            "_section_hint": (
                "Top panel configuration. Often used for status indicators and menus."
            ),
            "menu_icon": "archlinux-logo",
            "menu_icon_hint": "Icon for the main application menu button.",
            "folder_icon": "folder",
            "folder_icon_hint": "Icon for the quick folder access button.",
            "bookmarks_icon": "internet-web-browser",
            "bookmarks_icon_hint": ("Icon for the web browser bookmarks button."),
            "clipboard_icon": "edit-paste",
            "clipboard_icon_hint": ("Icon for the clipboard manager button."),
            "soundcard_icon": "audio-volume-high",
            "soundcard_icon_hint": ("Icon for the soundcard/volume control button."),
            "system_icon": "system-shutdown",
            "system_icon_hint": (
                "Icon for the system/power menu (shutdown, restart, etc.) button."
            ),
            "bluetooth_icon": "bluetooth",
            "bluetooth_icon_hint": ("Icon for the bluetooth manager button."),
            "notes_icon": "stock_notes",
            "notes_icon_hint": "Icon for the quick notes button.",
            "notes_icon_delete": "delete",
            "notes_icon_delete_hint": "Icon for the delete note button.",
            "layer_position": "TOP",
            "layer_position_hint": (
                "The **stacking order layer** this panel will be placed on. "
                "Use 'BACKGROUND' (behind windows) or 'TOP' (above windows)."
            ),
            "Exclusive": 1.0,
            "Exclusive_hint": (
                "Set to **1.0 (exclusive)** if the panel should permanently "
                "reserve screen space."
            ),
            "height": 32.0,
            "height_hint": ("The fixed height (in pixels) of the top panel area."),
            "width": screen_width,
            "width_hint": "The width (in pixels) of this horizontal panel, matched to the primary output width.",
            "max_note_lenght": 100.0,
            "max_note_lenght_hint": (
                "Maximum number of characters allowed for a single quick note entry."
            ),
        },
    },
    "menu": {
        "_section_hint": (
            "Configuration for the custom menu plugin, used for running "
            "scripts or system commands."
        ),
        "Wayfire": {
            "_section_hint": (
                "A custom submenu for Wayfire-related scripts and commands."
            ),
            "icon": "dialog-scripts",
            "icon_hint": "Icon for this specific submenu entry.",
            "items": [
                {
                    "name": "Update and install wayfire",
                    "name_hint": "The display name for the menu item.",
                    "cmd": "sh $HOME/Scripts/wayfire/update-wayfire.sh",
                    "cmd_hint": (
                        "The **full shell command** that runs when this "
                        "menu item is clicked."
                    ),
                },
                {
                    "name": "Run wayfire benchmark",
                    "name_hint": "The display name for the menu item.",
                    "cmd": "sh $HOME/Scripts/wayfire/wayfire-headless-bench.sh",
                    "cmd_hint": (
                        "The **full shell command** that runs when this "
                        "menu item is clicked."
                    ),
                },
                {
                    "name": "Patch wayfire and install",
                    "name_hint": "The display name for the menu item.",
                    "cmd": (
                        'kitty -e bash -c "cd $HOME/Git/wayfire/; '
                        "$HOME/Scripts/wayfire/patch.apply; "
                        '$HOME/Scripts/wayfire/install"'
                    ),
                    "cmd_hint": (
                        "The **full shell command** that runs when this "
                        "menu item is clicked."
                    ),
                },
                {
                    "name": "Wayland Color Picker",
                    "name_hint": "The display name for the menu item.",
                    "cmd": "wl-color-picker",
                    "cmd_hint": (
                        "The **full shell command** that runs when this "
                        "menu item is clicked."
                    ),
                },
                {
                    "name": "Turn ON/OFF DP-2",
                    "name_hint": "The display name for the menu item.",
                    "cmd": "python $HOME/Scripts/wayfire/output_dp_2.py",
                    "cmd_hint": (
                        "The **full shell command** that runs when this "
                        "menu item is clicked."
                    ),
                },
            ],
            "items_hint": (
                "List of custom menu entries. Each entry is a dictionary "
                "with 'name' (display label) and 'cmd' (shell command)."
            ),
        },
    },
    "folders": {
        "_section_hint": (
            "Configuration for the quick access folders/directories menu."
        ),
        "Imagens": {
            "_section_hint": "A custom folder entry definition.",
            "name": "Wallpapers",
            "name_hint": "The display name for the folder in the menu.",
            "path": "/home/neo/Imagens/Wallpapers/",
            "path_hint": (
                "The **absolute path** (starting from `/`) to the directory "
                "that will be opened."
            ),
            "filemanager": "thunar",
            "filemanager_hint": (
                "The command for the file manager to use when opening "
                "the folder (e.g., `nautilus`, `thunar`, `dolphin`)."
            ),
            "icon": "folder-symbolic",
            "icon_hint": "Icon name for the folder entry.",
        },
    },
}
