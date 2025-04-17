import gi
from gi.repository import Adw, Gtk

# NOTE: Always use GLib.idle_add for non-blocking code.


def get_plugin_placement():
    """
    Define where the plugin should be placed in the panel and its order.
    plugin_loader will use this metadata to append the widget to the panel instance.
    Returns:
        tuple: (position, order, priority)
    """
    position = "center"  # loader_plugin will append: (left, right, center, systray, after-systray)
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


class ExamplePluginFeatures(Adw.Application):
    def __init__(self, panel_instance):
        self.popover_example = None
        self.obj = panel_instance
        self.top_panel = None

    def append_widget(self):
        # this will tell to the plugin_loader to append the widget to the panel instance
        # the plugin loader will get position() to define where the plugin should append
        return self.menubutton_example

    def create_menu_popover_example(self):
        # obj is a instance of class Panel(Adw.Application) from panel.py
        # This lists all possible methods that can be called with the *obj*
        # Use panel_methods_example for auto-completion and listing different methods
        # Then use obj to actually call the methods and interact with the panel instance

        # Setup basic button
        self.menubutton_example = Gtk.Button()
        self.menubutton_example.set_icon_name("preferences-system-symbolic")
        self.menubutton_example.connect("clicked", self.open_popover_example)

        # Load custom configuration if exists
        # load_config will return cached version of toml.load(waypanel_toml_file)
        config = self.obj.load_config()
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
