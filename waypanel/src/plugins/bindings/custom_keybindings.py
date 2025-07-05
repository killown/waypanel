from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True
DEPS = []

PLUGIN_NAME = "custom_keybindings"


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return CustomKeybindingsPlugin(panel_instance)
    return None


class CustomKeybindingsPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.plugin_name = PLUGIN_NAME
        self.register_all_bindings()

    def register_all_bindings(self):
        config_section = self.config.get("custom_keybindings", {})

        for key in config_section:
            if key.startswith("binding_"):
                binding_name = key
                binding_value = config_section[binding_name]

                # Get corresponding command
                command_key = binding_name.replace("binding_", "command_")
                command_value = config_section.get(command_key)

                if not command_value:
                    self.logger.warning(
                        f"[{self.plugin_name}] Missing command for {binding_name}"
                    )
                    continue

                self.logger.info(
                    f"[{self.plugin_name}] Registering: {binding_value} → {command_value}"
                )

                # Register the binding without fallback
                self.register_binding(binding_value, command_value)

    def register_binding(self, keybind, command):
        if self.utils.is_keybind_used(keybind):
            self.logger.warning(
                f"Keybind '{keybind}' already used. Skipping registration."
            )
            return

        self.logger.info(f"Registering keybinding: {keybind}")
        self.ipc.register_binding(
            binding=keybind, command=command, mode="normal", exec_always=True
        )
