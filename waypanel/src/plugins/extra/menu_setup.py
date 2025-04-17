import os
from gi.repository import Gtk, Gio
from ...core.utils import Utils
import toml
import subprocess

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement():
    """Define the plugin's position and order."""
    return "systray", 5  # Position: right, Order: 5


def initialize_plugin(panel_instance):
    """Initialize the plugin."""
    if ENABLE_PLUGIN:
        plugin = MenuSetupPlugin(panel_instance)
        plugin.setup_menus()
        return plugin


class MenuSetupPlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
        self.menu_button = None
        self.utils = Utils(application_id="com.github.menu-setup-plugin")
        self.config_path = os.path.expanduser("~/.config/waypanel/waypanel.toml")
        self.logger = self.obj.logger
        self.widgets = []

    def append_widget(self):
        # a list of buttons
        return self.widgets

    def load_menu_config(self):
        """Load menu configuration from waypanel.toml."""
        if not os.path.exists(self.config_path):
            self.logger.error(f"Menu config file not found: {self.config_path}")
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

            # Set icon if specified in the configuration
            if "icon" in menu_data:
                menu_button.set_icon_name(menu_data["icon"])
            else:
                menu_button.set_label(menu_name)

            menu_button.set_menu_model(menu)
            menu_buttons[menu_name] = menu_button
            self.widgets.append(menu_button)

            # Add menu items or submenus
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
            self.logger.error(f"Error running command '{cmd}': {e}")
