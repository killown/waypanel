import gi
from gi.repository import Gtk, GLib

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


# Define the plugin's placement in the panel
def get_plugin_placement(panel_instance):
    position = "top-panel-right"  # Position: right side of the panel
    order = 5  # Order: determines the relative position among other plugins
    return position, order


# Initialize the plugin
def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return IconTimerPlugin(panel_instance)


# Plugin class
class IconTimerPlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.utils = self.obj.utils

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
            self.logger.error_handler.handle(
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
            self.logger.error_handler.handle(
                error=e,
                message="Error removing widget in IconTimerPlugin.",
                level="error",
            )
