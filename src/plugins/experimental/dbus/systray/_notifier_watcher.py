from dbus_fast.aio import MessageBus
from dbus_fast import Message
from dbus_fast.constants import MessageType
from dbus_fast.service import ServiceInterface, dbus_property, signal, method
from dbus_fast import Variant, DBusError, BusType, PropertyAccess
import asyncio
from typing import Dict
from src.plugins.core._event_loop import global_loop
from src.plugins.core._base import BasePlugin

SPEC = """
<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name='org.kde.StatusNotifierItem'>
    <annotation name="org.gtk.GDBus.C.Name" value="Item" />
    <method name='ContextMenu'>
      <arg type='i' direction='in' name='x'/>
      <arg type='i' direction='in' name='y'/>
    </method>
    <method name='Activate'>
      <arg type='i' direction='in' name='x'/>
      <arg type='i' direction='in' name='y'/>
    </method>
    <method name='SecondaryActivate'>
      <arg type='i' direction='in' name='x'/>
      <arg type='i' direction='in' name='y'/>
    </method>
    <method name='Scroll'>
      <arg type='i' direction='in' name='delta'/>
      <arg type='s' direction='in' name='orientation'/>
    </method>
    <signal name='NewTitle'/>
    <signal name='NewIcon'/>
    <signal name='NewAttentionIcon'/>
    <signal name='NewOverlayIcon'/>
    <signal name='NewToolTip'/>
    <signal name='NewStatus'>
      <arg type='s' name='status'/>
    </signal>
    <property name='Category' type='s' access='read'/>
    <property name='Id' type='s' access='read'/>
    <property name='Title' type='s' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='IconThemePath' type='s' access='read'/>
    <property name='IconName' type='s' access='read'/>
    <property name='IconPixmap' type='a(iiay)' access='read'/>
    <property name='OverlayIconName' type='s' access='read'/>
    <property name='OverlayIconPixmap' type='a(iiay)' access='read'/>
    <property name='AttentionIconName' type='s' access='read'/>
    <property name='AttentionIconPixmap' type='a(iiay)' access='read'/>
    <property name='AttentionMovieName' type='s' access='read'/>
    <property name='ToolTip' type='(sa(iiay)ss)' access='read'/>
    <property name='Menu' type='o' access='read'/>
    <property name='ItemIsMenu' type='b' access='read'/>
  </interface>
</node>
"""


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

    async def register_item(self, bus, service_name: str, object_path: str):
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
    It handles `NameOwnerChanged` signals and the `RegisterStatusNotifierItem`
    method call to detect when an icon becomes available.
    """

    def __init__(self, service: str, panel_instance):
        super().__init__(service)
        self.host = StatusNotifierHost(panel_instance)
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.loop = global_loop
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

    def run_server_in_background(self, panel_instance):
        watcher = None
        from ._notifier_watcher import (
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

        def _start_loop():
            asyncio.set_event_loop(global_loop)
            global_loop.run_until_complete(_run_server(panel_instance))

        import threading

        thread = threading.Thread(target=_start_loop, daemon=True)
        thread.start()
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

    async def get_pid_for_service(self, service_name: str, bus) -> int:
        """
        Retrieve the PID of a D-Bus service using its unique name.
        Args:
            service_name (str): The unique name of the D-Bus service.
        Returns:
            int: The PID of the service, or -1 if it cannot be retrieved.
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
            if reply.message_type == MessageType.METHOD_RETURN:
                pid = reply.body[0]
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
        Args:
            service_and_path (str): A string containing the service name and object path.
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
            item = StatusNotifierItem(self.bus, service_name, object_path, self.obj)
            success = await item.initialize()
            if not success:
                self.logger.warning(
                    f"Failed to initialize StatusNotifierItem for {service_name}{object_path}"
                )
                return
            await self.host.register_item(self.bus, service_name, object_path)
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
        Args:
            object_path (str): The object path to resolve.
        Returns:
            str | None: The current service name, or None if unresolved.
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
    It connects to the remote D-Bus object to fetch its properties
    (like icon and tooltip) and signals.
    """

    def __init__(self, bus, service_name: str, object_path: str, panel_instance):
        super().__init__(panel_instance)
        self.watcher = StatusNotifierWatcher(service_name, panel_instance)
        self.bus = bus
        self.ipc_client = self.plugins["event_manager"].ipc_client
        self.service_name = service_name
        self.object_path = object_path
        self.icon_name = None
        self.icon_pixmap = None
        self.is_hidden = False

    async def broadcast_message(self, message):
        """
        Broadcast a custom message to all connected clients via the IPC server.
        Args:
            message (dict): The message to broadcast.
        """
        try:
            self.ipc_server.handle_msg(message)
        except Exception as e:
            self.logger.error(f"Failed to broadcast message: {e}")

    def get_new_icon_message(self):
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

    async def initialize(self, broadcast=True) -> bool:
        for attempt in range(3):
            try:
                introspection = await self.bus.introspect(
                    self.service_name, self.object_path
                )
                self.proxy_object = self.bus.get_proxy_object(
                    self.service_name, self.object_path, introspection=introspection
                )
                ifaces = [
                    "org.kde.StatusNotifierItem",
                    "org.freedesktop.StatusNotifierItem",
                ]
                for interface in ifaces:
                    try:
                        self.item = self.proxy_object.get_interface(interface)
                        break
                    except Exception:
                        continue
                else:
                    if attempt < 2:
                        await asyncio.sleep(0.3)
                        continue
                    self.logger.warning("No valid interface found after retries.")
                    return False
                try:
                    self.icon_name = await self.item.get_icon_name()
                    if hasattr(self.item, "get_icon_pixmap"):
                        self.icon_pixmap = await self.item.get_icon_pixmap()
                    if broadcast:
                        await self.on_new_tray_icon()
                except Exception as e:
                    self.logger.error(f"Failed to fetch IconName: {e}")
                    return False
                return True
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize StatusNotifierItem (attempt {attempt + 1}): {e}"
                )
                if attempt < 2:
                    await asyncio.sleep(0.3)
                else:
                    self.logger.error(f"Initialization failed after 3 attempts: {e}")
                    return False
        return False

    def code_explanation(self):
        """
        This Python code is a D-Bus service that acts as a
        StatusNotifierHost, a role for managing modern system tray icons.
        It uses the 'dbus-fast' library for D-Bus communication.
        - **StatusNotifierWatcher**: The central service that listens for
          applications to register new tray icons. It handles
          `NameOwnerChanged` signals and the `RegisterStatusNotifierItem`
          method call to detect when an icon becomes available.
        - **StatusNotifierHost**: This class acts as a registry for all
          currently active tray icons. It adds or removes `StatusNotifierItem`
          objects and notifies other components of these changes.
        - **StatusNotifierItem**: A proxy object that represents a single
          application's tray icon. It connects to the remote D-Bus object
          to fetch its properties (like icon and tooltip) and signals.
        """
        return self.code_explanation.__doc__
