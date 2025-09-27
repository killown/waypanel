import gi
from gi.repository import Gtk  # pyright: ignore
from src.plugins.core.event_handler_decorator import subscribe_to_event
from src.plugins.core._base import BasePlugin

gi.require_version("Gtk", "4.0")
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-after-systray"
    order = 1
    priority = 1
    return position, order, priority


def initialize_plugin(panel_instance):
    """Initialize the window controls plugin."""
    if ENABLE_PLUGIN:
        return WindowControlsPlugin(panel_instance)


class WindowControlsPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.last_toplevel_focused_view = None
        self.cf_box = Gtk.Box()
        self.main_widget = (self.cf_box, "append")
        self.maximize_button = self.create_control_button(
            "window-maximize-symbolic",
            "window-controls-maximize-button",
            self.maximize_last_focused_view,
        )
        self.close_button = self.create_control_button(
            "window-close-symbolic",
            "window-controls-close-button",
            self.close_last_focused_view,
        )
        self.minimize_button = self.create_control_button(
            "window-minimize-symbolic",
            "window-controls-minimize-button",
            self.minimize_view,
        )
        self.cf_box.append(self.minimize_button)
        self.cf_box.append(self.maximize_button)
        self.cf_box.append(self.close_button)
        self.gtk_helper.add_cursor_effect(self.cf_box)
        self.cf_box.add_css_class("window-controls-box")

    def create_control_button(self, icon_name, css_class, callback):
        button = self.gtk_helper.create_button(
            icon_name, None, css_class, None, use_function=callback
        )
        return button

    @subscribe_to_event("view-focused")
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
            self.logger.error(f"Error handling 'view-focused' event: {e}")

    def maximize_last_focused_view(self, *_):
        if self.last_toplevel_focused_view:
            self.ipc.assign_slot(self.last_toplevel_focused_view["id"], "slot_c")

    def close_last_focused_view(self, *_):
        if (
            self.last_toplevel_focused_view
            and self.last_toplevel_focused_view.get("role") == "toplevel"
        ):
            self.logger.info(
                f"Closing view with ID: {self.last_toplevel_focused_view['id']}"
            )
            self.ipc.close_view(self.last_toplevel_focused_view["id"])
        else:
            self.logger.info("No valid toplevel view to close.")

    def minimize_view(self, *_):
        if self.last_toplevel_focused_view:
            self.ipc.set_view_minimized(self.last_toplevel_focused_view["id"], True)

    def about(self):
        """
        A system dashboard for quick access to system actions,
        power management, and settings.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin creates a popover-based user interface for managing
        system-level actions. It provides a single access point for
        common tasks such as logging out, shutting down, or accessing
        settings.
        Its core logic is centered on **dynamic UI generation and
        system command execution**:
        1.  **UI Generation**: It creates a popover with a grid of buttons.
            Each button represents a system action, and the plugin
            dynamically selects the most suitable icon for each.
        2.  **System Command Execution**: For each button, it executes a
            corresponding system command (e.g., `reboot`, `shutdown`)
            using `subprocess.Popen`, allowing it to interact with the
            underlying operating system.
        3.  **External Tool Integration**: It checks for an external
            application (`waypanel-settings`) and launches it if available,
            providing graceful error handling if the dependency is not met.
        4.  **Session Management**: It includes actions specifically for
            managing the panel's session, such as exiting and restarting
            the panel itself.
        """
        return self.code_explanation.__doc__
