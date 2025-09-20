import gi

from src.plugins.core._base import BasePlugin

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
from subprocess import run
import pulsectl

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    """Initialize the volume scroll plugin."""
    if ENABLE_PLUGIN:
        return VolumeScrollPlugin(panel_instance)


class VolumeScrollPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        """Initialize the plugin."""
        self.widget = None
        self.hide_timeout_id = None
        self.slider = None  # Initialize slider as None
        self.icon = None  # Initialize icon as None
        self.label = None  # Initialize label as None
        self.max_volume = 150  # Default max volume (will be updated dynamically)

        # Fetch the actual maximum volume from PulseAudio
        self.update_max_volume()

        # Set up the scroll event listener
        self.setup_scroll_event()

    def update_max_volume(self):
        """Fetch the maximum volume supported by the system."""
        try:
            with pulsectl.Pulse("volume-increaser") as pulse:
                for sink in pulse.sink_list():
                    if "RUNNING" in str(sink.state).upper():
                        # Calculate the maximum volume percentage
                        self.max_volume = round(
                            sink.volume.values[0]
                            * 100
                            * sink.base_volume
                            / sink.volume.value_flat
                        )
                        break
        except Exception as e:
            self.log_error(f"Error fetching maximum volume: {e}")
            self.max_volume = 150  # Fallback to default max volume

    def setup_scroll_event(self):
        """Set up the scroll event listener."""
        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        scroll_controller.connect("scroll", self.on_scroll)
        self.obj.top_panel_box_full.add_controller(scroll_controller)

    def on_scroll(self, controller, dx, dy):
        """Handle scroll events to adjust the volume."""
        try:
            adjustment = "-8%" if dy > 0 else "+8%"
            self.adjust_volume(adjustment)
        except Exception as e:
            self.log_error(f"Error handling scroll event: {e}")

    def adjust_volume(self, adjustment):
        """Adjust the volume using the `pactl` command."""
        try:
            # Adjust the volume using `pactl`
            cmd = f"pactl -- set-sink-volume @DEFAULT_SINK@ {adjustment}"
            run(cmd.split(), check=True)

            # Get the current volume level
            current_volume = self.get_current_volume()

            # Update the floating volume widget
            self.set_volume(current_volume)
            self.show_widget()
        except Exception as e:
            self.log_error(f"Error adjusting volume: {e}")

    def get_current_volume(self):
        """Get the current volume level using `pulsectl`."""
        try:
            with pulsectl.Pulse("volume-increaser") as pulse:
                for sink in pulse.sink_list():
                    if "RUNNING" in str(sink.state).upper():
                        # Calculate the volume percentage and round it to the nearest whole number
                        volume = round(sink.volume.values[0] * 100)
                        return min(volume, self.max_volume)  # Clamp to max volume
            return 0  # Default to 0 if no active sink is found
        except Exception as e:
            self.log_error(f"Error fetching current volume: {e}")
            return 0

    def create_floating_widget(self):
        """Create the floating volume widget."""
        self.widget = Gtk.Window()
        self.layer_shell.init_for_window(self.widget)
        self.layer_shell.set_layer(self.widget, self.layer_shell.Layer.TOP)
        self.layer_shell.set_anchor(self.widget, self.layer_shell.Edge.BOTTOM, True)
        self.layer_shell.set_anchor(self.widget, self.layer_shell.Edge.RIGHT, True)
        self.layer_shell.set_margin(self.widget, self.layer_shell.Edge.BOTTOM, 50)
        self.layer_shell.set_margin(self.widget, self.layer_shell.Edge.RIGHT, 50)

        # Create the content of the widget
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        # Icon
        self.icon = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
        self.icon.set_pixel_size(48)
        vbox.append(self.icon)

        # Label
        self.label = Gtk.Label(label="100%")
        vbox.append(self.label)

        # Slider
        self.slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, self.max_volume, 1
        )
        self.slider.set_value(100)
        self.slider.connect("value-changed", self.on_slider_changed)
        vbox.append(self.slider)

        self.widget.set_child(vbox)
        self.widget.set_default_size(200, 100)
        self.icon.add_css_class("floating-volume-icon")
        self.slider.add_css_class("floating-volume-slider")
        self.label.add_css_class("floating-volume-label")
        vbox.add_css_class("floating-volume-box")
        self.widget.add_css_class("floating-volume-widget")

    def show_widget(self):
        """Show the floating widget."""
        if not self.widget:
            self.create_floating_widget()  # Ensure the widget is created
        self.widget.present()
        self.widget.set_opacity(1.0)

        # Cancel any existing hide timeout
        if self.hide_timeout_id:
            GLib.source_remove(self.hide_timeout_id)

        # Schedule the widget to hide after 3 seconds
        self.hide_timeout_id = GLib.timeout_add_seconds(3, self.hide_widget)

    def hide_widget(self):
        """Hide the floating widget."""
        if self.widget:
            self.widget.set_opacity(0.0)
            self.widget.hide()
        self.hide_timeout_id = None
        return False  # Stop the timeout

    def set_volume(self, volume):
        """Set the volume level and update the widget."""
        volume = min(volume, self.max_volume)  # Clamp to max volume
        if self.slider:
            self.slider.set_value(volume)
        if self.label:
            self.label.set_text(f"{int(volume)}%")

        # Update the icon based on the volume level
        if self.icon:
            if volume == 0:
                self.icon.set_from_icon_name("audio-volume-muted-symbolic")
            elif volume < 33:
                self.icon.set_from_icon_name("audio-volume-low-symbolic")
            elif volume < 66:
                self.icon.set_from_icon_name("audio-volume-medium-symbolic")
            else:
                self.icon.set_from_icon_name("audio-volume-high-symbolic")

    def on_slider_changed(self, *__):
        """Handle slider value changes."""
        if self.slider:
            volume = self.slider.get_value()
            self.adjust_volume(f"{int(volume)}%")
            self.set_volume(volume)

    def about(self):
        """
        A plugin that allows volume control via the scroll wheel and
        displays a floating on-screen display (OSD).
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin provides a dynamic and temporary visual feedback
        for volume changes triggered by the scroll wheel.

        Its core logic is centered on **event-driven volume control and
        dynamic UI display**:

        1.  **Event Handling**: It attaches a scroll event controller to
            the panel. When a user scrolls, it triggers the volume
            adjustment logic.
        2.  **System Volume Control**: It uses command-line tools like
            `pactl` to increase or decrease the system's volume in
            response to scroll events. It uses `pulsectl` to retrieve the
            current volume level.
        3.  **Dynamic UI**: A temporary, floating `Gtk.Window` is created
            to serve as an on-screen display (OSD). This widget contains a
            volume slider, a label with the volume percentage, and an
            icon that changes to reflect the volume level (e.g., mute,
            low, high).
        4.  **Widget Management**: The floating widget automatically
            appears when the volume is adjusted and disappears after a
            short timeout period, ensuring it does not permanently clutter
            the screen.
        """
        return self.code_explanation.__doc__
