def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.command_manager",
        "name": "Command Manager",
        "version": "1.0.0",
        "enabled": True,
        "container": "background",
        "description": "Dynamic keybinding manager for custom user commands.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class CommandManagerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

        def delay_on_start(self):
            """Lifecycle hook to register all configured commands."""
            self.get_plugin_setting_add_hint(
                ["custom_commands"],
                {
                    "kitty": ["<alt><shift><super> KEY_ENTER", "kitty"],
                    "logout": ["<alt><shift><super> KEY_M", "wayland-logout"],
                },
                "Dictionary of custom commands: name = [binding, command]",
            )
            self.register_custom_bindings()
            return False

        def on_start(self):
            self.glib.timeout_add_seconds(3, self.delay_on_start)

        def register_custom_bindings(self):
            """
            Iterates through the user settings and registers each
            key/value pair as a Wayfire binding.
            """
            settings = self.get_root_setting(
                ["org.waypanel.plugin.command_manager"], None
            )

            commands = settings.get("custom_commands", {})

            for name, data in commands.items():
                if not isinstance(data, list) or len(data) < 2:
                    self.logger.warning(
                        f"Invalid format for command '{name}'. Expected [binding, command]."
                    )
                    continue

                binding, command = data[0], data[1]

                self.logger.info(
                    f"Registering custom command '{name}': {binding} -> {command}"
                )

                self.ipc.register_binding(
                    binding=binding,
                    command=command,
                    exec_always=True,
                    mode="normal",
                )

    return CommandManagerPlugin
