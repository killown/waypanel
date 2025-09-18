import os
import sys
from typing import Dict, Any, Optional, Union
import gi
import toml
from gi.repository import Adw, Gdk, Gtk
from gi.repository import Gtk4LayerShell as LayerShell
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


def set_layer_position_exclusive(window, size) -> None:
    """
    Sets the layer position exclusively for the given window.

    Note: If you encounter issues with the first execution of this function not working,
    it may be due to a delay in IPC with sock.watch immediately after the panel starts.
    Waiting longer before activating the scale for the first time should resolve this.
    Alternatively, executing the scale twice can also have the desired effect.

    The panel is hidden by default. This function makes it visible.
    If visibility doesn't take effect, the panel will remain hidden until IPC is ready.
    """
    # LayerShell.set_exclusive_zone(window, size)
    if window:
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
        # window.set_visible(True)


def unset_layer_position_exclusive(window) -> None:
    # LayerShell.set_exclusive_zone(window, 0)
    # print(LayerShell.get_exclusive_zone(window))
    if window:
        LayerShell.set_layer(window, LayerShell.Layer.BOTTOM)
        # window.set_visible(False)


def get_monitor_info() -> Dict[str, Dict[str, Any]]:
    """
    Retrieve information about the connected monitors.

    This function retrieves information about the connected monitors,
    such as their dimensions and names,
    and returns the information as a dictionary.

    Returns:
        Dict[str, Dict[str, Any]]: A dictionary where keys are monitor names
        and values are dictionaries containing monitor objects, width, and height.
        Example:
        {
            "HDMI-1": {
                "monitor": Gdk.Monitor,
                "width": 1920,
                "height": 1080
            },
            ...
        }
    """
    # Initialize GTK
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

    Args:
        monitor: Either a Gdk.Monitor object or a dictionary containing monitor info.
                Dictionary can be in format:
                - {"width": 1920, ...}
                - {"monitor": Gdk.Monitor, ...}
                - Nested structures (recursively searched)

    Returns:
        int: The monitor width in pixels

    Raises:
        ValueError: If no valid width can be determined from the input
    """
    # Case 1: Direct Gdk.Monitor object
    if isinstance(monitor, Gdk.Monitor):
        geom = Gdk.Rectangle()
        if hasattr(monitor, "get_geometry"):
            try:
                # New GTK: get_geometry() returns Gdk.Rectangle
                return monitor.get_geometry().width
            except TypeError:
                return geom.width

    # Case 2: Dictionary with direct width
    if isinstance(monitor, dict):
        if "width" in monitor and isinstance(monitor["width"], int):
            return monitor["width"]

        # Case 3: Nested dictionary structure
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


def load_panel_config() -> Dict[str, Any]:
    """Load and return the panel configuration."""
    with open(get_config_path()) as config_file:
        return toml.load(config_file)["panel"]


def get_target_monitor(
    config: Dict[str, Any], monitors: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Determine which monitor to use based on config and command line args."""
    # Check command line arguments first
    if len(sys.argv) > 1:
        monitor_name = sys.argv[1]
        return monitors.get(monitor_name)

    # Then check config file
    if "monitor" in config:
        monitor_name = config["monitor"]["name"]
        return monitors.get(monitor_name)

    # Default to first monitor ending with "-1"
    return next(
        (monitor for name, monitor in monitors.items() if name.endswith("-1")), None
    )


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

    # Set monitor if available
    if monitor and "monitor" in monitor:
        LayerShell.set_monitor(window, monitor["monitor"])

    # Set layer
    if layer == "TOP":
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
    elif layer == "BOTTOM":
        LayerShell.set_layer(window, LayerShell.Layer.BOTTOM)

    # Set anchors and exclusive zone
    if anchor in ["LEFT", "RIGHT", "TOP", "BOTTOM"]:
        edge = getattr(LayerShell.Edge, anchor)
        LayerShell.set_anchor(window, edge, True)
        if exclusive:
            LayerShell.auto_exclusive_zone_enable(window)

    # Handle special class styles
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

    # Create window
    window = Adw.Window(application=app)
    window.set_default_size(width, height)
    window.set_focus_on_click(False)

    # Get monitor and config information
    monitors = get_monitor_info()
    config = load_panel_config()
    monitor = get_target_monitor(config, monitors)

    # Configure layer shell properties
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
