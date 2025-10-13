screen_width = 1920  # Fallback width when WayfireSocket cannot be used
FIXED_DIMENSION = 32.0  # Fixed value
distributor_id = "linux"  # Fallback distributor ID when 'distro' is not imported
distributor_logo_fallback_icons = [
    f"distributor-{distributor_id}",
    f"{distributor_id}-logo",
    f"{distributor_id}_logo",
    f"distributor_{distributor_id}",
    f"logo{distributor_id}",
    f"{distributor_id}logo",
]

default_config = {
    "_section_hint": (
        "General configuration settings for Waypanel, a panel "
        "for Wayland compositors like Wayfire and Sway."
    ),
    "plugins": {
        "_section_hint": ("Configuration for loading and managing Waypanel plugins."),
        "enabled": [],
        "list_hint": (
            "A comma-separated list of enabled plugins (e.g., 'taskbar, calendar'). "
            "If left empty, all discovered plugins will be loaded, unless disabled."
        ),
        "disabled": [],
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
            "auto_connect": ["", "", ""],
            "auto_connect_hint": (
                "A list of **Bluetooth MAC addresses** (e.g., "
                "['00:1A:7D:XX:XX:XX']) for devices Waypanel should "
                "automatically attempt to connect to when it starts."
            ),
        },
        "network": {
            "_section_hint": "Settings related to network connection management, including Wi-Fi auto-connection behavior.",
            "auto_connect_ssid": [""],
            "auto_connect_ssid_hint": (
                "List of Wi-Fi SSIDs to automatically connect to on "
                "startup (whitelist). All other saved Wi-Fi connections "
                "will be set to manual connect (autoconnect=no)."
            ),
        },
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
                "from covering it and resizing the available desktop area."
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
        },
    },
    "org.waypanel.plugin.bluetooth": {
        "_section_hint": (
            "Settings for the Bluetooth plugin, used to manage connections to local devices."
        ),
        "hide_in_systray": True,
        "main_icon": "bluetooth-symbolic",
        "fallback_main_icons": [
            "org.gnome.Settings-bluetooth-symbolic",
            "bluetooth",
        ],
    },
    "org.waypanel.plugin.global_shortcuts": {
        "_section_hint": (
            "Provides system-wide D-Bus actions to link keyboard shortcuts directly to commands in active plugins"
        ),
        "open_editor": "open_with_editor.open_popover_folders",
    },
    "org.waypanel.plugin.open_with_editor": {
        "_section_hint": (
            "A plugin to quickly search and open files from a configured directory, using a specified editor based on file extension"
        ),
    },
    "org.waypanel.plugin.wayfire_plugins": {
        "_section_hint": (
            "Settings for Wayfire-specific plugin integration and status updates."
        ),
        "hide_in_systray": True,
    },
    "org.waypanel.plugin.notes": {
        "_section_hint": (
            "Configuration for the Quick Notes plugin, allowing users to save and view short text entries."
        ),
        "main_icon": "stock_notes",
        "fallback_main_icons": [
            "accessories-notes-symbolic",
            "xapp-annotations-text-symbolic",
            "accessories-notes",
        ],
        "icon_delete": "edit-delete",
        "hide_in_systray": False,
    },
    "org.waypanel.plugin.overflow_indicator": {
        "_section_hint": (
            "Settings for the Overflow Indicator plugin, which shows a button when other panel items are hidden due to lack of space."
        )
    },
    "org.waypanel.plugin.app_launcher": {
        "_section_hint": (
            "Configuration for the Application Menu (Start Menu) button and associated settings."
        ),
        "main_icon": "start-here",
        "fallback_main_icons": distributor_logo_fallback_icons,
    },
    "org.waypanel.plugin.screen_recorder": {"hide_in_systray": False},
    "org.waypanel.plugin.exit_dashboard": {
        "hide_in_systray": False,
    },
    "org.waypanel.plugin.system_monitor": {"hide_in_systray": False},
    "org.waypanel.plugin.mullvad": {
        "hide_in_systray": False,
    },
    "org.waypanel.plugin.taskbar": {
        "_section_hint": (
            "Configuration for the Taskbar plugin (shows running applications)."
        ),
        "panel": {
            "_section_hint": "Layer-shell and size configuration for the panel that hosts the Taskbar plugin.",
            "name": "bottom-panel-center",
            "name_hint": (
                "The unique **Layer-shell name** for this panel (e.g., "
                "'bottom-panel-center'). Used by Wayland compositors to identify "
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
    "org.waypanel.plugin.dockbar": {
        "_section_hint": (
            "Configuration for the Dockbar plugin (for favorite/pinned applications)."
        ),
        "panel": {
            "_section_hint": "Layer-shell, size, and orientation configuration for the panel that hosts the Dockbar plugin.",
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
                "Settings defining the list of pinned/favorite applications that appear in the Dockbar."
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
    "org.waypanel.plugin.custom_menu": {
        "_section_hint": (
            "Configuration for the custom menu plugin, used for running "
            "scripts or system commands."
        ),
        "hide_in_systray": False,
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
}
