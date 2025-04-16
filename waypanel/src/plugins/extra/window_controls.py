import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
from wayfire.ipc import WayfireSocket
from ...core.utils import Utils

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def position():
    """Define the plugin's position and order."""
    position = "right"  # Can be "left", "right", or "center"
    order = 5  # Middle priority
    return position, order


def initialize_plugin(obj, app):
    """Initialize the window controls plugin."""
    if ENABLE_PLUGIN:
        return WindowControlsPlugin(obj, app)


class WindowControlsPlugin:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app
        self.sock = WayfireSocket()
        self.utils = Utils()

        # Store the last focused toplevel view as an instance variable
        self.last_toplevel_focused_view = None

        # Initialize buttons container
        self.cf_box = Gtk.Box()

        # Create buttons
        self.maximize_button = self.create_control_button(
            "window-maximize-symbolic",
            "maximize-button",
            self.maximize_last_focused_view,
        )

        self.close_button = self.create_control_button(
            "window-close-symbolic", "close-button", self.close_last_focused_view
        )

        self.minimize_button = self.create_control_button(
            "window-minimize-symbolic", "minimize-button", self.minimize_view
        )

        # Add buttons to container
        self.cf_box.append(self.minimize_button)
        self.cf_box.append(self.maximize_button)
        self.cf_box.append(self.close_button)

        # Add CSS class
        self.cf_box.add_css_class("cf_box")

        # Add container to panel
        if hasattr(self.obj, "top_panel_box_for_buttons"):
            self.obj.top_panel_box_for_buttons.append(self.cf_box)

        # Subscribe to the 'view-focused' event
        if "event_manager" in obj.plugins:
            event_manager = obj.plugins["event_manager"]
            event_manager.subscribe_to_event("view-focused", self.on_view_focused)

    def create_control_button(self, icon_name, css_class, callback):
        button = self.utils.create_button(
            icon_name, None, css_class, None, use_function=callback
        )
        return button

    def on_view_focused(self, event_message):
        """
        Handle when a view gains focus.

        Args:
            event_message (dict): The event message containing view details.
        """
        try:
            if "view" in event_message and event_message["view"] is not None:
                view = event_message["view"]
                if view.get("role") == "toplevel":
                    self.last_toplevel_focused_view = view
                    print(f"Last focused toplevel view updated: {view['id']}")
        except Exception as e:
            print(f"Error handling 'view-focused' event: {e}")

    def maximize_last_focused_view(self, *_):
        if self.last_toplevel_focused_view:
            print(self.last_toplevel_focused_view)
            self.sock.assign_slot(self.last_toplevel_focused_view["id"], "slot_c")

    def close_last_focused_view(self, *_):
        print("Attempting to close last focused view...")
        if (
            self.last_toplevel_focused_view
            and self.last_toplevel_focused_view.get("role") == "toplevel"
        ):
            print(f"Closing view with ID: {self.last_toplevel_focused_view['id']}")
            self.sock.close_view(self.last_toplevel_focused_view["id"])
        else:
            print("No valid toplevel view to close.")

    def minimize_view(self, *_):
        if self.last_toplevel_focused_view:
            self.sock.set_view_minimized(self.last_toplevel_focused_view["id"], True)

    # # Hide desktop-environment views with unknown type
    # for view in self.sock.list_views():
    # if view["role"] == "desktop-environment" and view["type"] == "unknown":
    # self.hide_view_instead_closing(view, ignore_toplevel=True)

    # def hide_view_instead_closing(self, view, ignore_toplevel=None):
    #     if view:
    #         if view["role"] != "toplevel" and ignore_toplevel is None:
    #             return
    #         button = Gtk.Button()
    #         button.connect("clicked", lambda widget: self.on_hidden_view(widget, view))
    #         self.update_widget(self.obj.top_panel_box_center.append, button)
    #         self.utils.handle_icon_for_button(view, button)
    #         self.sock.hide_view(view["id"])
    #
    # def on_hidden_view(self, widget, view):
    #     id = view["id"]
    #     if id in self.wf_utils.list_ids():
    #         self.sock.unhide_view(id)
    #         # ***Warning*** this was freezing the panel
    #         # set focus will return an Exception in case the view is not toplevel
    #         GLib.idle_add(lambda *_: self.utils.focus_view_when_ready(view))
    #         if self.utils.widget_exists(widget):
    #             self.update_widget(self.top_panel_box_center.remove, widget)
