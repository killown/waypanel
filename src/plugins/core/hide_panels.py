def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.hide_panels",
        "name": "Hide Panels",
        "version": "1.0.1",
        "enabled": True,
        "priority": 999,
        "container": "background",
        "deps": ["css_generator"],
        "description": "Orchestrates panel visibility by sinking layers and removing exclusive zones.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class HidePanels(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.panels_to_process = [
                "top_panel",
                "bottom_panel",
                "left_panel",
                "right_panel",
            ]

        def on_start(self):
            for panel_key in self.panels_to_process:
                self.get_plugin_setting_add_hint(
                    ["panels", f"hide_{panel_key}"],
                    False,
                    f"Sink the {panel_key.replace('_', ' ')} into the background and release screen space.",
                )

            self.glib.timeout_add(500, self.apply_layer_logic)

        def apply_layer_logic(self):
            for panel_key in self.panels_to_process:
                should_hide = self.get_plugin_setting(
                    ["panels", f"hide_{panel_key}"], False
                )
                if should_hide:
                    panel_window = getattr(self._panel_instance, panel_key, None)
                    if panel_window:
                        self.transform_panel_to_background(panel_key, panel_window)
            return False

        def transform_panel_to_background(self, panel_key, panel_window):
            """
            Directly manipulates the panel window using self.layer_shell.
            Fixes AttributeError by using set_keyboard_mode for Gtk4.
            """
            self.layer_shell.set_layer(panel_window, self.layer_shell.Layer.BACKGROUND)
            self.layer_shell.set_exclusive_zone(panel_window, 0)
            self.layer_shell.set_keyboard_mode(
                panel_window, self.layer_shell.KeyboardMode.NONE
            )
            panel_window.present()

            self.logger.info(
                f"HidePanels: {panel_key} successfully sunk to background layer."
            )

        def on_disable(self):
            for panel_key in self.panels_to_process:
                panel_window = getattr(self._panel_instance, panel_key, None)
                if panel_window:
                    self.layer_shell.set_layer(panel_window, self.layer_shell.Layer.TOP)
                    self.layer_shell.set_keyboard_mode(
                        panel_window, self.layer_shell.KeyboardMode.NONE
                    )
                    panel_window.present()

    return HidePanels
