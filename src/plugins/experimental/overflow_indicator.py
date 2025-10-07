def get_plugin_metadata(_):
    return {
        "enabled": True,
        "index": 1,
        "container": "top-panel-systray",
        "deps": ["top_panel"],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class OverflowIndicator(BasePlugin):
        PLUGIN_ID = "overflow_indicator"

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.is_revealed = False
            self.hidden_widgets_box = self.gtk.Box.new(
                self.gtk.Orientation.HORIZONTAL, 0
            )
            self.hidden_widgets_box.set_hexpand(False)
            self.hidden_widgets_box.set_homogeneous(False)
            self.revealer = self.gtk.Revealer.new()
            self.revealer.set_reveal_child(False)
            self.revealer.set_transition_duration(200)
            self.revealer.set_transition_type(
                self.gtk.RevealerTransitionType.SLIDE_RIGHT
            )
            self.revealer.set_child(self.hidden_widgets_box)
            self.toggle_button = self.gtk.Button.new()
            self.toggle_button.set_icon_name("view-more-symbolic")
            self.toggle_button.add_css_class("flat")
            self.toggle_button.add_css_class("panel-button")
            self.toggle_button.connect("clicked", self._on_toggle_clicked)
            self.widget = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
            self.widget.add_css_class("linked")
            self.widget.append(self.toggle_button)
            self.widget.append(self.revealer)
            self.main_widget = (self.widget, "append")
            self.plugin_loader.register_overflow_container(self)
            self.logger.info(f"{self.PLUGIN_ID} initialized")

        def _on_toggle_clicked(self, *args):
            """Toggles the state of the self.gtk.Revealer."""
            self.is_revealed = not self.is_revealed
            self.revealer.set_reveal_child(self.is_revealed)
            self.logger.debug(f"Overflow toggled: {self.is_revealed}")
            icon_name = "view-more-symbolic" if not self.is_revealed else "arrow-right"
            self.toggle_button.set_icon_name(icon_name)

        def add_hidden_widget(self, widget):
            """
            Method called by PluginLoader to add a plugin's widget.
            The widgets are correctly appended to the hidden_widgets_box,
            which is the child of the self.gtk.Revealer.
            """
            widget.set_visible(True)
            self.hidden_widgets_box.append(widget)
            self.logger.info(f"Widget {widget.get_name()} added to overflow container.")

        def about(self):
            """Provides a toggle button to reveal or hide an overflow container for other panel widgets."""
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin creates an overflow mechanism using a self.gtk.Revealer.

            1. Widget Structure: The main widget is a self.gtk.Box containing the
               `toggle_button` and the `revealer`. The `revealer` itself holds the
               `hidden_widgets_box`, where overflowed plugin widgets are placed (via
               `add_hidden_widget`).

            2. Toggling Logic: The `_on_toggle_clicked` method flips the internal
               `self.is_revealed` state and passes this boolean directly to
               `self.revealer.set_reveal_child()`. This triggers the transition effect
               (`SLIDE_RIGHT`) to show or hide the overflow box smoothly. The button's
               icon is also updated to reflect the current state.
            """
            return self.code_explanation.__doc__

    return OverflowIndicator
