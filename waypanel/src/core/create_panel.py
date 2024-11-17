import gi
import os
import toml
import sys
from wayfire import WayfireSocket 
sock = WayfireSocket()

gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gtk


def set_layer_position_exclusive(window, size):
    """
    Sets the layer position exclusively for the given window.

    Note: If you encounter issues with the first execution of this function not working,
    it may be due to a delay in IPC with sock.watch immediately after the panel starts.
    Waiting longer before activating the scale for the first time should resolve this.
    Alternatively, executing the scale twice can also have the desired effect.

    The panel is hidden by default. This function makes it visible.
    If visibility doesn't take effect, the panel will remain hidden until IPC is ready.
    """
    #LayerShell.set_exclusive_zone(window, size)
    if window:
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
        #window.set_visible(True)
    return


def unset_layer_position_exclusive(window):
    #LayerShell.set_exclusive_zone(window, 0)
    # print(LayerShell.get_exclusive_zone(window))
    if window:
        LayerShell.set_layer(window, LayerShell.Layer.BOTTOM)
        #window.set_visible(False)
    return


def get_monitor_info():
    """
    Retrieve information about the connected monitors.

    This function retrieves information about the connected monitors,
    such as their dimensions and names,
    and returns the information as a dictionary.

    Returns:
        dict: A dictionary containing information
        about the connected monitors.
    """
    # get default display and retrieve
    # information about the connected monitors
    # # Initialize GTK
    Gtk.init()

    screen = Gdk.Display.get_default()
    monitors = screen.get_monitors()
    monitor_info = {}
    for monitor in monitors:
        monitor_width = monitor.get_geometry().width
        monitor_height = monitor.get_geometry().height
        name = monitor.props.connector
        monitor_info[name] = {
            "monitor": monitor,
            "width": monitor_width,
            "height": monitor_height,
        }
    return monitor_info


def CreatePanel(app, anchor, layer, exclusive, width, height, class_style):
    window = Adw.Window(application=app)
    window.add_css_class(class_style)
    # lets try to set monitor info from Gdk, if not, get the panel default info instead
    monitor = get_monitor_info()
    gdk_monitor = None
    print(type(monitor))
    monitor_name = next((name for name in monitor if name.endswith('-1')), None)
    home = os.path.expanduser("~")
    config_path = os.path.join(home, ".config/waypanel")
    panel_config = os.path.join(config_path, "panel.toml")
    full_path = os.path.abspath(__file__)
    directory_path = os.path.dirname(full_path)
    parent_directory_path = os.path.dirname(directory_path)
    parent_directory_path = os.path.dirname(parent_directory_path)
    if not os.path.exists(panel_config):
        panel_config = os.path.join(parent_directory_path, "config/panel.toml")
    with open(panel_config) as panel_config:
        config = toml.load(panel_config)

    # Monitor dimensions to set the panel size
    if "monitor" in config:
        monitor_name = config["monitor"]["name"]

    argv = sys.argv
    if len(argv) > 1:
        argv = sys.argv[1]
        monitor_name = argv


    if monitor_name in monitor:
        monitor = monitor[monitor_name]
        gdk_monitor = monitor["monitor"]

    window.set_default_size(width, height)
    window.set_focus_on_click(False)
    LayerShell.init_for_window(window)
    LayerShell.set_namespace(window, "waypanel")
    #LayerShell.set_keyboard_mode(window, 0)


    if gdk_monitor is not None:
        LayerShell.set_monitor(window, gdk_monitor)

    if layer == "TOP":
        window.set_default_size(monitor["width"], height)
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
        window.set_size_request(10,10)

    if anchor == "LEFT":
        LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
        window.set_size_request(10,10)

        if exclusive:
            LayerShell.auto_exclusive_zone_enable(window)

    if anchor == "RIGHT":
        LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
        if exclusive:
            LayerShell.auto_exclusive_zone_enable(window)

    if anchor == "TOP":
        LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
        if exclusive:
            LayerShell.auto_exclusive_zone_enable(window)

    if anchor == "BOTTOM":
        LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
        window.set_size_request(10,10)
        if exclusive:
            LayerShell.auto_exclusive_zone_enable(window)

    # LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 0)
    # LayerShell.set_margin(window, LayerShell.Edge.TOP, 0)
    if class_style == "TopBarBackground":
        window.set_default_size(monitor["width"], height)
        LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 11)
        # LayerShell.set_margin(window, LayerShell.Edge.TOP, 11)

    if layer == "BOTTOM":
        LayerShell.set_layer(window, LayerShell.Layer.BOTTOM)

    return window
