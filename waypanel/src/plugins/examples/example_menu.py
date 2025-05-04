import os
import toml
from gi.repository import Gtk, Gio
import re

from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = False
# NOTE: If the code hangs, it will delay the execution of all plugins. Always use GLib.idle_add for non-blocking code.


def get_plugin_placement(panel_instance):
    """
    Define plugin position and order.
    """
    return "top-panel-right", 6, 6


def initialize_plugin(panel_instance):
    """
    Initialize the example menu plugin.
    Args:
        obj: The main panel object from panel.py
        app: The main application instance
    """
    if ENABLE_PLUGIN:
        panel_instance.logger.info("Initializing example menu plugin.")
        example_menu = ExampleMenuPlugin(panel_instance)
        example_menu.create_menu_popover_example()
        panel_instance.logger.info(
            "Example menu plugin initialized and menu button added."
        )
        return example_menu


class ExampleMenuPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self._setup_config_paths()
        self.logger.info("ExampleMenuPlugin initialized.")

    def append_widget(self):
        return self.menubutton_example

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.waypanel_cfg = os.path.join(self.config_path, "waypanel.toml")
        self.utils = self.obj.utils

    def create_menu_popover_example(self):
        """
        Create a menu button and attach it to the panel.
        """
        self.logger.info("Creating menu popover example.")

        # Create the MenuButton
        self.menubutton_example = Gtk.MenuButton()
        self.menubutton_example.set_icon_name("preferences-system-symbolic")
        self.menubutton_example.add_css_class("top_left_widgets")

        # Load custom icon from config if available
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
        if os.path.exists(waypanel_config_path):
            with open(waypanel_config_path, "r") as f:
                config = toml.load(f)
                menu_icon = (
                    config.get("panel", {})
                    .get("top", {})
                    .get("example_icon", "preferences-system-symbolic")
                )
                self.menubutton_example.set_icon_name(
                    self.utils.get_nearest_icon_name(menu_icon)
                )

        # use append_widget instead
        # obj.top_panel_box_systray.append(self.menubutton_example)

        # Create and set the menu model
        self.create_menu_model()

    def create_menu_model(self):
        """
        Create a Gio.Menu and populate it with application entries grouped by category.
        """
        self.logger.info("Creating menu model.")
        menu = Gio.Menu()

        # Populate the menu with installed applications grouped by category
        applications = Gio.AppInfo.get_all()
        categorized_apps = {}

        for app in applications:
            app_name = app.get_name()
            app_command = app.get_commandline()
            app_categories = app.get_categories()  # Get categories from .desktop file
            if not app_categories:
                app_categories = "Other"  # Default category for apps without categories

            # Split categories into a list and use the first one
            primary_category = app_categories.split(";")[0].strip()
            if not primary_category:
                primary_category = "Other"

            # Group apps by category
            if primary_category not in categorized_apps:
                categorized_apps[primary_category] = []
            categorized_apps[primary_category].append((app_name, app_command))

        # Sort categories alphabetically
        sorted_categories = sorted(categorized_apps.keys())

        # Create submenus for each category
        action_group = Gio.SimpleActionGroup()
        for category in sorted_categories:
            apps_in_category = categorized_apps[category]
            submenu = Gio.Menu.new()

            for app_name, app_command in apps_in_category:
                # Create a unique action name for each application
                ac_name = re.sub(r"[^a-zA-Z0-9]", "_", app_name)
                action_name = f"launch.{ac_name}"  # Replace dots to avoid invalid names
                menu_item = Gio.MenuItem.new(app_name, f"app.{action_name}")
                submenu.append_item(menu_item)

                # Create and connect the action
                action = Gio.SimpleAction.new(
                    action_name, None
                )  # No parameter required
                action.connect("activate", self.run_application, app_command)
                action_group.add_action(action)

            # Add the submenu to the main menu
            section = Gio.MenuItem.new_submenu(category, submenu)
            menu.append_item(section)

        # Set the menu model to the MenuButton
        self.menubutton_example.set_menu_model(menu)

        # Insert the action group into the MenuButton
        self.menubutton_example.insert_action_group("app", action_group)

    def run_application(self, action, parameter, app_id):
        """
        Run the application when a menu item is clicked.
        """
        self.logger.info(f"Running application: {app_id}")
        try:
            self.utils.run_app(app_id)
        except Exception as e:
            self.log_error(f"Error running application {app_id}: {e}")
