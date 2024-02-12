import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell
from gi.repository import Adw


def CreatePanel(app, anchor, layer, exclusive, width, height, class_style):
    window = Adw.Window(application=app)
    window.set_default_size(width, height)
    window.add_css_class(class_style)

    LayerShell.init_for_window(window)
    if anchor == "LEFT":
        LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
    if anchor == "RIGHT":
        LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
    if anchor == "TOP":
        LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
    if anchor == "BOTTOM":
        LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
    LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 0)
    LayerShell.set_margin(window, LayerShell.Edge.TOP, 0)
    if class_style == "TopBarBackground":
        LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 11)
        LayerShell.set_margin(window, LayerShell.Edge.TOP, 11)

    if layer == "BOTTOM":
        LayerShell.set_layer(window, LayerShell.Layer.BOTTOM)
    if layer == "TOP":
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
    if exclusive:
        LayerShell.auto_exclusive_zone_enable(window)

    return window
