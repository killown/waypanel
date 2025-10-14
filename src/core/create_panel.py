import os
import sys
from typing import Dict, Any, Optional, Union
import gi
import toml
from gi.repository import Adw, Gdk, Gtk  # pyright: ignore
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore
from wayfire import WayfireSocket

sock = None
if os.getenv("WAYFIRE_SOCKET"):
    sock = WayfireSocket()
if os.getenv("SWAYSOCK") and not os.getenv("WAYFIRE_SOCKET"):
    from pysway.ipc import SwayIPC

    sock = SwayIPC()
gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
PRIMARY_OUTPUT_NAME = None


def set_layer_position_exclusive(window) -> None:
    """
    Sets the layer position exclusively for the given window.
    """
    if window:
        LayerShell.set_layer(window, LayerShell.Layer.TOP)


def unset_layer_position_exclusive(window) -> None:
    if window:
        LayerShell.set_layer(window, LayerShell.Layer.BOTTOM)


def get_monitor_info() -> Dict[str, Dict[str, Any]]:
    """
    Retrieve information about the connected monitors.
    """
    Gtk.init()
    screen: Optional[Gdk.Display] = Gdk.Display.get_default()
    monitor_info: Dict[str, Dict[str, Any]] = {}
    if screen:
        monitors = screen.get_monitors()
        for monitor in monitors:
            monitor_width: int = int(monitor.get_geometry().width)
            monitor_height: int = int(monitor.get_geometry().height)
            name: str = monitor.props.connector
            monitor_info[name] = {
                "monitor": monitor,
                "width": monitor_width,
                "height": monitor_height,
            }
    return monitor_info


def get_monitor_width(monitor: Union[Gdk.Monitor, Dict[str, Any]]) -> int:
    """
    Get the width of a monitor from either a Gdk.Monitor object or a dictionary.
    """
    if isinstance(monitor, Gdk.Monitor):
        geom = Gdk.Rectangle()
        if hasattr(monitor, "get_geometry"):
            try:
                return monitor.get_geometry().width
            except TypeError:
                return geom.width
    if isinstance(monitor, dict):
        if "width" in monitor and isinstance(monitor["width"], int):
            return monitor["width"]
        for value in monitor.values():
            if isinstance(value, (dict, Gdk.Monitor)):
                try:
                    return get_monitor_width(value)
                except ValueError:
                    continue
    raise ValueError("Could not determine monitor width from input")


def get_config_path() -> str:
    """Get the path to the panel configuration file."""
    home = os.path.expanduser("~")
    config_path = os.path.join(home, ".config/waypanel")
    panel_config = os.path.join(config_path, "config.toml")
    if not os.path.exists(panel_config):
        full_path = os.path.abspath(__file__)
        directory_path = os.path.dirname(full_path)
        parent_directory_path = os.path.dirname(os.path.dirname(directory_path))
        panel_config = os.path.join(parent_directory_path, "config/panel.toml")
    return panel_config


def load_full_config() -> Dict[str, Any]:
    """Load and return the entire application configuration."""
    with open(get_config_path()) as config_file:
        return toml.load(config_file)


def get_target_monitor(
    config: Dict[str, Any], monitors: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Determine which monitor to use based on config and command line args."""
    if len(sys.argv) > 1:
        monitor_name = sys.argv[1]
        target = monitors.get(monitor_name)
        if target:
            return target
    monitor_name = config["org.waypanel.panel"]["primary_output"].get("name")
    target = monitors.get(monitor_name)
    if target:
        return target
    return next(iter(monitors.values()), None)


def setup_layer_shell(
    window: Adw.Window,
    anchor: str,
    layer: str,
    exclusive: bool,
    width: int,
    height: int,
    monitor: Optional[Dict[str, Any]],
    class_style: str,
) -> None:
    """Configure the GTK Layer Shell properties for the window."""
    LayerShell.init_for_window(window)
    LayerShell.set_namespace(window, "waypanel")
    if monitor and "monitor" in monitor:
        LayerShell.set_monitor(window, monitor["monitor"])
    layer = layer.upper()
    if layer in ("TOP", "LEFT", "RIGHT"):
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
    elif layer in ("BACKGROUND", "BOTTOM"):
        LayerShell.set_layer(window, LayerShell.Layer.BACKGROUND)
    if anchor in ["LEFT", "RIGHT", "TOP", "BOTTOM"]:
        edge = getattr(LayerShell.Edge, anchor)
        LayerShell.set_anchor(window, edge, True)
        if exclusive:
            LayerShell.auto_exclusive_zone_enable(window)
    if class_style == "TopBarBackground":
        monitor_width = get_monitor_width(monitor) if monitor else width
        window.set_default_size(monitor_width, height)
        LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 11)
    window.set_size_request(10, 10)
    window.add_css_class(class_style)


def CreatePanel(
    app: Adw.Application,
    anchor: str,
    layer: str,
    exclusive: bool,
    width: int,
    height: int,
    class_style: str,
) -> Adw.Window:
    """Create and configure a panel window using GTK Layer Shell."""
    window = Adw.Window(application=app)
    window.set_default_size(width, height)
    window.set_focus_on_click(False)
    config = load_full_config()
    monitors = get_monitor_info()
    monitor = get_target_monitor(config, monitors)
    setup_layer_shell(
        window=window,
        anchor=anchor,
        layer=layer,
        exclusive=exclusive,
        width=width,
        height=height,
        monitor=monitor,
        class_style=class_style,
    )
    return window
