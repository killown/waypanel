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
    import threading
    from dbus_fast.aio import MessageBus
    from dbus_fast.service import ServiceInterface, method, signal
    from dbus_fast import BusType, NameFlag, RequestNameReply
    from gi.repository import GLib
    from src.plugins.core._event_loop import get_global_loop
    from ._notify_server_db import Database
    from ._notify_server_ui import get_plugin_class as get_ui_class

    def run_server_in_background(panel_instance):
        """
        Registers the notification daemon within the global asyncio loop.
        """
        server = NotificationDaemon(panel_instance)
        loop = get_global_loop()

        async def _run_server():
            await server.run()
            panel_instance.logger.info(
                "Notification server integrated with global loop"
            )

        # Schedule the server startup in the global loop
        asyncio.run_coroutine_threadsafe(_run_server(), loop)

        # Start the global loop in a single shared thread if it's not running
        if not loop.is_running():

            def start_loop():
                asyncio.set_event_loop(loop)
                loop.run_forever()

            thread = threading.Thread(target=start_loop, daemon=True)
            thread.start()

        return server

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
            notification_id = replaces_id if replaces_id != 0 else self.next_id
            if replaces_id == 0:
                self.next_id += 1

            # UI Version (Raw data for immediate display)
            notification_ui = {
                "app_name": app_name,
                "summary": summary,
                "body": body,
                "app_icon": app_icon,
                "actions": actions,
                "hints": hints,
                "expire_timeout": expire_timeout,
            }
            self.notifications[notification_id] = notification_ui

            # DB Version (Sanitized and Cached)
            try:
                # sanitize_for_db now returns a path string if it saves an image
                processed_hints = self.ui.notify_utils.sanitize_for_db(
                    hints, notification_id
                )

                # Check if processed_hints is a path to a cached icon
                db_icon = app_icon
                if isinstance(processed_hints, str) and processed_hints.endswith(
                    ".png"
                ):
                    db_icon = processed_hints

                notification_db = {
                    "app_name": app_name,
                    "summary": summary,
                    "body": body,
                    "app_icon": db_icon,
                    "actions": actions,
                    "hints": processed_hints,
                    "expire_timeout": expire_timeout,
                }
                self.db._save_notification_to_db(notification_db, self.db_path)
            except Exception as e:
                self.logger.error(f"Failed to save notification: {str(e)}")

            GLib.idle_add(self.ui.show_popup, notification_ui)
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
