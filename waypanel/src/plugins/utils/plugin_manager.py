# Import necessary modules
import os
from src.plugins.core._base import BasePlugin
from gi.repository import Gtk

# Set to True to enable the plugin
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


# Define the plugin's placement in the panel
def get_plugin_placement(panel_instance):
    position = "top-panel-systray"  # Position: left side of the panel
    order = 99  # Order: low priority (appears at the end)
    return position, order


# Initialize the plugin
def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        instance = PluginManagerPlugin(panel_instance)
        instance.set_main_widget()
        return instance


# Plugin class
class PluginManagerPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        # Create the main button to open the popover
        self.menubutton_plugin_manager = Gtk.MenuButton()
        self.menubutton_plugin_manager.set_icon_name(
            "preferences-plugin-symbolic"
        )  # Default icon
        self.stack = Gtk.Stack()  # Create a stack for grouping plugins
        self.stack_switcher = Gtk.StackSwitcher()  # Create a stack switcher
        self.stack_switcher.set_stack(self.stack)

        # Create the popover content
        self.create_popover_plugin_manager()

        # Add gesture to handle interactions
        self.add_gesture_to_menu_button()

    def set_main_widget(self):
        self.main_widget = (self.menubutton_plugin_manager, "append")

    def create_popover_plugin_manager(self):
        """Create and configure the popover for managing plugins."""
        # Create the popover
        self.popover_plugin_manager = Gtk.Popover.new()
        self.popover_plugin_manager.set_has_arrow(False)

        # Create a horizontal box to hold the vertical tabs and the stack content
        hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_margin_top(10)
        hbox.set_margin_bottom(10)
        hbox.set_margin_start(10)
        hbox.set_margin_end(10)
        hbox.set_size_request(350, 200)

        # Create a vertical stack switcher (tabs on the left)
        self.stack_switcher = Gtk.StackSwitcher()
        self.stack_switcher.set_stack(self.stack)
        self.stack_switcher.set_orientation(
            Gtk.Orientation.VERTICAL
        )  # Set vertical orientation
        self.stack_switcher.set_halign(Gtk.Align.START)  # Align to the left
        self.stack_switcher.set_valign(
            Gtk.Align.FILL
        )  # Fill the height of the container

        # Add the stack switcher to the horizontal box
        hbox.append(self.stack_switcher)

        # Populate the stack with plugins grouped by folder
        self.populate_stack_with_plugins()

        # Add the stack to the horizontal box
        hbox.append(self.stack)

        # Set the horizontal box as the child of the popover
        self.popover_plugin_manager.set_child(hbox)

        # Connect signals
        self.popover_plugin_manager.connect("closed", self.popover_is_closed)
        self.menubutton_plugin_manager.set_popover(self.popover_plugin_manager)

    def on_switch_toggled(self, switch, state, plugin_name):
        """Handle toggling the switch to enable/disable a plugin."""
        try:
            # Load the disabled plugins as a list (split by spaces)
            disabled_plugins = (
                self.config.get("plugins", {}).get("disabled", "").split()
            )

            if state:
                # Add the plugin to the disabled list
                # Enable the plugin: Remove it from the disabled list
                self.plugin_loader.reload_plugin(plugin_name)
                self.logger.info(f"Enabled plugin: {plugin_name}")
                if plugin_name in disabled_plugins:
                    disabled_plugins.remove(plugin_name)
            else:
                self.plugin_loader.disable_plugin(plugin_name)
                self.logger.info(f"Disabled plugin: {plugin_name}")
                # Disable the plugin: Add it to the disabled list
                if plugin_name not in disabled_plugins:
                    disabled_plugins.append(plugin_name)

            # Update the configuration with the modified list
            self.config["plugins"]["disabled"] = " ".join(
                disabled_plugins
            )  # Convert back to string
            self.obj.save_config()  # Save the updated configuration

        except Exception as e:
            self.log_error(
                message=f"Error toggling plugin '{plugin_name}': {e}",
            )

    def populate_stack_with_plugins(self):
        """Group plugins by folder and populate the stack."""
        plugins = self.plugin_loader.plugins_path  # All available plugins
        disabled_plugins = self.config.get("plugins", {}).get("disabled", [])
        # FIXME: need a better way to handle plugin folders
        excluded_folders = ["clipboard"]
        # Temporary dictionary to group plugins by folder
        plugin_folders = {}

        # Group plugins by folder
        for plugin_name, plugin_path in plugins.items():
            if plugin_name.startswith("_"):
                continue

            # Determine the folder (e.g., essential, experimental)
            folder = os.path.basename(os.path.dirname(plugin_path))
            if folder not in plugin_folders:
                plugin_folders[folder] = []

            plugin_folders[folder].append(plugin_name)

        # Update self.plugin_loader.plugins_path with the grouped plugins
        self.plugin_loader.plugins_path.update(plugin_folders)

        # Create a stack page for each folder
        for folder, plugin_names in plugin_folders.items():
            # Create a ListBox for the folder
            listbox = Gtk.ListBox()
            listbox.set_selection_mode(Gtk.SelectionMode.NONE)

            if folder in excluded_folders:
                continue

            for plugin_name in sorted(plugin_names):
                # Create a row for the plugin
                row_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 10)
                row_box.set_margin_start(10)
                row_box.set_margin_end(10)

                # Plugin name label
                name = plugin_name.replace("_", " ").capitalize()
                plugin_label = Gtk.Label.new(name)
                plugin_label.set_hexpand(True)
                plugin_label.set_halign(Gtk.Align.START)
                row_box.append(plugin_label)

                # Toggle switch for enabling/disabling the plugin
                switch = Gtk.Switch()
                is_plugin_enabled = plugin_name not in disabled_plugins
                switch.set_active(is_plugin_enabled)
                switch.connect("state-set", self.on_switch_toggled, plugin_name)
                row_box.append(switch)

                # Add the row to the ListBox
                listbox.append(row_box)

            # Add the ListBox to a ScrolledWindow
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_child(listbox)
            scrolled_window.set_size_request(300, 300)

            # Add the ScrolledWindow to the stack
            self.stack.add_titled(scrolled_window, folder, folder.capitalize())

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
