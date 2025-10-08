def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.notify_server_ui",
        "name": "Notify Server UI",
        "version": "1.0.0",
        "enabled": True,
        "deps": ["top_panel"],
    }


def get_plugin_class():
    import re
    from src.plugins.core._base import BasePlugin
    from ._utils import NotifyUtils

    class UI(BasePlugin):
        def __init__(self, panel_instance) -> None:
            super().__init__(panel_instance)
            self.notify_utils = NotifyUtils(panel_instance)
            self.app = self.gtk.Application(
                application_id="com.example.NotificationPopup"
            )
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
            This pattern is designed to catch http/https, ftp, file, and www. links.
            It ensures the returned URI is launchable by adding a scheme if necessary.
            """
            url_regex = r"(?:https?|ftp|file)://\S+|www\.\S+"
            matches = re.findall(url_regex, text)
            if matches:
                uri = matches[0].rstrip(".,;")
                if uri.startswith("www.") and "://" not in uri:
                    uri = "http://" + uri
                return uri
            return None

        def _strip_html_tags(self, text: str) -> str:
            """
            Removes all HTML/XML/Pango tags from a string for safe display.
            """
            return re.sub(r"<[^>]*>", "", text)

        def on_notification_click(self, gesture, n_press, x, y, notification, window):
            """
            Handle click action on a notification:
            1. Extract URI from hints (priority) or body (fallback).
            2. If URI exists, use xdg-open via self.cmd.run (synchronous) and return.
            3. If no URI, launch application from desktop-entry hint (FALLBACK).
            """
            hints = notification.get("hints", {})
            desktop_entry = hints.get("desktop-entry", "").lower()
            uri_to_launch = hints.get("uri") or hints.get("url")
            if not uri_to_launch:
                uri_to_launch = self._extract_first_uri_from_text(
                    notification.get("body", "")
                )
            if uri_to_launch:
                command = f"xdg-open '{uri_to_launch}'"
                try:
                    self.cmd.run(command)
                    self.logger.info(f"Launching URI (via xdg-open): {uri_to_launch}")
                except Exception as e:
                    self.logger.error(f"Failed to launch URI with xdg-open: {e}")
                window.close()
                return
            if desktop_entry:
                self.cmd.run(desktop_entry)
                self.logger.info(
                    f"Launching application via desktop entry: {desktop_entry}"
                )
                window.close()
                return
            self.logger.debug("Notification click had no associated action.")

        def show_popup(self, notification):
            """
            Show a GTK4 popup for the notification using LayerShell.
            :param notification: Dictionary containing notification details.
            """
            self.notify_reload_config()
            if not self.show_messages:
                self.logger.info(
                    "Do Not Disturb mode is active. Notification suppressed."
                )
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
            window = self.gtk.Window()
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
            vbox = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL, spacing=10)
            vbox.set_margin_top(10)
            vbox.set_margin_bottom(10)
            vbox.set_margin_start(10)
            vbox.set_margin_end(10)
            vbox.add_css_class("notify-server-vbox")
            click_gesture = self.gtk.GestureClick.new()
            click_gesture.set_button(0)
            click_gesture.connect(
                "released", self.on_notification_click, notification, window
            )
            vbox.add_controller(click_gesture)
            icon = self.notify_utils.load_icon(notification)
            if icon:
                icon.set_pixel_size(48)
                vbox.append(icon)
            summary_label = self.gtk.Label(label=notification["summary"])
            summary_label.add_css_class("notify-server-summary-label")
            summary_label.set_wrap(True)
            vbox.append(summary_label)
            body_text_to_display = self._strip_html_tags(notification["body"])
            body_label = self.gtk.Label(label=body_text_to_display)
            body_label.add_css_class("notify-server-body-label")
            body_label.set_wrap(True)
            body_label.set_max_width_chars(100)
            body_label.set_lines(5)
            body_label.set_ellipsize(self.pango.EllipsizeMode.END)
            body_label.set_halign(self.gtk.Align.CENTER)
            vbox.append(body_label)
            close_button = self.gtk.Button(label="Close")
            close_button.connect("clicked", lambda _: window.close())
            vbox.append(close_button)
            window.set_child(vbox)
            window.set_default_size(popup_width, popup_height)
            vbox.add_css_class("notification-box")
            summary_label.add_css_class("notification-summary")
            body_label.add_css_class("notification-body")
            window.present()
            self.glib.timeout_add_seconds(
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
                API, `self.gtk4LayerShell`, to create windows that are not managed
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
            5.  **Unified Click Action (Final Launch Fix)**: The entire notification box is clickable via `self.gtk.GestureClick`. The `on_notification_click` method centralizes the action hierarchy:
                - **Launch Mechanism FIX**: The problematic asynchronous `Gtk.UriLauncher` methods (`_launch_uri_async` and `on_launch_finished`) have been removed from the class. They are replaced by a **synchronous** call to `self.cmd.run(f"xdg-open '{uri_to_launch}'")`. This direct command execution is the most robust way to launch all URIs (including `file://` paths) from a transient window environment, eliminating the race condition that caused the "application launch failed" error.
                - **Window Closure**: For both URI launches and `desktop-entry` launches, `window.close()` is now performed immediately after the synchronous `self.cmd.run` call, ensuring the notification disappears upon action.
                - **URI Extraction**: `_extract_first_uri_from_text` correctly recognizes **`file://`** URIs in addition to web protocols.
            """
            return self.code_explanation.__doc__

    return UI
