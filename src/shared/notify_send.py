from gi.repository import Gio, GLib  # pyright: ignore
import threading


class Notifier:
    def __init__(self):
        # Start a background GLib MainLoop thread once
        self.loop = GLib.MainLoop()
        self.loop_thread = threading.Thread(target=self.loop.run, daemon=True)
        self.loop_thread.start()

    def _on_notification_sent(self, proxy, result, *args):
        try:
            proxy.call_finish(result)
        except Exception as e:
            print(f"Error sending notification: {e}")

    def _on_bus_acquired(self, source_object, result, user_data):
        title, message, icon = user_data
        try:
            # Finish acquiring the bus
            connection = Gio.bus_get_finish(result)

            # Create a **synchronous proxy** now that we have the bus
            proxy = Gio.DBusProxy.new_sync(
                connection,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
                None,
            )

            app_name = "Notify"
            replaces_id = 0
            hints = {}
            expire_timeout = 5000

            # Async call to send the notification
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
                        [],
                        hints,
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

    def notify_send(self, title: str, message: str, icon: str = ""):
        # Fire-and-forget async notification
        Gio.bus_get(
            Gio.BusType.SESSION, None, self._on_bus_acquired, (title, message, icon)
        )
