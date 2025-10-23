def get_plugin_metadata(panel):
    about = """A plugin that dynamically creates custom menus and submenus based on a TOML configuration file."""

    id = "org.waypanel.plugin.custom_menu"
    default_container = "top-panel-systray"
    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Custom Menus",
        "version": "1.0.0",
        "enabled": True,
        "index": 4,
        "container": container,
        "deps": [
            "top_panel",
        ],
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class MenuSetupPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.menu_button = None
            self.widgets = []
            self.main_widget = (self.widgets, "append")

        def on_start(self):
            self.setup_menus()

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
                if not item:
                    continue
                if "submenu" in item:
                    submenu_label = item["submenu"]
                    action_map[submenu_label] = {
                        "is_submenu": True,
                        "items": self._convert_toml_to_action_map(item["items"]),
                    }
                elif "name" in item:
                    action_name = self._sanitize_name(item["name"])
                    if action_name == "separator":
                        action_map[action_name] = {"is_separator": True}
                        continue
                    cmd = item.get("cmd")
                    icon_name = item.get("icon")
                    action_entry = {
                        "label": item["name"],
                        "callback": lambda a, p, c=cmd: self.menu_run_action(a, p, c)
                        if cmd
                        else None,
                    }
                    if icon_name:
                        action_entry["icon"] = icon_name
                    action_map[action_name] = action_entry
            return action_map

        def setup_menus(self):
            """set up menus based on the configuration by using the enhanced gtk_helper."""
            all_menus_config = self.get_plugin_setting()
            if not all_menus_config:
                self.logger.warning("No configuration sections found for custom menus.")
                return
            for menu_name, menu_data in all_menus_config.items():
                if not isinstance(menu_data, dict) or "items" not in menu_data:
                    self.logger.warning(
                        f"Skipping invalid menu section: '{menu_name}'. Missing 'items'."
                    )
                    continue
                menu_items_list = menu_data.get("items", [])
                if not menu_items_list:
                    self.logger.warning(f"Menu '{menu_name}' has no items defined.")
                    continue
                action_map = self._convert_toml_to_action_map(menu_items_list)
                action_prefix = self._sanitize_name(menu_name)
                menu_button = self.gtk_helper.create_menu_with_actions(
                    action_map=action_map, action_prefix=action_prefix
                )
                menu_button.set_label(menu_name.replace("_", " ").title())
                self.gtk_helper.add_cursor_effect(menu_button)
                configured_icon = menu_data.get("icon")
                if configured_icon:
                    icon_to_use = configured_icon
                else:
                    icon_to_use = self.gtk_helper.icon_exist(
                        f"custom_menu_{menu_name}",
                        [
                            "utilities-terminal-symbolic",
                            "open-menu-symbolic",
                        ],
                    )
                menu_button.set_icon_name(icon_to_use)
                self.widgets.append(menu_button)

        def code_explanation(self):
            """
            This plugin creates dynamic, user-configurable menus for the panel.
            The `setup_menus` function has been adapted to use the new `self.get_plugin_setting()`
            (called without arguments) to fetch the entire configuration dictionary
            for the plugin's section.
            It now iterates over the keys of this dictionary (e.g., 'Wayfire', 'Apps')
            to create multiple custom menu buttons, making the plugin fully flexible
            for multi-menu configurations defined under the main plugin section.
            """
            return self.code_explanation.__doc__

    return MenuSetupPlugin
