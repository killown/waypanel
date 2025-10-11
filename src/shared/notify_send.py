from gi.repository import Gio, GLib  # pyright: ignore
import threading


class Notifier:
    def __init__(self):
        self.loop = GLib.MainLoop()
        self.loop_thread = threading.Thread(target=self.loop.run, daemon=True)
        self.loop_thread.start()

    def _on_notification_sent(self, proxy, result, *args):
        try:
            proxy.call_finish(result)
        except Exception as e:
            print(f"Error sending notification: {e}")

    def _on_bus_acquired(self, source_object, result, user_data):
        (
            title,
            message,
            icon,
            app_name,
            replaces_id,
            expire_timeout,
            hints,
            actions,
        ) = user_data
        try:
            connection = Gio.bus_get_finish(result)
            proxy = Gio.DBusProxy.new_sync(
                connection,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
                None,
            )
            final_hints = {}
            if hints:
                for key, value in hints.items():
                    if isinstance(value, str):
                        final_hints[key] = GLib.Variant("s", value)
                    elif isinstance(value, int):
                        final_hints[key] = GLib.Variant("i", value)
                    elif isinstance(value, bool):
                        final_hints[key] = GLib.Variant("b", value)
                    elif isinstance(value, GLib.Variant):
                        final_hints[key] = value
                    else:
                        print(
                            f"Warning: Hint '{key}' has unsupported type {type(value)}. Skipping."
                        )
            final_actions = actions if isinstance(actions, list) else []
            proxy.call(
                "Notify",
                GLib.Variant(
                    "(susssasa{sv}i)",
                    (
                        app_name,
                        replaces_id,
                        icon,
                        title,
                        message,
                        final_actions,
                        final_hints,
                        expire_timeout,
                    ),
                ),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                self._on_notification_sent,
            )
        except Exception as e:
            print(f"Error preparing notification: {e}")

    def notify_send(
        self,
        title: str,
        message: str,
        icon: str = "",
        app_name: str = "Waypanel",
        replaces_id: int = 0,
        expire_timeout: int = 5000,
        hints: dict = None,  # pyright: ignore
        actions: list = None,  # pyright: ignore
    ):
        """
        Sends a desktop notification with full support for DBus Notify arguments.
        Args:
            title (str): The summary text.
            message (str): The body text.
            icon (str): Name of the icon to display (e.g., 'dialog-information').
            app_name (str): The application name to display. Defaults to 'Waypanel'.
            replaces_id (int): ID of the notification to replace (0 for new).
            expire_timeout (int): Notification timeout in milliseconds.
            hints (dict): A dictionary of hints (key/value pairs). Values (str, int, bool)
                          are auto-converted to GLib.Variant. This is where you pass
                          URL hints (e.g., {'x-action-url': 'http://example.com'}) or
                          urgency levels.
            actions (list): An array of strings defining action keys and labels
                            (e.g., ['key1', 'Label 1', 'key2', 'Label 2']).
        """
        Gio.bus_get(
            Gio.BusType.SESSION,
            None,
            self._on_bus_acquired,
            (
                title,
                message,
                icon,
                app_name,
                replaces_id,
                expire_timeout,
                hints,
                actions,
            ),
        )
