# Import necessary modules
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Adw

# Set to True to enable the plugin
ENABLE_PLUGIN = True


# Define the plugin's placement in the panel
def get_plugin_placement(panel_instance):
    position = "systray"  # Position: left side of the panel
    order = 99  # Order: low priority (appears at the end)
    return position, order


# Initialize the plugin
def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return PluginManagerPlugin(panel_instance)


# Plugin class
class PluginManagerPlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.utils = self.obj.utils
        self.plugin_loader = self.obj.plugin_loader

        # Create the main button to open the popover
        self.menubutton_plugin_manager = Gtk.MenuButton()
        self.menubutton_plugin_manager.set_icon_name(
            "preferences-plugin-symbolic"
        )  # Default icon

        # Create the popover content
        self.create_popover_plugin_manager()

        # Add gesture to handle interactions
        self.add_gesture_to_menu_button()

    def append_widget(self):
        """
        Append the plugin manager button to the panel.
        Returns:
            Gtk.Widget: The main button of the plugin.
        """
        return self.menubutton_plugin_manager

    def create_popover_plugin_manager(self):
        """Create and configure the popover for managing plugins."""
        # Create the popover
        self.popover_plugin_manager = Gtk.Popover.new()
        self.popover_plugin_manager.set_has_arrow(False)
        self.popover_plugin_manager.connect("closed", self.popover_is_closed)

        # Create a vertical box to hold the content
        vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        # Add a title label
        title_label = Gtk.Label.new("Plugin Manager")
        title_label.add_css_class("plugin-manager-title")
        vbox.append(title_label)

        # Create a ListBox to display plugins
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        vbox.append(self.listbox)

        # Populate the ListBox with plugin rows
        self.populate_plugin_list()

        # Set the box as the child of the popover
        self.popover_plugin_manager.set_child(vbox)

        # Set the popover parent to the menu button
        self.popover_plugin_manager.set_parent(self.menubutton_plugin_manager)

    def populate_plugin_list(self):
        """
        Populate the ListBox with rows for all plugins (enabled and disabled).
        Disabled plugins will have their switches set to 'off' but remain interactive.
        """
        # Get the list of disabled plugins as a set for quick lookup
        disabled_plugins = set(self.obj.config["plugins"]["disabled"].split())
        plugins = self.plugin_loader.plugins_path  # All available plugins

        for plugin_name in plugins.keys():
            print(plugin_name)
            # Create a row for the plugin
            row_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 10)
            row_box.set_margin_start(10)
            row_box.set_margin_end(10)

            # Plugin name label
            plugin_label = Gtk.Label.new(plugin_name)
            plugin_label.set_hexpand(True)
            row_box.append(plugin_label)

            # Toggle switch for enabling/disabling the plugin
            switch = Gtk.Switch()
            is_plugin_enabled = (
                plugin_name not in disabled_plugins
            )  # Check if the plugin is enabled
            switch.set_active(is_plugin_enabled)

            # Connect the switch to the toggle handler
            switch.connect("state-set", self.on_switch_toggled, plugin_name)
            row_box.append(switch)

            # Add the row to the ListBox
            self.listbox.append(row_box)

    def on_switch_toggled(self, switch, state, plugin_name):
        """
        Handle toggling the switch to enable/disable a plugin.
        Args:
            switch (Gtk.Switch): The switch that was toggled.
            state (bool): The new state of the switch.
            plugin_name (str): The name of the plugin being toggled.
        """
        try:
            # Get the current disabled plugins as a list
            disabled_plugins = self.obj.config["plugins"]["disabled"].split()

            if state:
                # Enable the plugin
                self.plugin_loader.reload_plugin(plugin_name)
                self.logger.info(f"Enabled plugin: {plugin_name}")

                # Remove the plugin from the disabled list
                if plugin_name in disabled_plugins:
                    disabled_plugins.remove(plugin_name)
            else:
                # Disable the plugin
                self.plugin_loader.disable_plugin(plugin_name)
                self.logger.info(f"Disabled plugin: {plugin_name}")

                # Add the plugin to the disabled list
                if plugin_name not in disabled_plugins:
                    disabled_plugins.append(plugin_name)

            # Update the disabled string in the configuration
            self.obj.config["plugins"]["disabled"] = " ".join(disabled_plugins)

            # Save the updated configuration to the TOML file
            self.obj.save_config()

        except Exception as e:
            self.logger.error_handler.handle(
                error=e,
                message=f"Error toggling plugin '{plugin_name}': {e}",
                level="error",
            )

    def add_gesture_to_menu_button(self):
        """
        Add a gesture to the menu button to handle interactions.
        """
        # Create a click gesture for the menu button
        gesture = Gtk.GestureClick.new()
        gesture.connect("released", self.on_menu_button_clicked)
        gesture.set_button(1)  # Left mouse button
        self.menubutton_plugin_manager.add_controller(gesture)

    def on_menu_button_clicked(self, gesture, *_):
        """
        Handle the menu button click to toggle the popover.
        """
        if not self.popover_plugin_manager.is_visible():
            self.popover_plugin_manager.popup()
        else:
            self.popover_plugin_manager.popdown()

    def popover_is_open(self, *_):
        """
        Callback when the popover is opened.
        """
        pass

    def popover_is_closed(self, *_):
        """
        Callback when the popover is closed.
        """
        pass
