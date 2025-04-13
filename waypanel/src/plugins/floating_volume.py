import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, GLib, Gtk4LayerShell as LayerShell
from ..core.utils import Utils

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


class FloatingVolumePlugin:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app
        self.utils = Utils()
        self.widget = None
        self.hide_timeout_id = None

    def create_floating_widget(self):
        """Create the floating volume widget."""
        self.widget = Gtk.Window()
        LayerShell.init_for_window(self.widget)
        LayerShell.set_layer(self.widget, LayerShell.Layer.TOP)
        LayerShell.set_anchor(self.widget, LayerShell.Edge.BOTTOM, True)
        LayerShell.set_anchor(self.widget, LayerShell.Edge.RIGHT, True)
        LayerShell.set_margin(self.widget, LayerShell.Edge.BOTTOM, 50)
        LayerShell.set_margin(self.widget, LayerShell.Edge.RIGHT, 50)

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
        self.slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.slider.set_value(100)
        self.slider.connect("value-changed", self.on_slider_changed)
        vbox.append(self.slider)

        self.widget.set_child(vbox)
        self.widget.set_default_size(200, 100)

    def show_widget(self):
        """Show the floating widget."""
        if not self.widget:
            self.create_floating_widget()
        self.widget.present()
        self.widget.set_opacity(1.0)

        # Cancel any existing hide timeout
        if self.hide_timeout_id:
            GLib.source_remove(self.hide_timeout_id)

        # Schedule the widget to hide after 3 seconds
        self.hide_timeout_id = GLib.timeout_add_seconds(1, self.hide_widget)

    def hide_widget(self):
        """Hide the floating widget."""
        if self.widget:
            self.widget.set_opacity(0.0)
            self.widget.hide()
        self.hide_timeout_id = None
        return False  # Stop the timeout

    def set_volume(self, volume):
        """Set the volume level and update the widget."""
        volume = max(0, min(100, volume))
        if self.slider:
            self.slider.set_value(volume)
        if self.label:
            self.label.set_text(f"{int(volume)}%")

        # Update the icon based on the volume level
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
        volume = self.slider.get_value()
        self.set_volume(volume)


def initialize_plugin(obj, app):
    """Initialize the floating volume plugin."""
    # Attach the plugin instance to the main application object
    if ENABLE_PLUGIN:
        obj.floating_volume_plugin = FloatingVolumePlugin(obj, app)


def position():
    """Define the plugin's position and order."""
    return "right", 10  # Position: right, Order: 10
