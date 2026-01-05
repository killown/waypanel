# The MIT License (MIT)
#
# Copyright (c) 2023 Thiago <24453+killown@users.noreply.github.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


def get_plugin_metadata(_):
    about = """
            This plugin is a D-Bus service that acts as a notification
            daemon, implementing the FreeDesktop.org Notifications
            Specification. It receives, stores, and displays desktop
            notifications from other applications.
            """
    return {
        "id": "org.waypanel.plugin.notify_server",
        "name": "Notify Server",
        "version": "1.0.0",
        "enabled": True,
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    import asyncio
    from dbus_next.aio.message_bus import MessageBus
    from dbus_next.service import ServiceInterface, method, signal
    from dbus_next.constants import BusType, NameFlag, RequestNameReply
    from gi.repository import GLib  # pyright: ignore
    from ._notify_server_db import Database
    from ._notify_server_ui import get_plugin_class

    def run_server_in_background(panel_instance):
        async def _run_server():
            server = NotificationDaemon(panel_instance)
            await server.run()
            panel_instance.logger.info("Notification server running in background")
            while True:  # Keep alive
                await asyncio.sleep(1)

        def _start_loop():
            asyncio.run(_run_server())

        import threading

        thread = threading.Thread(target=_start_loop, daemon=True)
        thread.start()
        return thread

    class NotificationDaemon(ServiceInterface):
        def __init__(self, panel_instance):
            super().__init__("org.freedesktop.Notifications")
            self.last_modified = None
            self.db = Database(panel_instance)
            ui = get_plugin_class()
            self.ui = ui(panel_instance)
            self.logger = self.ui.logger
            self.config_handler = panel_instance.config_handler
            self.timeout = self.config_handler.config_data.get(
                "org.waypanel.plugin.notify_client"
            ).get("server_timeout", 10)
            self.notify_client_setting = self.config_handler.config_data.get(
                "org.waypanel.plugin.notify_client"
            )
            self.show_messages = self.notify_client_setting.get("show_messages", True)

            # Initialize the database
            self.db_path = self.db._initialize_db()

            # Store notifications
            self.notifications = {}
            self.next_id = 1

            self.logger.info(
                "Notification daemon started. Listening for notifications..."
            )

        @method()
        async def Notify(
            self,
            app_name: "s",
            replaces_id: "u",
            app_icon: "s",
            summary: "s",
            body: "s",
            actions: "as",
            hints: "a{sv}",
            expire_timeout: "i",
        ) -> "u":
            """Handle incoming notifications."""
            notification_id = replaces_id if replaces_id != 0 else self.next_id
            self.next_id += 1
            notification = {
                "app_name": app_name,
                "summary": summary,
                "body": body,
                "app_icon": app_icon,
                "actions": actions,
                "hints": {k: v.value for k, v in hints.items()},
                "expire_timeout": expire_timeout,
            }
            self.notifications[notification_id] = notification

            # Save the notification to the database
            self.db._save_notification_to_db(notification, self.db_path)
            self.logger.info(f"Received notification {notification_id}:")
            self.logger.info(f" App: {app_name}")
            self.logger.info(f" Summary: {summary}")
            self.logger.info(f" Body: {body}")
            self.logger.info(f" Icon: {app_icon}")

            # Show a popup for the notification
            GLib.idle_add(self.ui.show_popup, notification)

            # Emit the NotificationClosed signal after the timeout
            if expire_timeout > 0:
                GLib.timeout_add(
                    expire_timeout, self.close_notification, notification_id, 1
                )

            return notification_id

        @method()
        def CloseNotification(self, id: "u"):
            if id in self.notifications:
                del self.notifications[id]
                self.NotificationClosed(id, 1)
            else:
                self.logger.info(f"Attempted to close non-existent notification {id}")

        @signal()
        def NotificationClosed(self, id: "u", reason: "u") -> "uu":
            self.logger.info(
                f"Emitting NotificationClosed signal: id={id}, reason={reason}"
            )
            return [id, reason]

        @signal()
        def ActionInvoked(self, id: "u", action_key: "s") -> "us":
            self.logger.info(
                f"Emitting ActionInvoked signal: id={id}, action_key={action_key}"
            )
            return [id, action_key]

        @method()
        def GetCapabilities(self) -> "as":
            return ["actions", "body", "icon-static"]

        @method()
        def GetServerInformation(self) -> "ssss":
            """Returns the server identity and supported specification version.

            The return signature consists of four strings:
            1. Server Name: Identifies the implementation.
            2. Vendor: The entity/project responsible for the code.
            3. Version: The specific release version of this server.
            4. Spec Version: The FreeDesktop.org Notification Spec version supported.

            IMPLICATIONS:
            The Spec Version MUST be '1.0' or higher (e.g., '1.2'). Setting this to
            a value where the major version is 0 (e.g., '0.1') will cause
            strict client libraries like libnotify to trigger a SIGABRT via
            an internal assertion failure. This value acts as a contract
            guaranteeing that the server supports the mandatory methods and
            signals defined in the reported version of the protocol.
            """
            return ["waypanel", "waypanel-project", "1.0.0", "1.2"]

        def close_notification(self, id, reason):
            if id in self.notifications:
                del self.notifications[id]
                self.NotificationClosed(id, reason)

        async def run(self):
            """Start the notification daemon."""
            try:
                bus = await MessageBus(bus_type=BusType.SESSION).connect()
                bus.export("/org/freedesktop/Notifications", self)
                reply = await bus.request_name(
                    "org.freedesktop.Notifications",
                    flags=NameFlag.ALLOW_REPLACEMENT
                    | NameFlag.REPLACE_EXISTING
                    | NameFlag.DO_NOT_QUEUE,
                )
                if reply != RequestNameReply.PRIMARY_OWNER:
                    self.logger.info(
                        "Failed to acquire the org.freedesktop.Notifications name. Is another daemon running?"
                    )
                    return
                self.logger.info(
                    "Notification daemon started. Listening for notifications..."
                )
                await asyncio.Future()
            except Exception as e:
                self.logger.error(f"Error starting notification daemon: {e}")

        def code_explanation(self):
            """
            This code's core logic is to provide a persistent,
            future-proof desktop notification server. It's built on three
            main principles:

            1.  **Standardized Communication**: The service uses D-Bus to
                adhere to the `org.freedesktop.Notifications` standard. This
                makes it universally compatible with any application that
                wants to send notifications, decoupling the server's
                implementation from the clients that use it.

            2.  **Separation of Concerns**: The logic is divided into
                distinct components:
                - A **D-Bus communication layer** that listens for requests.
                - A **database layer** for long-term storage of
                  notifications.
                - A **UI layer** that is responsible only for displaying
                  the visual pop-ups.
                This modular design allows each part to be refactored
                independently without affecting the others.

            3.  **Asynchronous and Concurrent Processing**: The D-Bus
                server runs in a dedicated background thread using
                `asyncio`. This ensures that processing incoming
                notifications does not block or freeze the main UI thread
                of the panel, providing a smooth and responsive user
                experience. The `Notify` method handles the full
                notification lifecycle, from receipt to database storage,
                UI display, and timed expiration.
            """
            return self.code_explanation.__doc__

    return run_server_in_background
