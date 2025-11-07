from wayfire import WayfireSocket

socket = WayfireSocket()
outputs = socket.list_outputs()

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
    "org.waypanel.panel": {
        "_section_hint": ("Global settings for Waypanel's panels "),
        "primary_output": {
            "_section_hint": "Settings for the main display output/monitor.",
            "name": "DP-1",
            "name_hint": (
                "The name of your main display output, as recognized "
                "by the Wayland compositor (e.g., DP-1, HDMI-A-1). "
                "This output determines where Waypanel is placed by default."
            ),
        },
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
            "width_hint": "The width (in pixels) of this horizontal panel, matched to the primary output width.",
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
            "width_hint": "The width (in pixels) of this horizontal panel, matched to the primary output width.",
        },
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
        "main_icon": "notes-panel",
        "fallback_main_icons": [
            "stock_notes",
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
