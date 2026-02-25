from dbus_fast.aio import MessageBus
from dbus_fast import Message
from dbus_fast.constants import MessageType
from dbus_fast.service import ServiceInterface, dbus_property, signal, method
from dbus_fast import Variant, DBusError, BusType, PropertyAccess
import asyncio
import typing
from typing import Dict
from src.plugins.core._event_loop import get_global_loop
from src.plugins.core._base import BasePlugin
from ._dbus_menu_proxy import DBusMenuProxy, dbus_menu_to_gio_model
from src.shared.concurrency_helper import ConcurrencyHelper


class StatusNotifierHost(BasePlugin):
    """
    This plugin is a D-Bus service that acts as a
    StatusNotifierHost to manage system tray icons.
    """

    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.items = {}
        self._on_item_added = []
        self._on_item_removed = []

    async def register_item(self, bus: MessageBus, service_name: str, object_path: str):
        """Register a new StatusNotifierItem."""
        try:
            item = StatusNotifierItem(bus, service_name, object_path, self.obj)
            self.items[service_name] = item
            success = await item.initialize()
            if success:
                for callback in self._on_item_added:
                    callback(item)
            else:
                self.logger.error(
                    f"Failed to initialize StatusNotifierItem for {service_name}{object_path}"
                )
        except Exception as e:
            self.logger.error(
                f"Error registering item for {service_name}{object_path}: {e}"
            )

    def unregister_item(self, service_name: str):
        """
        Unregister a StatusNotifierItem and clean up resources.
        Args:
            service_name (str): The D-Bus service name of the tray icon.
        """
        if service_name in self.items:
            item = self.items.pop(service_name, None)
            if item:
                self.logger.info(f"Removing tray icon for service: {service_name}")
                for callback in self._on_item_removed:
                    try:
                        callback(item)
                    except Exception as e:
                        self.logger.error(
                            f"Error invoking removal callback for {service_name}: {e}"
                        )
            else:
                self.logger.error(f"No tray icon found for service: {service_name}")
        else:
            self.logger.warning(f"Service not registered: {service_name}")


