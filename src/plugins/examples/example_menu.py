from gi.repository import Gtk, Gio
import re

from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
# NOTE: If the code hangs, it will delay the execution of all plugins. Always use GLib.idle_add for non-blocking code.

# DEPS list is where you add required plugins to load before this example_menu plugin loads,
# Adding DEPS isn't mandatory, but if top_panel doesn't load before example_menu, example_menu will fail too.
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """
    Define where the plugin should be placed in the panel and its order.
    plugin_loader will use this metadata to append the widget to the panel instance.

    Returns:
        tuple: (position, order, priority) for UI plugins
        str: "background" for non-UI/background plugins

    Valid Positions:
        - Top Panel:
            "top-panel-left"
            "top-panel-center"
            "top-panel-right"
            "top-panel-systray"
            "top-panel-after-systray"

        - Bottom Panel:
            "bottom-panel-left"
            "bottom-panel-center"
            "bottom-panel-right"

        - Left Panel:
            "left-panel-top"
            "left-panel-center"
            "left-panel-bottom"

        - Right Panel:
            "right-panel-top"
            "right-panel-center"
            "right-panel-bottom"

        - Background:
            "background"  # For plugins that don't have a UI

    Parameters:
        panel_instance: The main panel object. Can be used to access config or other panels.
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
        self.logger.info("ExampleMenuPlugin initialized.")

    def create_menu_popover_example(self):
        """
        Create a menu button and attach it to the panel.
        """
        self.logger.info("Creating menu popover example.")
        self.menubutton_example = Gtk.MenuButton()
        # The main widget must always be set after the main widget container to which we want to append the target_box.
        # The available actions are `append` to append widgets to the top_panel and `set_content`,
        # which is used to set content in other panels such as the left-panel or right-panel.
        # This part of the code is highly important, as the plugin loader strictly requires this metadata.
        self.main_widget = (self.menubutton_example, "append")
        # Create the MenuButton
        self.menubutton_example.set_icon_name("preferences-system-symbolic")
        self.menubutton_example.add_css_class("top_left_widgets")

        # Load custom icon from config if available
        menu_icon = (
            self.config.get("panel", {})
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

    def about(self):
        """A plugin that creates a dynamic application menu from installed applications, grouped by category."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin creates a dynamic application menu for the panel.
        It scans the system for installed applications, organizes them into
        categories, and displays them in a `Gtk.MenuButton`.

        The core logic is centered on **dynamic UI generation and application launching**:

        1.  **UI Creation**: It creates a `Gtk.MenuButton` and sets a system icon,
            with the option to use a custom icon from the panel's configuration.
        2.  **Menu Model**: It uses `Gio.AppInfo.get_all()` to retrieve a list of all
            installed applications.
        3.  **Categorization**: Applications are grouped by their primary category
            (e.g., "Utility", "Network") to create a structured submenu.
        4.  **Action Handling**: For each application, it creates a `Gio.SimpleAction`
            that, when activated, calls the `run_application` method.
        5.  **Placement**: The `get_plugin_placement` function specifies the button's
            position on the `top-panel-right`.
        """
        return self.code_explanation.__doc__
