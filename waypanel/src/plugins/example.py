import gi
import toml
import os
from gi.repository import Adw, Gtk
from wayfire.ipc import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils
from ..panel import Panel


def position():
    # Define plugin position (left, right, center) and order
    position = "right"
    order = 10  # Higher number means lower priority
    return position, order


def initialize_plugin(obj, app):
    """
    Initialize the plugin.

    obj: This is the main panel object from panel.py
         It contains references to all panels (top, left, right, bottom)
         and utility functions. You can access:
         - obj.top_panel: The top panel window
         - obj.utils: Utility functions for creating widgets, etc.
         - obj.create_gesture(): To add gestures to panels

    app: The main application instance
    """

    # uncomment if you want to enable the plugin
    # example = ExamplePluginFeatures()
    # example.create_menu_popover_example(obj, app)


class ExamplePluginFeatures(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_example = None
        self.app = None
        self.top_panel = None
        self.sock = WayfireSocket()
        self.utils = WayfireUtils(self.sock)

    def create_menu_popover_example(self, obj, app):
        # obj is a instance of class Panel(Adw.Application) from panel.py
        self.top_panel = obj.top_panel
        # This lists all possible methods that can be called with the *obj*
        # Use panel_methods_example for auto-completion and listing different methods
        # Then use obj to actually call the methods and interact with the panel instance
        panel_methods_example = Panel("test")
        self.app = app

        # Setup basic button
        self.menubutton_example = Gtk.Button()
        self.menubutton_example.set_icon_name("preferences-system-symbolic")
        self.menubutton_example.connect("clicked", self.open_popover_example)

        # Add button to right panel
        obj.top_panel_box_right.append(self.menubutton_example)

        # Load custom configuration if exists
        config_path = "~/.config/waypanel/waypanel.toml"
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = toml.load(f)
            custom_icon = config.get("icon", "preferences-system-symbolic")
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
