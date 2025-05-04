from gi.repository import Gtk, GLib, Pango
from gi.repository import Gtk, Gtk4LayerShell as LayerShell
from src.plugins.core._base import BasePlugin
import os
import toml
from ._utils import NotifyUtils


class UI(BasePlugin):
    def __init__(self, panel_instance) -> None:
        super().__init__(panel_instance)
        self.layer_shell = LayerShell
        self.notify_utils = NotifyUtils(panel_instance)
        # Initialize GTK application for popups
        self.app = Gtk.Application(application_id="com.example.NotificationPopup")
        self.app.connect("activate", self.on_activate)

    def on_activate(self, app):
        """
        Callback when the GTK application is activated.
        """
        pass

    def notify_reload_config(self):
        self.config = self.load_config()
        self.show_messages = (
            self.config.get("notify", {}).get("server", {}).get("show_messages", True)
        )
        self.timeout = (
            self.config.get("notify", {}).get("server", {}).get("timeout", 10)
        )

    def load_config(self):
        config_path = os.path.expanduser("~/.config/waypanel/waypanel.toml")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return toml.load(f)
        return {}

    def show_popup(self, notification):
        """
        Show a GTK4 popup for the notification using LayerShell.
        :param notification: Dictionary containing notification details.
        """
        self.notify_reload_config()
        if not self.show_messages:
            self.logger.info("Do Not Disturb mode is active. Notification suppressed.")
            return

        # FIXME: make this data work with the config
        popup_width = (
            self.config.get("notify", {}).get("server", {}).get("popup_width", 399)
        )
        popup_height = (
            self.config.get("notify", {}).get("server", {}).get("popup_height", 150)
        )
        output_w = self.ipc.get_focused_output()["geometry"]["width"]
        center_popup_position = (output_w - popup_width) // 2
        top_popup_position = 32
        new_width_position = (
            self.config.get("notify", {})
            .get("server", {})
            .get("popup_position_x", False)
        )
        new_height_position = (
            self.config.get("notify", {})
            .get("server", {})
            .get("popup_position_y", False)
        )
        if new_width_position:
            center_popup_position = new_width_position
        if new_height_position:
            top_popup_position = new_height_position

        # Create a new window for the popup
        window = Gtk.Window()
        window.add_css_class("notify-window")
        self.layer_shell.init_for_window(window)
        self.layer_shell.set_layer(
            window, self.layer_shell.Layer.TOP
        )  # Set the popup to the top layer
        self.layer_shell.set_anchor(
            window, self.layer_shell.Edge.TOP, True
        )  # Anchor to the top of the screen
        self.layer_shell.set_anchor(
            window, self.layer_shell.Edge.RIGHT, True
        )  # Anchor to the right of the screen
        self.layer_shell.set_margin(
            window, self.layer_shell.Edge.TOP, top_popup_position
        )  # Add margin from the top
        self.layer_shell.set_margin(
            window, self.layer_shell.Edge.RIGHT, center_popup_position
        )  # Add margin from the right

        # Center the popup horizontally by anchoring to both left and right edges

        # Create the content of the popup
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.add_css_class("notify-server-vbox")

        icon = self.notify_utils.load_icon(notification)
        if icon:
            icon.set_pixel_size(48)
            vbox.append(icon)

        # Summary
        summary_label = Gtk.Label(label=notification["summary"])
        summary_label.add_css_class("notify-server-summary-label")
        summary_label.set_wrap(True)
        vbox.append(summary_label)

        # Body (with forced text wrapping and ellipsis for long strings)
        body_label = Gtk.Label(label=notification["body"])
        body_label.add_css_class("notify-server-body-label")
        body_label.set_wrap(True)  # Enable text wrapping
        body_label.set_max_width_chars(100)  # Limit the number of characters per line
        body_label.set_lines(5)
        body_label.set_ellipsize(
            Pango.EllipsizeMode.END
        )  # Add ellipsis (...) for overflow
        body_label.set_halign(Gtk.Align.CENTER)

        vbox.append(body_label)

        # Close button
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _: window.close())
        vbox.append(close_button)

        # Set the content of the window
        window.set_child(vbox)
        window.set_default_size(
            popup_width, popup_height
        )  # Set default size for the popup

        # Add CSS classes for styling
        vbox.add_css_class("notification-box")
        summary_label.add_css_class("notification-summary")
        body_label.add_css_class("notification-body")

        # Present the window
        window.present()

        # Automatically close the popup after self.timeout seconds
        GLib.timeout_add_seconds(self.timeout, lambda: window.close())
