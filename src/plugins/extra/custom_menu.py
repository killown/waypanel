ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    return "top-panel-systray", 5


def initialize_plugin(panel_instance):
    """Initialize the plugin."""
    if ENABLE_PLUGIN:
        custom_menu = call_plugin_class()
        return custom_menu(panel_instance)


def call_plugin_class():
    from src.plugins.core._base import BasePlugin

    class MenuSetupPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.menu_button = None
            self.config_path = self.os.path.expanduser("~/.config/waypanel/config.toml")
            self.widgets = []
            self.main_widget = (self.widgets, "append")

        def on_start(self):
            self.setup_menus()

        def load_menu_config(self):
            """Load menu configuration from config.toml."""
            if not self.os.path.exists(self.config_path):
                self.logger.error(f"Menu config file not found: {self.config_path}")
                return {}
            with open(self.config_path, "r") as f:
                config = self.toml.load(f)
                return config.get("menu", {})

        def menu_run_action(self, action, parameter, cmd):
            """Run the specified command when a menu item is activated."""
            try:
                self.run_cmd(cmd)
            except Exception as e:
                self.logger.error(f"Error running command '{cmd}': {e}")

        def _sanitize_name(self, name):
            """Creates a safe action name from a menu label (e.g., 'My App' -> 'my-app')."""
            return name.lower().replace(" ", "-").replace("_", "-")

        def _convert_toml_to_action_map(self, toml_items: list) -> dict:
            """
            Recursively converts the TOML list structure into the nested action_map
            dictionary structure, now correctly including the optional 'icon' name.
            """
            action_map = {}
            for item in toml_items:
                if "submenu" in item:
                    submenu_label = item["submenu"]
                    action_map[submenu_label] = {
                        "is_submenu": True,
                        "items": self._convert_toml_to_action_map(item["items"]),
                    }
                else:
                    action_name = self._sanitize_name(item["name"])
                    cmd = item["cmd"]
                    icon_name = item.get("icon")
                    action_entry = {
                        "label": item["name"],
                        "callback": lambda a, p, c=cmd: self.menu_run_action(a, p, c),
                    }
                    if icon_name:
                        action_entry["icon"] = icon_name
                    action_map[action_name] = action_entry
            return action_map

        def setup_menus(self):
            """Set up menus based on the configuration by using the enhanced gtk_helper."""
            menu_config = self.load_menu_config()
            if not menu_config:
                self.logger.warning("No menu configuration found.")
                return
            for menu_name, menu_data in menu_config.items():
                action_map = self._convert_toml_to_action_map(
                    menu_data.get("items", [])
                )
                menu_button = self.gtk_helper.create_menu_with_actions(
                    action_map=action_map, action_prefix="app"
                )
                menu_button.set_label(menu_name)
                self.gtk_helper.add_cursor_effect(menu_button)
                menu_button.set_icon_name(
                    self.gtk_helper.icon_exist(
                        "custom_menu",
                        [
                            "utilities-terminal-symbolic",
                            "open-menu-symbolic",
                        ],
                    )
                )
                self.widgets.append(menu_button)

        def about(self):
            """A plugin that dynamically creates custom menus and submenus based on a TOML configuration file."""
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin creates dynamic, user-configurable menus for the panel.
            The refactored code now fully leverages the enhanced `self.gtk_helper.create_menu_with_actions`
            utility, significantly simplifying the `MenuSetupPlugin` logic.
            The key change is the introduction of `_convert_toml_to_action_map`, which is a recursive
            method that transforms the TOML file's structure (which uses lists of dictionaries) into
            the hierarchical dictionary structure (`action_map`) expected by the helper.
            This method:
            1.  **Handles Recursion**: It detects `submenu` items and recursively calls itself to build
                the nested `items` dictionary.
            2.  **Generates Actions**: For command items (leaf nodes), it creates a unique, safe action name
                using `_sanitize_name` and generates a `callback` lambda. This lambda captures the shell
                command (`cmd`) from the TOML file and passes it to the `menu_run_action` method when the
                menu item is clicked. It now correctly includes the optional 'icon' field in the action map.
            By providing this structured `action_map` to `self.gtk_helper.create_menu_with_actions`, the
            plugin delegates all boilerplate Gtk/Gio setup—including recursive menu model construction,
            action group creation, and callback wiring—making `setup_menus` much more concise and robust.
            """
            return self.code_explanation.__doc__

    return MenuSetupPlugin
