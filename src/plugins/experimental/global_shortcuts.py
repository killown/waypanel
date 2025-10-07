# FIXME: make the plugin bind keys instead of manual setup in wayfire.toml
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        plugin_class = call_plugin_class()
        return plugin_class(panel_instance)


def call_plugin_class():
    from src.plugins.core._base import BasePlugin

    class GlobalShortcuts(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.panel_instance = panel_instance
            self.shortcuts = self.get_config(["plugins", "global_shortcuts"]) or {}
            if not self.shortcuts:
                self.logger.info(
                    "No global shortcuts configured for GlobalShortcuts plugin."
                )
            self.actions = {}

        def on_start(self):
            if isinstance(self.shortcuts, dict):
                for action_name, command_str in self.shortcuts.items():
                    self._create_action(action_name, command_str)

        def _create_action(self, action_name, command_str):
            """
            Cria uma GIO SimpleAction.
            FIX: Alterado para ser parameter-less (None) já que o
            _execute_command_from_action não usa o parâmetro.
            """
            action = self.gio.SimpleAction.new(action_name, None)
            action.connect("activate", self._execute_command_from_action, command_str)
            self.obj.add_action(action)
            self.actions[action_name] = action
            self.logger.info(
                f"Created global action 'app.{action_name}' for command '{command_str}'"
            )

        def _execute_command_from_action(self, action, parameter, command_str):
            """
            Executa o comando associado à ação. Usa o `command_str` passado como dado extra.
            """
            if not command_str or "." not in command_str:
                self.logger.error(
                    f"Invalid command format: '{command_str}'. Expected 'plugin.method'"
                )
                return
            plugin_name, method_name = command_str.split(".", 1)
            target_plugin = self.panel_instance.plugins.get(plugin_name)
            if not target_plugin:
                self.logger.error(
                    f"Plugin '{plugin_name}' not found in panel instance."
                )
                return
            if not hasattr(target_plugin, method_name):
                self.logger.error(
                    f"Method '{method_name}' not found in plugin '{plugin_name}'."
                )
                return
            try:
                getattr(target_plugin, method_name)()
                self.logger.info(f"Executed command: {command_str}")
            except Exception as e:
                self.logger.error(f"Error executing command '{command_str}': {e}")

        def set_main_widget(self):
            self.main_widget = None

        def about(self):
            return "Registers global GIO actions which can be bound to keyboard shortcuts by the user's system."

        def code_explanation(self):
            return self.about()

    return GlobalShortcuts
