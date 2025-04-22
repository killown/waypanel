import gi
from gi.repository import Gtk

from waypanel.src.plugins.core._base import BasePlugin

# NOTE: Always use GLib.idle_add for non-blocking code.


def get_plugin_placement(panel_instance):
    """
    Define where the plugin should be placed in the panel and its order.
    plugin_loader will use this metadata to append the widget to the panel instance.
    Returns:
        tuple: (position, order, priority)
    """
    # Example of panel_instance usage:
    # position = panel_instance.config["my_plugin"]["position"]
    # the config loaded is ~/.config/waypanel/waypanel.toml
    position = "top-panel-center"  # loader_plugin will append: (left, right, center, systray, after-systray)
    order = 10  # The order will rearrange the plugin sequence.
    priority = 10  # If there are 10 plugins, this one will load last.
    return position, order, priority


def initialize_plugin(panel_instance):
    """
    Initialize the plugin.

    obj: This is the main panel object from panel.py
         It contains references to all panels (top, left, right, bottom)
    """

    example = ExamplePluginFeatures(panel_instance)
    example.create_menu_popover_example()
    # Return the plugin instance so it can interact with other plugins
    # Access this instance from any plugin using: self.obj.plugin_loader.plugins["example"]
    # the plugin filename without .py is the name of the instance
    return example


class ExamplePluginFeatures(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_example = None
        # Setup basic button
        self.menubutton_example = Gtk.Button()

        # The main widget must always be set after the main widget container to which we want to append the target_box.
        # The available actions are `append` to append widgets to the top_panel and `set_content`,
        # which is used to set content in other panels such as the left-panel or right-panel.
        # This part of the code is highly important, as the plugin loader strictly requires this metadata.
        self.main_widget = (self.menubutton_example, "append")

    def append_widget(self):
        # this will tell to the plugin_loader to append the widget to the panel instance
        # the plugin loader will get position() to define where the plugin should append
        return self.menubutton_example

    def create_menu_popover_example(self):
        self.menubutton_example.set_icon_name("preferences-system-symbolic")
        self.menubutton_example.connect("clicked", self.open_popover_example)

        # load_config will return cached version of toml.load(waypanel_toml_file)
        custom_icon = self.config.get("icon", "preferences-system-symbolic")
        self.menubutton_example.set_icon_name(custom_icon)

        # Create system menu popover
        self.popover_example = Gtk.Popover()
        self.popover_example.set_parent(self.menubutton_example)
        self.popover_example.set_has_arrow(False)

        # Populate popover with widgets
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Add some example widgets
        label = Gtk.Label(label="Example Plugin")
        vbox.append(label)

        switch = Gtk.Switch()
        switch.set_active(False)
        vbox.append(switch)

        self.popover_example.set_child(vbox)

    def open_popover_example(self, widget):
        if self.popover_example:
            self.popover_example.popup()

    def popover_is_closed(self, *_):
        print("Example plugin popover closed")