class StatusNotifierWatcher(ServiceInterface):
    """
    The central service that listens for applications to register new tray icons.
    """

    def __init__(self, service: str, panel_instance):
        super().__init__(service)
        self.host = StatusNotifierHost(panel_instance)
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.loop = get_global_loop()
        self.newest_service_name = None
        self._items: list[tuple[str, str]] = []
        self.bus = None
        self.on_item_added = None
        self.object_path_to_bus_name = {}
        self.on_item_removed = None
        self.status_notifier_item = None
        self.watcher = None
        self.service = service
        self.service_name_to_object_path: Dict[str, str] = {}
        self.concurrency_helper = ConcurrencyHelper(panel_instance)

    def run_server_in_background(self, panel_instance):
        watcher = None
        from ._service import (
            StatusNotifierWatcher,
            StatusNotifierItem,
        )

        async def _run_server(panel_instance):
            bus_name = "org.kde.StatusNotifierWatcher"
            watcher = StatusNotifierWatcher(bus_name, self.obj)
            bus = await watcher.setup()
            bus.export("/StatusNotifierWatcher", watcher)
            await bus.request_name(bus_name)

            async def on_item_added(service_name: str, object_path: str):
                self.status_notifier_item = StatusNotifierItem(
                    bus, service_name, object_path, panel_instance
                )
                success = await self.status_notifier_item.initialize()
                if success:
                    self.logger.info(
                        f"Initialized StatusNotifierItem for {service_name}{object_path}"
                    )
                else:
                    self.logger.warning(
                        f"Failed to initialize StatusNotifierItem for {service_name}{object_path}"
                    )

            watcher.on_item_added = on_item_added
            while True:
                await asyncio.sleep(1)

        self.concurrency_helper.run_in_async_task(_run_server(panel_instance))
        return watcher

    async def setup(self):
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self.bus.add_message_handler(self.handle_message)
        return self.bus

    def handle_name_owner_changed(
        self, service_name: str, old_owner: str, new_owner: str
    ):
        """Handle the NameOwnerChanged signal."""
        try:
            self.logger.info(
                f"NameOwnerChanged signal: {service_name}, old={old_owner}, new={new_owner}"
            )
            if new_owner:
                self.logger.info(
                    f"Service {service_name} has appeared. Waiting for it to register a StatusNotifierItem."
                )
            elif service_name in self.service_name_to_object_path:
                self.unregister_item(service_name)
        except Exception as e:
            self.logger.error(f"Error handling NameOwnerChanged signal: {e}")

    def unregister_item(self, service_name: str):
        """
        Unregister a StatusNotifierItem and clean up resources.
        Args:
            service_name (str): The D-Bus service name of the tray icon.
        """
        if service_name not in self.service_name_to_object_path:
            self.logger.warning(f"Service not registered: {service_name}")
            return
        object_path = self.service_name_to_object_path.pop(service_name, None)
        self.logger.info(f"Removed service mapping: {service_name} -> {object_path}")
        self.host.unregister_item(service_name)

        async def cleanup():
            try:
                item = StatusNotifierItem(self.bus, service_name, object_path, self.obj)  # pyright: ignore
                await item._tray_icon_removed()
            except Exception as e:
                self.logger.error(f"Error during cleanup for {service_name}: {e}")

        asyncio.create_task(cleanup())
        self.logger.info(f"Removing tray icon for service: {service_name}")

    async def get_pid_for_service(self, service_name: str, bus: MessageBus) -> int:
        """
        Retrieve the PID of a D-Bus service using its unique name.
        """
        try:
            reply = await bus.call(
                Message(
                    message_type=MessageType.METHOD_CALL,
                    destination="org.freedesktop.DBus",
                    interface="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    member="GetConnectionUnixProcessID",
                    signature="s",
                    body=[service_name],
                )
            )
            if reply.message_type == MessageType.METHOD_RETURN:  # pyright: ignore
                pid = reply.body[0]  # pyright: ignore
                return pid
            else:
                self.logger.warning(
                    f"Failed to retrieve PID for {service_name}: Invalid reply"
                )
                return -1
        except DBusError as e:
            self.logger.error(f"DBus error while fetching PID for {service_name}: {e}")
            return -1
        except Exception as e:
            self.logger.error(
                f"Unexpected error while fetching PID for {service_name}: {e}"
            )
            return -1

    @signal()
    def StatusNotifierItemRegistered(self, service_name: "s"):  # pyright: ignore
        self.logger.info(f"Tray icon registered: {service_name}")

    @signal()
    def StatusNotifierItemUnregistered(self, service_and_path: "s") -> "s":  # pyright: ignore
        """
        Signal emitted when a StatusNotifierItem is unregistered.
        """
        self.logger.info(f"StatusNotifierItem unregistered: {service_and_path}")
        return service_and_path

    def handle_message(self, message):
        try:
            if (
                message.sender == "org.freedesktop.DBus"
                and message.interface == "org.freedesktop.DBus"
                and message.member == "NameOwnerChanged"
            ):
                service_name, old_owner, new_owner = message.body
                self.handle_name_owner_changed(service_name, old_owner, new_owner)
                return
            if not message.sender or not message.body:
                return
            raw_object_path = message.body[0] if message.body else None
            if isinstance(raw_object_path, Variant):
                object_path = raw_object_path.value
            else:
                object_path = raw_object_path
            if not isinstance(object_path, str) or not object_path.startswith("/"):
                return
            if message.sender == "org.freedesktop.DBus":
                self.logger.info(f"Ignoring system-specific service: {message.sender}")
                return
            self.object_path_to_bus_name[object_path] = message.sender
            self.logger.info(f"Stored mapping: {object_path} -> {message.sender}")
            if object_path.startswith("/org/ayatana/NotificationItem"):
                self.logger.info(
                    f"Ayatana indicator detected: {message.sender} at {object_path}"
                )
        except Exception as e:
            self.logger.error(f"Error handling DBus message: {e}")

    @method()
    async def RegisterStatusNotifierItem(self, service_or_path: "s"):  # pyright: ignore
        """Register a status notifier item."""
        if not service_or_path:
            self.logger.warning("No service or path provided. Ignoring registration.")
            return
        if service_or_path == "org.freedesktop.DBus":
            self.logger.warning(f"Ignoring invalid registration: {service_or_path}")
            return
        if service_or_path.startswith(":"):
            service_name = service_or_path
            object_path = "/StatusNotifierItem"
            self.logger.info(
                f"Received service name: {service_name}, using default path: {object_path}"
            )
        elif service_or_path.startswith("/"):
            object_path = service_or_path
            service_name = await self.resolve_service_name_for_object_path(object_path)
            if not service_name:
                self.logger.warning(
                    f"Failed to resolve bus name for object path: {object_path}"
                )
                return
            self.logger.info(
                f"Resolved service name: {service_name} for object path: {object_path}"
            )
        else:
            self.logger.warning(
                f"Invalid input format: {service_or_path}. Must start with ':' or '/'."
            )
            return
        self.service_name_to_object_path[service_name] = object_path
        try:
            item = StatusNotifierItem(self.bus, service_name, object_path, self.obj)  # pyright: ignore
            success = await item.initialize()
            if not success:
                self.logger.warning(
                    f"Failed to initialize StatusNotifierItem for {service_name}{object_path}"
                )
                return
            await self.host.register_item(self.bus, service_name, object_path)  # pyright: ignore
            self.StatusNotifierItemRegistered(f"{service_name} {object_path}")
        except Exception as e:
            self.logger.error(
                f"Error creating StatusNotifierItem for {service_name}{object_path}: {e}"
            )

    async def resolve_service_name_for_object_path(
        self, object_path: str
    ) -> str | None:
        """
        Resolve the current service name for a given object path.
        """
        try:
            if object_path in self.object_path_to_bus_name:
                bus_name = self.object_path_to_bus_name[object_path]
                self.logger.info(
                    f"Resolved service name from dictionary: {bus_name} for object path: {object_path}"
                )
                return bus_name
            bus = await MessageBus().connect()
            reply = await bus.call(
                Message(
                    message_type=MessageType.METHOD_CALL,
                    destination="org.freedesktop.DBus",
                    interface="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    member="GetNameOwner",
                    signature="s",
                    body=[object_path],
                )
            )
            if reply.message_type == MessageType.METHOD_RETURN:  # pyright: ignore
                bus_name = reply.body[0]  # pyright: ignore
                self.object_path_to_bus_name[object_path] = bus_name
                self.logger.info(
                    f"Resolved service name via introspection: {bus_name} for object path: {object_path}"
                )
                return bus_name
        except Exception as e:
            self.logger.error(
                f"Error resolving service name for object path {object_path}: {e}"
            )
        return None

    @method()
    def RegisterStatusNotifierHost(self, service_name: "s"):  # pyright: ignore
        """Register a status notifier host."""
        self.logger.info(f"StatusNotifierHost registered: {service_name}")

    @dbus_property(access=PropertyAccess.READ)
    def RegisteredStatusNotifierItems(self) -> "as":  # pyright: ignore
        return [item[0] or item[1] for item in self._items]

    @dbus_property(access=PropertyAccess.READ)
    def IsStatusNotifierHostRegistered(self) -> "b":  # pyright: ignore
        return True

    @dbus_property(access=PropertyAccess.READ)
    def ProtocolVersion(self) -> "i":  # pyright: ignore
        return 0


