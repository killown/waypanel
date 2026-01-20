def get_plugin_metadata(panel):
    id = "org.waypanel.plugin.settings_demo"
    default_container = "top-panel-center"
    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Settings Pure Demo",
        "version": "1.0.8",
        "enabled": True,
        "container": container,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class SettingsDemo(BasePlugin):
        def __init__(self, panel_instance):
            """
            CONSTRUCTOR: Initialize UI and state immediately to prevent loader crashes.
            """
            super().__init__(panel_instance)

            # BasePlugin properties
            self.counter = 0
            self.prefix = "Value"

            # UI using self.gtk (GTK 4.0)
            self.button = self.gtk.Button(label="Loading...")

            # CRITICAL: Register main_widget to satisfy loader.py
            self.main_widget = (self.button, "append")

        def on_enable(self):
            """
            LIFECYCLE: Logic using verified setting methods from _base.py.
            """
            # get_plugin_setting_add_hint: Registers Control Center hint and fetches value
            self.prefix = self.get_plugin_setting_add_hint(
                ["ui", "label_prefix"], "Total", "Text shown before the counter"
            )

            # get_plugin_setting: Standard fetch for plugin-scoped keys
            self.counter = self.get_plugin_setting("data/current", 0)

            # get_root_setting: Fetch global panel configuration
            self.theme = self.get_root_setting(["panel", "theme"], "default")

            self.button.set_label(f"{self.prefix}: {self.counter}")
            self.button.connect("clicked", self._on_interaction)

        def _on_interaction(self, widget):
            """
            Interaction logic using set_plugin_setting and notify_send.
            """
            self.counter += 1

            # set_plugin_setting: Persists value to config.toml
            self.set_plugin_setting(["data", "current"], self.counter)

            widget.set_label(f"{self.prefix}: {self.counter}")

            # notify_send: Verified property from BasePlugin
            self.notify_send(
                title="Setting Updated",
                message=f"{self.prefix} is now {self.counter}",
                icon="low",
            )

            if self.counter >= 10:
                # remove_plugin_setting: Delete key from configuration
                self.remove_plugin_setting(["data", "current"])
                self.counter = 0
                widget.set_label(f"{self.prefix}: Reset")

        def on_disable(self):
            self.logger.info("Settings Demo disabled.")

    return SettingsDemo
