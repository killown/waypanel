import gi
from gi.repository import Gtk  # pyright: ignore
from src.plugins.core._base import BasePlugin

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return "top-panel-systray", 1


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return OverflowIndicatorPlugin(panel_instance)


class OverflowIndicatorPlugin(BasePlugin):
    PLUGIN_ID = "overflow_indicator"

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.is_revealed = False
        self.hidden_widgets_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self.hidden_widgets_box.set_hexpand(False)
        self.hidden_widgets_box.set_homogeneous(False)
        self.revealer = Gtk.Revealer.new()
        self.revealer.set_reveal_child(False)
        self.revealer.set_transition_duration(200)
        self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        self.revealer.set_child(self.hidden_widgets_box)
        self.toggle_button = Gtk.Button.new()
        self.toggle_button.set_icon_name("view-more-symbolic")
        self.toggle_button.add_css_class("flat")
        self.toggle_button.add_css_class("panel-button")
        self.toggle_button.connect("clicked", self._on_toggle_clicked)
        self.widget = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self.widget.add_css_class("linked")
        self.widget.append(self.toggle_button)
        self.widget.append(self.revealer)
        self.main_widget = (self.widget, "append")
        self.plugin_loader.register_overflow_container(self)
        self.logger.info(f"{self.PLUGIN_ID} initialized")

    def _on_toggle_clicked(self, *args):
        """Toggles the state of the Gtk.Revealer."""
        self.is_revealed = not self.is_revealed
        self.revealer.set_reveal_child(self.is_revealed)
        self.logger.debug(f"Overflow toggled: {self.is_revealed}")
        icon_name = "view-more-symbolic" if not self.is_revealed else "arrow-right"
        self.toggle_button.set_icon_name(icon_name)

    def add_hidden_widget(self, widget: Gtk.Widget):
        """
        Method called by PluginLoader to add a plugin's widget.
        The widgets are correctly appended to the hidden_widgets_box,
        which is the child of the Gtk.Revealer.
        """
        widget.set_visible(True)
        self.hidden_widgets_box.append(widget)
        self.logger.info(f"Widget {widget.get_name()} added to overflow container.")
