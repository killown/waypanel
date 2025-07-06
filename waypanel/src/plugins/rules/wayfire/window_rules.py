from waypanel.src.plugins.core._base import BasePlugin
import os
import toml

CONFIG_PATH = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
ENABLE_PLUGIN = True  # Toggle plugin activation
DEPS = []  # No dependencies


def get_plugin_placement(panel_instance):
    return "background"


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return WindowRulesPlugin(panel_instance)
    return None


class WindowRulesPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.logger.info("[WindowRulesPlugin] Loading window rules from config...")
        self.apply_rules_from_config()

    def load_config(self):
        try:
            with open(CONFIG_PATH, "r") as f:
                return toml.load(f)
        except Exception as e:
            self.logger.error(f"[Failed to load config: {e}")
            return {}

    def apply_rules_from_config(self):
        try:
            # Get [window_rules] section from wayfire.toml
            config_section = self.load_config().get("window_rules", {})

            # Extract all keys (like rule1, rule2...) and sort them
            rule_items = sorted(
                [(k, v) for k, v in config_section.items() if k.startswith("rule")],
                key=lambda x: x[0],
            )

            # Build list of rule strings
            rules_list = [v.strip() for k, v in rule_items if v.strip()]

            if not rules_list:
                self.logger.warning(
                    "[WindowRulesPlugin] No valid rules found in config."
                )
                return

            self.logger.info(f"[WindowRulesPlugin] Applying {len(rules_list)} rules...")

            # Send rules to Wayfire
            result = self.ipc.set_option_values({"window-rules": {"rules": rules_list}})

            if result.get("result") == "ok":
                self.logger.info(
                    f"[WindowRulesPlugin] Successfully applied {len(rules_list)} rules."
                )
            else:
                self.logger.error(
                    f"[WindowRulesPlugin] Failed to apply rules: {result}"
                )
        except Exception as e:
            self.logger.error(f"[WindowRulesPlugin] Error applying rules: {e}")
