import os
from gi.repository import Gtk, Gio
from ...core.utils import Utils
import toml
import subprocess

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


class MenuSetupPlugin:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app
        self.utils = Utils(application_id="com.github.menu-setup-plugin")
        self.config_path = os.path.expanduser("~/.config/waypanel/waypanel.toml")
        self.logger = app.logger  # Assuming logger is available via app instance

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
        self.app.add_action(action)

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
            btn = Gtk.MenuButton(label=menu_name)

            # Set icon if specified in the configuration
            if "icon" in menu_data:
                btn.set_icon_name(menu_data["icon"])
            else:
                btn.set_label(menu_name)

            btn.set_menu_model(menu)
            menu_buttons[menu_name] = btn

            # Add menu items or submenus
            for item in menu_data.get("items", []):
                if "submenu" in item:
                    self.create_submenu(menu, item["submenu"], item["items"])
                else:
                    self.create_menu_item(menu, item["name"], item["cmd"])

            # Attach the button to the systray or panel
            if hasattr(self.obj, "top_panel_box_systray"):
                self.obj.top_panel_box_systray.append(btn)
            else:
                self.logger.error("Systray box not found in Panel object.")

    def menu_run_action(self, action, parameter, cmd):
        """Run the specified command when a menu item is activated."""
        try:
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            self.logger.error(f"Error running command '{cmd}': {e}")


def position():
    """Define the plugin's position and order."""
    return "right", 5  # Position: right, Order: 5


def initialize_plugin(obj, app):
    """Initialize the plugin."""
    if ENABLE_PLUGIN:
        plugin = MenuSetupPlugin(obj, app)
        plugin.setup_menus()
        return plugin
