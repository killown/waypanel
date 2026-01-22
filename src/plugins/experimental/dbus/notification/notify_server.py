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
        "version": "1.1.0",
        "enabled": True,
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    import asyncio

    from dbus_fast.aio import MessageBus
    from dbus_fast.service import ServiceInterface, method, signal
    from dbus_fast import BusType, NameFlag, RequestNameReply
    from gi.repository import GLib
    from ._notify_server_db import Database
    from ._notify_server_ui import get_plugin_class as get_ui_class

    def run_server_in_background(panel_instance):
        async def _run_server():
            server = NotificationDaemon(panel_instance)
            await server.run()
            panel_instance.logger.info(
                "Notification server (dbus-fast) running in background"
            )
            # Keep the background loop alive
            await asyncio.Future()

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
            ui_plugin_class = get_ui_class()
            self.ui = ui_plugin_class(panel_instance)
            self.logger = self.ui.logger
            self.config_handler = panel_instance.config_handler

            # Safe settings retrieval
            notify_client_cfg = self.config_handler.config_data.get(
                "org.waypanel.plugin.notify_client", {}
            )
            self.timeout = notify_client_cfg.get("server_timeout", 10)
            self.show_messages = notify_client_cfg.get("show_messages", True)

            # Initialize the database
            self.db_path = self.db._initialize_db()

            self.notifications = {}
            self.next_id = 1

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
            """Handle incoming notifications via dbus-fast."""
            notification_id = replaces_id if replaces_id != 0 else self.next_id
            if replaces_id == 0:
                self.next_id += 1

            # dbus-fast Variant handling: unpack .value if it exists
            processed_hints = {}
            for k, v in hints.items():
                processed_hints[k] = v.value if hasattr(v, "value") else v

            notification = {
                "app_name": app_name,
                "summary": summary,
                "body": body,
                "app_icon": app_icon,
                "actions": actions,
                "hints": processed_hints,
                "expire_timeout": expire_timeout,
            }
            self.notifications[notification_id] = notification

            # Save the notification to the database
            self.db._save_notification_to_db(notification, self.db_path)

            self.logger.info(f"Received notification {notification_id} from {app_name}")

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
            return [id, reason]

        @signal()
        def ActionInvoked(self, id: "u", action_key: "s") -> "us":
            return [id, action_key]

        @method()
        def GetCapabilities(self) -> "as":
            return ["actions", "body", "icon-static"]

        @method()
        def GetServerInformation(self) -> "ssss":
            return ["waypanel", "waypanel-project", "1.1.0", "1.2"]

        def close_notification(self, id, reason):
            if id in self.notifications:
                del self.notifications[id]
                self.NotificationClosed(id, reason)

        async def run(self):
            """Start the notification daemon using dbus-fast connection logic."""
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
                        "Failed to acquire org.freedesktop.Notifications name."
                    )
                    return

                self.logger.info("Notification daemon listening via dbus-fast.")
            except Exception as e:
                self.logger.error(f"Error starting notification daemon: {e}")

    return run_server_in_background
