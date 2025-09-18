import gi
from gi.repository import Gtk

from src.plugins.core._base import BasePlugin  # this is required for every plugin

# NOTE: Always use GLib.idle_add for non-blocking code.

# DEPS list is where you add required plugins to load before this main_example plugin loads,
# Adding DEPS isn't mandatory, but if top_panel doesn't load before main_example, main_example will fail too.
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """
    Define where the plugin should be placed in the panel and its order.
    plugin_loader will use this metadata to append the widget to the panel instance.

    Returns:
        tuple: (position, order, priority) for UI plugins
        str: "background" for non-UI/background plugins

    Valid Positions:
        - Top Panel:
            "top-panel-left"
            "top-panel-center"
            "top-panel-right"
            "top-panel-systray"
            "top-panel-after-systray"

        - Bottom Panel:
            "bottom-panel-left"
            "bottom-panel-center"
            "bottom-panel-right"

        - Left Panel:
            "left-panel-top"
            "left-panel-center"
            "left-panel-bottom"

        - Right Panel:
            "right-panel-top"
            "right-panel-center"
            "right-panel-bottom"

        - Background:
            "background"  # For plugins that don't have a UI

    Parameters:
        panel_instance: The main panel object. Can be used to access config or other panels.
    """

    plugin_require_ui = True

    # Example: Get position from config (fallback hardcoded for development)
    # position = panel_instance.config.get("my_plugin", {}).get("position", "top-panel-center")
    position = "top-panel-center"  # Possible values listed above
    order = 10  # Order among plugins in the same section
    priority = 10  # Initialization order; lower numbers load first

    if plugin_require_ui:
        return position, order, priority
    else:
        # This marks the plugin as background-only (no UI element)
        return "background"


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
    """BasePlugin is a class that provides a basic structure for plugins"""

    # WARNING:: BasePlugin is Required for every plugin

    def __init__(self, panel_instance):
        # NOTE: the following line ensures your plugin gets all the shared tools, attributes,
        # and integration it needs to work properly inside Waypanel
        # WARNING: super is required for every plugin
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
