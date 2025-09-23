import os
from gi.repository import Gtk, Gio

import toml
import subprocess

from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    return "top-panel-systray", 5  # Position: right, Order: 5


def initialize_plugin(panel_instance):
    """Initialize the plugin."""
    if ENABLE_PLUGIN:
        plugin = MenuSetupPlugin(panel_instance)
        plugin.setup_menus()
        return plugin


class MenuSetupPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.menu_button = None
        self.config_path = os.path.expanduser("~/.config/waypanel/config.toml")
        self.logger = self.logger
        self.widgets = []
        self.main_widget = (self.widgets, "append")

    def load_menu_config(self):
        """Load menu configuration from config.toml."""
        if not os.path.exists(self.config_path):
            self.log_error(f"Menu config file not found: {self.config_path}")
            return {}

        with open(self.config_path, "r") as f:
            config = toml.load(f)  # Use tomllib for TOML parsing (Python 3.11+)
            return config.get("menu", {})

    def create_menu_item(self, menu, name, cmd):
        """Create a menu item with the specified name and command."""
        action_name = f"app.run-command-{name.replace(' ', '-')}"
        action = Gio.SimpleAction.new(action_name, None)
        action.connect("activate", self.menu_run_action, cmd)
        self.obj.add_action(action)

        menu_item = Gio.MenuItem.new(name, f"app.{action_name}")
        menu.append_item(menu_item)

    def create_submenu(self, parent_menu, submenu_label, submenu_items):
        """Create a submenu and append it to the parent menu."""
        submenu = Gio.Menu()
        for item in submenu_items:
            if "submenu" in item:
                self.create_submenu(submenu, item["submenu"], item["items"])
            else:
                self.create_menu_item(submenu, item["name"], item["cmd"])
        parent_menu.append_submenu(submenu_label, submenu)

    def setup_menus(self):
        """Set up menus based on the configuration."""
        menu_config = self.load_menu_config()
        if not menu_config:
            self.logger.warning("No menu configuration found.")
            return

        menu_buttons = {}
        for menu_name, menu_data in menu_config.items():
            menu = Gio.Menu()
            menu_button = Gtk.MenuButton(label=menu_name)
            self.gtk_helper.add_cursor_effect(menu_button)
            if "icon" in menu_data:
                icon_name = menu_data["icon"]
                menu_button.set_icon_name(
                    self.gtk_helper.set_widget_icon_name(
                        "custom_menu", [icon_name, "open-menu-symbolic"]
                    )
                )
            else:
                menu_button.set_label(menu_name)

            menu_button.set_menu_model(menu)
            menu_buttons[menu_name] = menu_button
            self.widgets.append(menu_button)

            for item in menu_data.get("items", []):
                if "submenu" in item:
                    self.create_submenu(menu, item["submenu"], item["items"])
                else:
                    self.create_menu_item(menu, item["name"], item["cmd"])

    def menu_run_action(self, action, parameter, cmd):
        """Run the specified command when a menu item is activated."""
        try:
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            self.log_error(f"Error running command '{cmd}': {e}")

    def about(self):
        """A plugin that dynamically creates custom menus and submenus based on a TOML configuration file."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin creates dynamic, user-configurable menus for the panel.
        Instead of hardcoding menu items, it reads a structured TOML file to build the
        menu's hierarchy and functionality.

        Its core logic is centered on **configuration-driven UI generation and command execution**:

        1.  **Configuration Loading**: It reads a `config.toml` file to get the menu
            structure, including labels, icons, commands, and submenus. This decouples
            the UI from the code, making the menus highly customizable without
            requiring code changes.
        2.  **Recursive Menu Creation**: It uses a recursive approach to handle nested menu structures,
            allowing for complex, multi-level menus.
        3.  **Command Execution**: For each menu item, it creates an action that executes
            a shell command, ensuring that clicking a menu item correctly launches the
            configured application or runs a script.
        4.  **Flexible UI**: It dynamically creates menu button widgets based on
            the top-level menu names found in the configuration, and can use either
            labels or icons as specified in the TOML file.
        """
        return self.code_explanation.__doc__
