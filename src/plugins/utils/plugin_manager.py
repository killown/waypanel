def get_plugin_metadata(_):
    about = """
            A graphical user interface (GUI) plugin that allows users to view,
            enable, and disable other Waypanel plugins dynamically without
            restarting the panel. It organizes plugins by their folder/category
            using a Gtk.Stack and Gtk.StackSwitcher.
            """
    return {
        "id": "org.waypanel.plugin.plugin_manager",
        "name": "Plugin Manager",
        "version": "1.0.0",
        "enabled": False,
        "container": "top-panel-systray",
        "index": 99,
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    """
    The factory function for the PluginManagerPlugin class.
    ALL necessary imports, including standard library modules and framework components,
    are deferred here to ensure fast top-level loading as required by the plugin loader.
    """
    import os
    from src.plugins.core._base import BasePlugin
    from gi.repository import Gtk  # pyright: ignore
    from typing import Dict, Any, List, Optional, Tuple

    class PluginManagerPlugin(BasePlugin):
        """
        Manages the configuration state of other plugins through a graphical
        popover interface accessible via the system tray.
        """

        def __init__(self, panel_instance: Any):
            """
            Initializes the plugin state variables. Widget creation and setup
            are deferred to the on_start asynchronous lifecycle method.
            Args:
                panel_instance: The main panel instance.
            """
            super().__init__(panel_instance)
            self.menubutton_plugin_manager: Optional[Gtk.MenuButton] = None
            self.popover_plugin_manager: Optional[Gtk.Popover] = None
            self.stack: Optional[Gtk.Stack] = None
            self.stack_switcher: Optional[Gtk.StackSwitcher] = None
            self.main_widget: Optional[Tuple[Gtk.Widget, str]] = None

        async def on_start(self) -> None:
            """
            The primary activation method. Initializes all GUI components,
            populates the plugin list, and registers the main widget with the panel.
            """
            self.logger.info("PluginManagerPlugin starting up...")
            self.menubutton_plugin_manager = Gtk.MenuButton.new()
            self.menubutton_plugin_manager.set_icon_name("preferences-plugin-symbolic")
            self.stack = Gtk.Stack.new()
            self.stack_switcher = Gtk.StackSwitcher.new()
            self.stack_switcher.set_stack(self.stack)
            self.create_popover_plugin_manager()
            self.add_gesture_to_menu_button()
            if self.menubutton_plugin_manager:
                self.main_widget = (self.menubutton_plugin_manager, "append")

        async def on_stop(self) -> None:
            """
            The primary deactivation method. Destroys the main UI component to
            release resources.
            """
            self.logger.info("PluginManagerPlugin stopping. Destroying UI.")
            if self.menubutton_plugin_manager:
                self.menubutton_plugin_manager.unparent()
            self.popover_plugin_manager = None
            self.stack = None
            self.stack_switcher = None
            self.main_widget = None  # pyright: ignore

        def create_popover_plugin_manager(self) -> None:
            """Creates and configures the popover for managing plugins."""
            if (
                not self.menubutton_plugin_manager
                or not self.stack
                or not self.stack_switcher
            ):
                self.logger.error("UI components not initialized in on_start.")
                return
            self.popover_plugin_manager = Gtk.Popover.new()
            self.popover_plugin_manager.set_has_arrow(False)
            self.menubutton_plugin_manager.set_popover(self.popover_plugin_manager)
            hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(10)
            hbox.set_margin_bottom(10)
            hbox.set_margin_start(10)
            hbox.set_margin_end(10)
            hbox.set_size_request(350, 200)
            self.stack_switcher.set_orientation(Gtk.Orientation.VERTICAL)
            self.stack_switcher.set_halign(Gtk.Align.START)
            self.stack_switcher.set_valign(Gtk.Align.FILL)
            hbox.append(self.stack_switcher)
            self.populate_stack_with_plugins()
            hbox.append(self.stack)
            self.popover_plugin_manager.set_child(hbox)
            self.popover_plugin_manager.connect("closed", self.popover_is_closed)

        def on_switch_toggled(
            self, switch: Gtk.Switch, state: bool, plugin_name: str
        ) -> bool:
            """
            Handles toggling the switch to enable/disable a plugin and updates
            the configuration file.
            Args:
                switch: The Gtk.Switch widget.
                state: The new state of the switch (True for On/Enabled).
                plugin_name: The internal name of the plugin being toggled.
            Returns:
                False to stop other handlers from running (GTK convention for state-set).
            """
            try:
                disabled_list_str = self.config.get("plugins", {}).get("disabled", "")
                disabled_plugins = set(disabled_list_str.split())
                if state:
                    if plugin_name in disabled_plugins:
                        disabled_plugins.remove(plugin_name)
                    self.plugin_loader.reload_plugin(plugin_name)
                    self.logger.info(f"Enabled plugin: {plugin_name}")
                else:
                    if plugin_name not in disabled_plugins:
                        disabled_plugins.add(plugin_name)
                    self.plugin_loader.disable_plugin(plugin_name)
                    self.logger.info(f"Disabled plugin: {plugin_name}")
                self.config["plugins"]["disabled"] = " ".join(  # pyright: ignore
                    sorted(list(disabled_plugins))
                )
                self.obj.save_config()
            except Exception as e:
                self.logger.error(
                    message=f"Error toggling plugin '{plugin_name}': {e}",
                )
            return False

        def populate_stack_with_plugins(self) -> None:
            """Groups plugins by folder and populates the Gtk.Stack and Gtk.StackSwitcher."""
            if not self.stack:
                self.logger.error("Gtk.Stack not initialized.")
                return
            plugins: Dict[str, str] = self.plugin_loader.plugins_path
            disabled_list_str: str = self.config.get("plugins", {}).get("disabled", "")  # pyright: ignore
            disabled_plugins: List[str] = disabled_list_str.split()
            excluded_folders: List[str] = ["clipboard"]
            plugin_folders: Dict[str, List[str]] = {}
            for plugin_name, plugin_path in plugins.items():
                if plugin_name.startswith("_"):
                    continue
                folder: str = os.path.basename(os.path.dirname(plugin_path))
                if folder not in plugin_folders:
                    plugin_folders[folder] = []
                plugin_folders[folder].append(plugin_name)
            for folder, plugin_names in plugin_folders.items():
                if folder in excluded_folders:
                    continue
                listbox = Gtk.ListBox.new()
                listbox.set_selection_mode(Gtk.SelectionMode.NONE)
                for plugin_name in sorted(plugin_names):
                    row_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 10)
                    row_box.set_margin_start(10)
                    row_box.set_margin_end(10)
                    name: str = plugin_name.replace("_", " ").capitalize()
                    plugin_label = Gtk.Label.new(name)
                    plugin_label.set_hexpand(True)
                    plugin_label.set_halign(Gtk.Align.START)
                    row_box.append(plugin_label)
                    switch = Gtk.Switch.new()
                    is_plugin_enabled: bool = plugin_name not in disabled_plugins
                    switch.set_active(is_plugin_enabled)
                    switch.connect("state-set", self.on_switch_toggled, plugin_name)
                    row_box.append(switch)
                    row = Gtk.ListBoxRow.new()
                    row.set_child(row_box)
                    listbox.append(row)
                scrolled_window = Gtk.ScrolledWindow.new()
                scrolled_window.set_child(listbox)
                scrolled_window.set_size_request(300, 300)
                self.stack.add_titled(scrolled_window, folder, folder.capitalize())

        def add_gesture_to_menu_button(self) -> None:
            """
            Adds a click gesture to the menu button to handle toggling the popover.
            """
            if not self.menubutton_plugin_manager:
                return
            gesture = Gtk.GestureClick.new()
            gesture.connect("released", self.on_menu_button_clicked)
            gesture.set_button(1)
            self.menubutton_plugin_manager.add_controller(gesture)

        def on_menu_button_clicked(self, gesture: Gtk.GestureClick, *args: Any) -> None:
            """
            Handles the menu button click to manually toggle the popover visibility.
            This is used for the Gtk.GestureClick binding.
            """
            if not self.popover_plugin_manager:
                return
            if not self.popover_plugin_manager.is_visible():
                self.popover_plugin_manager.popup()
            else:
                self.popover_plugin_manager.popdown()

        def popover_is_closed(self, *args: Any) -> None:
            """Callback when the popover is closed (Placeholder for future logic)."""
            pass

    return PluginManagerPlugin
