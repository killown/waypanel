import gi
from gi.repository import Gtk, GLib

from src.plugins.core._base import BasePlugin

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True

# DEPS list is where you add required plugins to load before this example_icon_timer plugin loads,
# Adding DEPS isn't mandatory, but if top_panel doesn't load before example_icon_timer,
# example_icon_timer will fail too.
DEPS = ["top_panel"]


# Define the plugin's placement in the panel
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
    position = "top-panel-right"  # Position: right side of the panel
    order = 5  # Order: determines the relative position among other plugins
    return position, order


# Initialize the plugin
def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return IconTimerPlugin(panel_instance)


# Plugin class
class IconTimerPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)

        # Create the widget to append
        self.icon_widget = Gtk.Image.new_from_icon_name("system-run-symbolic")
        self.icon_widget.add_css_class("icon-timer-widget")

        # Append the widget to the panel
        self.appended_widget = self.append_widget()

        # Schedule the widget removal after 10 seconds
        GLib.timeout_add_seconds(10, self.remove_appended_widget)

    def append_widget(self):
        """
        Append the icon widget to the panel.
        Returns:
            Gtk.Widget: The appended widget.
        """
        try:
            # Return the widget to be appended by the plugin loader
            return self.icon_widget
        except Exception as e:
            self.log_error(
                error=e,
                message="Error appending widget in IconTimerPlugin.",
                level="error",
            )
            return None

    def remove_appended_widget(self):
        """
        Remove the appended widget from the panel after 10 seconds.
        """
        try:
            if self.utils.widget_exists(self.appended_widget):
                self.logger.info("Removing icon widget after 10 seconds.")
                self.utils.remove_widget(self.appended_widget)
            else:
                self.logger.warning("Icon widget does not exist. Skipping removal.")
        except Exception as e:
            self.log_error(
                error=e,
                message="Error removing widget in IconTimerPlugin.",
                level="error",
            )
