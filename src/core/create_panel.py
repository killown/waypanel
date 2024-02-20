import gi
import os
import toml

gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell

gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk


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
    monitor_name = None
    home = os.path.expanduser("~")
    config_path = os.path.join(home, ".config/waypanel")
    panel_config = os.path.join(config_path, "panel.toml")
    with open(panel_config) as panel_config:
        config = toml.load(panel_config)

    # Monitor dimensions to set the panel size
    if "monitor" in config:
        monitor_name = config["monitor"]["name"]

    if monitor_name in monitor:
        monitor = monitor[monitor_name]
        gdk_monitor = monitor["monitor"]

    window.set_default_size(width, height)
    LayerShell.init_for_window(window)

    if gdk_monitor is not None:
        LayerShell.set_monitor(window, gdk_monitor)

    if layer == "TOP":
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
        LayerShell.auto_exclusive_zone_enable(window)

    if anchor == "LEFT":
        LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
        # LayerShell.auto_exclusive_zone_enable(window)

    if anchor == "RIGHT":
        LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
    if anchor == "TOP":
        LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
    if anchor == "BOTTOM":
        LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
        # LayerShell.auto_exclusive_zone_enable(window)

    LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 0)
    LayerShell.set_margin(window, LayerShell.Edge.TOP, 0)
    if class_style == "TopBarBackground":
        LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 11)
        LayerShell.set_margin(window, LayerShell.Edge.TOP, 11)

    if layer == "BOTTOM":
        LayerShell.set_layer(window, LayerShell.Layer.BOTTOM)

    return window
