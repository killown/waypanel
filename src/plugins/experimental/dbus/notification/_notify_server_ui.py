import gi
import re
from gi.repository import Gtk, GLib, Pango  # pyright: ignore
from src.plugins.core._base import BasePlugin
from ._utils import NotifyUtils

gi.require_version("Gtk", "4.0")


class UI(BasePlugin):
    def __init__(self, panel_instance) -> None:
        super().__init__(panel_instance)
        self.notify_utils = NotifyUtils(panel_instance)
        self.app = Gtk.Application(application_id="com.example.NotificationPopup")
        self.app.connect("activate", self.on_activate)

    def on_activate(self, app):
        """
        Callback when the GTK application is activated.
        """
        pass

    def notify_reload_config(self):
        self.show_messages = self.get_config(
            ["notify", "server", "show_messages"], True
        )
        self.timeout = self.get_config(["notify", "server", "timeout"], 10)

    def _extract_first_uri_from_text(self, text: str) -> str | None:
        """
        Uses a regular expression to find and return the first URL in a string.
        This pattern is designed to catch http/https, ftp, and www. links.
        """
        url_regex = r"(?:https?|ftp)://\S+|www\.\S+"
        matches = re.findall(url_regex, text)
        if matches:
            uri = matches[0].rstrip(".,;")
            return uri
        return None

    def _launch_uri_async(self, uri: str, window: Gtk.Window):
        """
        Launches the specified URI asynchronously using Gtk.UriLauncher.
        """
        launcher = Gtk.UriLauncher.new(uri)
        launcher.launch(
            window,
            None,
            self.on_launch_finished,
            None,
        )
        self.logger.info(f"Launching URI: {uri}")

    def on_launch_finished(self, source_object, result, user_data):
        """
        Callback to handle the result of the Gtk.UriLauncher.launch() operation.
        """
        try:
            launcher = source_object
            success = launcher.launch_finish(result)
            if success:
                self.logger.info(f"URI successfully launched: {launcher.get_uri()}")
            else:
                self.logger.warning(
                    f"URI launch failed or was canceled for: {launcher.get_uri()}"
                )
        except GLib.Error as e:
            self.logger.error(f"Error launching URI: {e.message}")

    def on_notification_click(self, gesture, n_press, x, y, notification, window):
        """
        Handle click action on a notification:
        1. Link in body (Highest Priority)
        2. Link in hints (Fallback)
        3. Desktop Entry in hints (App Launch)
        """
        window.close()
        uri_to_launch = self._extract_first_uri_from_text(notification.get("body", ""))
        if not uri_to_launch:
            hints = notification.get("hints", {})
            uri_to_launch = hints.get("url", "")
        if uri_to_launch:
            self._launch_uri_async(uri_to_launch, window)
            return
        hints = notification.get("hints", {})
        desktop_entry = hints.get("desktop-entry", "").lower()
        if desktop_entry:
            self.cmd.run(desktop_entry)
            self.logger.info(
                f"Launching application via desktop entry: {desktop_entry}"
            )
            return
        self.logger.debug("Notification click had no associated action.")

    def show_popup(self, notification):
        """
        Show a GTK4 popup for the notification using LayerShell.
        :param notification: Dictionary containing notification details.
        """
        self.notify_reload_config()
        if not self.show_messages:
            self.logger.info("Do Not Disturb mode is active. Notification suppressed.")
            return
        popup_width = self.get_config(["notify", "server", "popup_width"], 399)
        popup_height = self.get_config(["notify", "server", "popup_height"], 150)
        focused_output = self.ipc.get_focused_output()
        output_w = focused_output["geometry"]["width"]
        if "rect" in focused_output:
            output_w = focused_output["rect"]["width"]
        center_popup_position = (output_w - popup_width) // 2
        top_popup_position = 32
        new_width_position = self.get_config(
            ["notify", "server", "popup_position_x"], False
        )
        new_height_position = self.get_config(
            ["notify", "server", "popup_position_y"], False
        )
        if new_width_position:
            center_popup_position = new_width_position
        if new_height_position:
            top_popup_position = new_height_position
        window = Gtk.Window()
        window.add_css_class("notify-window")
        self.layer_shell.init_for_window(window)
        self.layer_shell.set_layer(window, self.layer_shell.Layer.TOP)
        self.layer_shell.set_anchor(window, self.layer_shell.Edge.TOP, True)
        self.layer_shell.set_anchor(window, self.layer_shell.Edge.RIGHT, True)
        self.layer_shell.set_margin(
            window, self.layer_shell.Edge.TOP, top_popup_position
        )
        self.layer_shell.set_margin(
            window, self.layer_shell.Edge.RIGHT, center_popup_position
        )
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.add_css_class("notify-server-vbox")
        click_gesture = Gtk.GestureClick.new()
        click_gesture.set_button(0)
        click_gesture.connect(
            "released", self.on_notification_click, notification, window
        )
        vbox.add_controller(click_gesture)
        icon = self.notify_utils.load_icon(notification)
        if icon:
            icon.set_pixel_size(48)
            vbox.append(icon)
        summary_label = Gtk.Label(label=notification["summary"])
        summary_label.add_css_class("notify-server-summary-label")
        summary_label.set_wrap(True)
        vbox.append(summary_label)
        body_label = Gtk.Label(label=notification["body"])
        body_label.add_css_class("notify-server-body-label")
        body_label.set_wrap(True)
        body_label.set_max_width_chars(100)
        body_label.set_lines(5)
        body_label.set_ellipsize(Pango.EllipsizeMode.END)
        body_label.set_halign(Gtk.Align.CENTER)
        vbox.append(body_label)
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _: window.close())
        vbox.append(close_button)
        window.set_child(vbox)
        window.set_default_size(popup_width, popup_height)
        vbox.add_css_class("notification-box")
        summary_label.add_css_class("notification-summary")
        body_label.add_css_class("notification-body")
        window.present()
        GLib.timeout_add_seconds(
            self.timeout, lambda: window.close() if window.is_visible() else False
        )

    def about(self):
        """
        This module provides the user-facing graphical interface (UI)
        for the notification server, responsible for rendering ephemeral
        pop-up notifications on the desktop.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this UI module is to act as the presentation
        layer for a decoupled notification system. Its design is based
        on principles that make it robust and adaptable to future changes:
        1.  **Separation of UI and Logic**: It is deliberately separated
            from the D-Bus service (`notify_server.py`). Its only job is
            to visually display notifications and respect the "Do Not
            Disturb" setting. The `show_popup` method is the entry point
            for this display logic.
        2.  **Platform-Specific Presentation**: It utilizes a specialized
            API, `Gtk4LayerShell`, to create windows that are not managed
            by the typical window manager. This ensures that notifications
            appear consistently as non-intrusive overlays on the desktop.
        3.  **Dynamic Configuration**: The module dynamically loads
            settings (like pop-up size, position, and timeout) from a
            configuration file. This externalizes user preferences, making
            the UI highly customizable without requiring code modification.
        4.  **Controlled Lifetime**: Each notification pop-up is given a
            finite, configurable lifespan using a timer. This prevents the
            UI from becoming cluttered with stale notifications and ensures
            they are a transient visual cue rather than a persistent window.
        5.  **Unified Click Action**: The previous link button has been
            removed. Now, the entire notification box is clickable via
            `Gtk.GestureClick`. The `on_notification_click` method
            centralizes the action hierarchy:
            - **Launch URI**: If a URL is found in the body or hints, it's
              launched using `Gtk.UriLauncher` (the GTK equivalent of
              asynchronous `xdg-open`).
            - **Launch App**: If no URI, but a `desktop-entry` hint exists,
              the application is launched using `self.cmd.run`.
            - **Closure**: In all cases where an action is attempted, the
              notification window is immediately closed.
        """
        return self.code_explanation.__doc__
