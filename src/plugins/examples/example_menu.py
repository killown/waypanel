def get_plugin_metadata(_):
    return {
        "enabled": True,
        "container": "top-panel-right",
        "index": 6,
        "deps": ["top_panel"],
    }


def get_plugin_class():
    import re
    from src.plugins.core._base import BasePlugin

    class ExampleMenuPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.logger.info("ExampleMenuPlugin initialized.")

        async def on_start(self):
            self.logger.info("Starting example menu plugin.")
            self.create_menu_popover_example()
            self.logger.info("Example menu plugin started and menu button added.")

        def create_menu_popover_example(self):
            self.logger.info("Creating menu popover example.")
            self.menubutton_example = self.gtk.MenuButton()
            self.main_widget = (self.menubutton_example, "append")
            self.menubutton_example.set_icon_name("preferences-system-symbolic")
            self.menubutton_example.add_css_class("top_left_widgets")

            menu_icon = (
                self.config_handler.config_data("panel", {})  # pyright: ignore
                .get("top", {})
                .get("example_icon", "preferences-system-symbolic")
            )
            self.menubutton_example.set_icon_name(self.gtk_helper.get_icon(menu_icon))  # pyright: ignore

            self.create_menu_model()

        def create_menu_model(self):
            self.logger.info("Creating menu model.")
            menu = self.gio.Menu()

            applications = self.gio.AppInfo.get_all()
            categorized_apps = {}

            for app in applications:
                app_name = app.get_name()
                app_command = app.get_commandline()
                app_categories = app.get_categories()  # pyright: ignore
                if not app_categories:
                    app_categories = "Other"

                primary_category = app_categories.split(";")[0].strip()
                if not primary_category:
                    primary_category = "Other"

                if primary_category not in categorized_apps:
                    categorized_apps[primary_category] = []
                categorized_apps[primary_category].append((app_name, app_command))

            sorted_categories = sorted(categorized_apps.keys())

            action_group = self.gio.SimpleActionGroup()
            for category in sorted_categories:
                apps_in_category = categorized_apps[category]
                submenu = self.gio.Menu.new()

                for app_name, app_command in apps_in_category:
                    ac_name = re.sub(r"[^a-zA-Z0-9]", "_", app_name)
                    action_name = f"launch.{ac_name}"
                    menu_item = self.gio.MenuItem.new(app_name, f"app.{action_name}")
                    submenu.append_item(menu_item)

                    action = self.gio.SimpleAction.new(action_name, None)
                    action.connect("activate", self.run_application, app_command)
                    action_group.add_action(action)

                section = self.gio.MenuItem.new_submenu(category, submenu)
                menu.append_item(section)

            self.menubutton_example.set_menu_model(menu)
            self.menubutton_example.insert_action_group("app", action_group)

        def run_application(self, action, parameter, app_id):
            self.logger.info(f"Running application: {app_id}")
            try:
                self.cmd.run(app_id)
            except Exception as e:
                self.logger.error(f"Error running application {app_id}: {e}")

        def about(self):
            """A plugin that creates a dynamic application menu from installed applications, grouped by category."""
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin creates a dynamic application menu for the panel.
            It scans the system for installed applications, organizes them into
            categories, and displays them in a `self.gtk.MenuButton`.

            The core logic is centered on **dynamic UI generation and application launching**:

            1.  **UI Creation**: It creates a `self.gtk.MenuButton` and sets a system icon,
                with the option to use a custom icon from the panel's configuration.
            2.  **Menu Model**: It uses `self.gio.AppInfo.get_all()` to retrieve a list of all
                installed applications.
            3.  **Categorization**: Applications are grouped by their primary category
                (e.g., "Utility", "Network") to create a structured submenu.
            4.  **Action Handling**: For each application, it creates a `self.gio.SimpleAction`
                that, when activated, calls the `run_application` method.
            5.  **Placement**: The `get_plugin_metadata` function specifies the button's
                position on the `top-panel-right`.
            """
            return self.code_explanation.__doc__

    return ExampleMenuPlugin