class StatusNotifierItem(BasePlugin):
    """
    A proxy object that represents a single application's tray icon.
    It now includes logic for resilient initialization and D-Bus menu translation.
    """

    IFACES: typing.Final[typing.List[str]] = [
        "org.kde.StatusNotifierItem",
        "org.freedesktop.StatusNotifierItem",
    ]
    MAX_ATTEMPTS: typing.Final[int] = 10
    RETRY_DELAY: typing.Final[float] = 0.5

    def __init__(
        self,
        bus: MessageBus,
        service_name: str,
        object_path: str,
        panel_instance: typing.Any,
    ):
        """
        Initialize the StatusNotifierItem proxy.
        """
        super().__init__(panel_instance)
        self.bus: MessageBus = bus
        self.ipc_client = self.plugins["event_manager"].ipc_client
        self.service_name: str = service_name
        self.object_path: str = object_path
        self.icon_name: typing.Optional[str] = None
        self.icon_pixmap: typing.Optional[typing.Tuple] = None
        self.is_hidden: bool = False
        self.item: typing.Any = None
        self.proxy_object: typing.Any = None
        self.menu_object_path: str = ""
        self.menu_proxy: typing.Optional[DBusMenuProxy] = None

    async def broadcast_message(self, message: typing.Dict[str, typing.Any]):
        """
        Broadcast a custom message to all connected clients via the IPC server.
        """
        try:
            self.ipc_server.handle_msg(message)
        except Exception as e:
            self.logger.error(f"Failed to broadcast message: {e}")

    def get_new_icon_message(self) -> typing.Dict[str, typing.Any]:
        return {
            "event": "tray_icon_name_updated",
            "data": {
                "service_name": self.service_name,
                "object_path": self.object_path,
                "icon_name": self.icon_name,
                "icon_pixmap": self.icon_pixmap,
                "item": self.item,
                "bus": self.bus,
            },
        }

    async def on_new_tray_icon(self):
        """Callback for the NewIcon signal."""
        message = self.get_new_icon_message()
        await self.broadcast_message(message)

    async def _tray_icon_removed(self):
        message = {
            "event": "tray_icon_removed",
            "data": {
                "service_name": self.service_name,
                "object_path": self.object_path,
                "icon_name": self.icon_name,
            },
        }
        await self.broadcast_message(message)

    async def _is_service_name_valid(self) -> bool:
        """
        Checks if the D-Bus service name of this item is currently owned.
        """
        try:
            await self.bus.call(
                Message(
                    message_type=MessageType.METHOD_CALL,
                    destination="org.freedesktop.DBus",
                    interface="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    member="GetNameOwner",
                    signature="s",
                    body=[self.service_name],
                )
            )
            return True
        except DBusError as e:
            self.logger.info(
                f"D-Bus service {self.service_name} is no longer active: {e.__class__.__name__}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error during service validation for {self.service_name}: {e}"
            )
            return False

    async def initialize(self, broadcast: bool = True) -> bool:
        """
        Resilient initialization of the StatusNotifierItem proxy, with 10 retries.
        FIXED: Added check for D-Bus service ownership to prevent retrying stale names.
        """
        last_exception: typing.Optional[Exception] = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if not await self._is_service_name_valid():
                self.logger.info(
                    f"Aborting initialization for {self.service_name}. Service is no longer owned."
                )
                return False
            try:
                introspection = await self.bus.introspect(
                    self.service_name, self.object_path
                )
                self.proxy_object = self.bus.get_proxy_object(
                    self.service_name, self.object_path, introspection=introspection
                )
                self.item = None
                for interface in self.IFACES:
                    try:
                        self.item = self.proxy_object.get_interface(interface)
                        break
                    except Exception:
                        continue
                if not self.item:
                    raise ValueError("No matching StatusNotifierItem interface found.")
                self.icon_name = await self.item.get_icon_name()
                if hasattr(self.item, "get_icon_pixmap"):
                    self.icon_pixmap = await self.item.get_icon_pixmap()
                if broadcast:
                    await self.on_new_tray_icon()
                self.logger.info(
                    f"Initialized StatusNotifierItem for {self.service_name}{self.object_path} on attempt {attempt}"
                )
                return True
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Initialization attempt {attempt} failed for {self.service_name}{self.object_path}: {e.__class__.__name__}. Retrying...",
                )
            if attempt < self.MAX_ATTEMPTS:
                await asyncio.sleep(self.RETRY_DELAY)
            else:
                error_msg = f"Initialization failed after {self.MAX_ATTEMPTS} attempts."
                if last_exception:
                    error_msg += f" Last error: {last_exception.__class__.__name__}"
                self.logger.error(error_msg)
                return False
        return False

    async def get_context_menu_model(self) -> typing.Optional["typing.Any"]:
        """
        Fetches the 'Menu' property, connects to the com.canonical.dbusmenu service,
        and converts the proprietary structure into a standard Gio.MenuModel.
        """
        if not self.item:
            if not await self.initialize(broadcast=False):
                return None
        if not self.menu_object_path:
            try:
                menu_path: str = await self.item.get_menu()
                if not menu_path or menu_path == "/":
                    return None
                self.menu_object_path = menu_path
            except Exception as e:
                self.logger.error(
                    f"Failed to fetch 'Menu' property for {self.service_name}: {e}"
                )
                return None
        if self.menu_object_path and not self.menu_proxy:
            self.menu_proxy = DBusMenuProxy(
                self.bus, self.service_name, self.menu_object_path, self.logger
            )
            if not await self.menu_proxy.initialize():
                self.menu_proxy = None
                return None
        if self.menu_proxy:
            dbus_menu_data = await self.menu_proxy.fetch_menu_layout()
            if dbus_menu_data is None:
                return None
            return dbus_menu_to_gio_model(dbus_menu_data)
        return None
