import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
from wayfire.ipc import WayfireSocket
from ...core.utils import Utils

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "after-systray"
    order = 1
    priority = 1
    return position, order, priority


def initialize_plugin(panel_instance):
    """Initialize the window controls plugin."""
    if ENABLE_PLUGIN:
        return WindowControlsPlugin(panel_instance)


class WindowControlsPlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
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

        # Subscribe to the 'view-focused' event

        def run_once():
            if "event_manager" in self.obj.plugin_loader.plugins:
                event_manager = self.obj.plugin_loader.plugins["event_manager"]
                event_manager.subscribe_to_event(
                    "view-focused",
                    self.on_view_focused,
                    plugin_name="window_controls",
                )
                self.obj.logger.info(
                    "Window Constrols plugin subscribed to view-focused event!"
                )
                return False
            else:
                self.obj.logger.info(
                    "Window Constrols plugin waiting for event_manager to be ready"
                )
                return True

        GLib.timeout_add_seconds(1, run_once)

    def append_widget(self):
        return self.cf_box

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
        except Exception as e:
            print(f"Error handling 'view-focused' event: {e}")

    def maximize_last_focused_view(self, *_):
        if self.last_toplevel_focused_view:
            self.sock.assign_slot(self.last_toplevel_focused_view["id"], "slot_c")

    def close_last_focused_view(self, *_):
        if (
            self.last_toplevel_focused_view
            and self.last_toplevel_focused_view.get("role") == "toplevel"
        ):
            self.obj.logger.info(
                f"Closing view with ID: {self.last_toplevel_focused_view['id']}"
            )
            self.sock.close_view(self.last_toplevel_focused_view["id"])
        else:
            self.obj.logger.info("No valid toplevel view to close.")

        print(self.obj.plugin_loader.plugins)

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
