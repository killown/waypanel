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
from dbus_fast.aio import MessageBus
from dbus_fast import Message, introspection
from dbus_fast.constants import MessageType
from dbus_fast.service import ServiceInterface, dbus_property, signal, method
from dbus_fast import (
    InterfaceNotFoundError,
    InvalidBusNameError,
    InvalidObjectPathError,
)
from dbus_fast import Variant, DBusError, BusType, PropertyAccess
from dbus_fast.introspection import Node
import asyncio
from typing import List

from gi.repository import GLib, Gtk
from waypanel.src.plugins.core.event_loop import global_loop
from waypanel.src.plugins.core._base import BasePlugin

# XML Introspection Data for StatusNotifierItem
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
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.items = {}
        self._on_item_added = []
        self._on_item_removed = []

    async def register_item(self, bus, service_name: str, object_path: str):
        try:
            item = StatusNotifierItem(bus, service_name, object_path, self.obj)
            self.items[service_name] = item
            success = await item.initialize()
            if success:
                for callback in self._on_item_added:
                    callback(item)
            else:
                print(
                    f"Failed to initialize StatusNotifierItem for {service_name}{object_path}"
                )
        except Exception as e:
            print(f"Error registering item for {service_name}{object_path}: {e}")

    def unregister_item(self, service_name: str):
        """
        Unregister a StatusNotifierItem and clean up resources.
        Args:
            service_name (str): The D-Bus service name of the tray icon.
        """
        print(self.items, "remove")
        if service_name in self.items:
            item = self.items.pop(service_name, None)
            if item:
                print(f"Removing tray icon for service: {service_name}")
                # Notify subscribers by invoking their callbacks
                for callback in self._on_item_removed:
                    try:
                        callback(item)
                    except Exception as e:
                        print(
                            f"Error invoking removal callback for {service_name}: {e}"
                        )
            else:
                print(f"No tray icon found for service: {service_name}")
        else:
            print(f"Service not registered: {service_name}")


class StatusNotifierWatcher(ServiceInterface):
    def __init__(self, service: str, panel_instance):
        super().__init__(service)
        self.host = StatusNotifierHost(panel_instance)
        self.obj = panel_instance
        self.loop = global_loop
        self.newest_service_name = None
        self._items: list[tuple[str, str]] = []  # List of (service_name, object_path)
        self.bus = None  # Initialize the bus attribute here
        self.on_item_added = None
        self.object_path_to_bus_name = {}  # New dictionary to store mappings
        self.on_item_removed = None
        self.status_notifier_item = None
        self.watcher = None
        self.service = service
        self.service_name_to_object_path = {}  # Map service names to object paths

    def run_server_in_background(self, panel_instance):
        watcher = None
        from waypanel.src.plugins._status_notifier_server import (
            StatusNotifierWatcher,
            StatusNotifierItem,
        )

        async def _run_server(panel_instance):
            bus_name = "org.kde.StatusNotifierWatcher"
            watcher = StatusNotifierWatcher(bus_name, self.obj)
            bus = await watcher.setup()
            bus.export("/StatusNotifierWatcher", watcher)
            await bus.request_name(bus_name)

            # Define callback for when an item is added
            async def on_item_added(service_name: str, object_path: str):
                self.status_notifier_item = StatusNotifierItem(
                    bus, service_name, object_path, panel_instance
                )
                success = await self.status_notifier_item.initialize()
                if success:
                    print(
                        f"Initialized StatusNotifierItem for {service_name}{object_path}"
                    )
                else:
                    print(
                        f"Failed to initialize StatusNotifierItem for {service_name}{object_path}"
                    )

            # Assign the callback
            watcher.on_item_added = on_item_added

            # Keep the event loop running
            while True:
                await asyncio.sleep(1)

        # Run in dedicated thread using the global loop
        def _start_loop():
            asyncio.set_event_loop(
                global_loop
            )  # Ensure the thread uses the global loop
            global_loop.run_until_complete(_run_server(panel_instance))

        import threading

        thread = threading.Thread(target=_start_loop, daemon=True)
        thread.start()
        return watcher  # Return the watcher instance

    async def setup(self):
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self.bus.add_message_handler(self.handle_message)
        # Add a listener for NameOwnerChanged signals
        self.bus.add_message_handler(self.handle_name_owner_changed)
        return self.bus

    def handle_name_owner_changed(self, message):
        """
        Handle the NameOwnerChanged signal.

        Args:
            message: The D-Bus message containing the NameOwnerChanged signal.
        """
        try:
            if message.member == "NameOwnerChanged":
                service_name, old_owner, new_owner = message.body
                # Extract the object path from the message body
                object_path = None
                raw_object_path = message.body[0] if message.body else None

                # Unwrap the Variant object if necessary
                if hasattr(raw_object_path, "value"):
                    object_path = raw_object_path.value
                else:
                    object_path = raw_object_path

                if object_path:
                    self.loop.create_task(
                        self.host.register_item(self.bus, service_name, object_path)
                    )
                print(
                    f"NameOwnerChanged: {service_name}, Old Owner: {old_owner}, New Owner: {new_owner}"
                )
                # If the new owner is empty, the service has been unregistered
                if not new_owner:
                    self.unregister_item(service_name)
                else:
                    # Update the mapping with the new owner
                    self.service_name_to_object_path[service_name] = new_owner
                    print(f"Updated service mapping: {service_name} -> {new_owner}")

        except Exception as e:
            print(f"Error handling NameOwnerChanged signal: {e}")

    def unregister_item(self, service_name: str):
        """
        Unregister a StatusNotifierItem and clean up resources.

        Args:
            service_name (str): The D-Bus service name of the tray icon.
        """
        # Check if the service is registered
        if service_name not in self.service_name_to_object_path:
            print(f"Service not registered: {service_name}")
            return

        # Remove the service from the dictionary
        object_path = self.service_name_to_object_path.pop(service_name, None)
        print(f"Removed service mapping: {service_name} -> {object_path}")

        # Call the host's unregister_item method
        self.host.unregister_item(service_name)

        # Handle cleanup asynchronously
        async def cleanup():
            try:
                # Create the StatusNotifierItem instance
                item = StatusNotifierItem(self.bus, service_name, object_path, self.obj)
                await item._tray_icon_removed()  # Await the coroutine
            except Exception as e:
                print(f"Error during cleanup for {service_name}: {e}")

        # Schedule the cleanup task in the event loop
        asyncio.create_task(cleanup())
        print(f"Removing tray icon for service: {service_name}")

    async def get_pid_for_service(self, service_name: str, bus) -> int:
        """
        Retrieve the PID of a D-Bus service using its unique name (e.g., :1.100).

        Args:
            service_name (str): The unique name of the D-Bus service.

        Returns:
            int: The PID of the service, or -1 if it cannot be retrieved.
        """
        try:
            # Call GetConnectionUnixProcessID directly using a low-level D-Bus message
            reply = await bus.call(
                Message(
                    message_type=MessageType.METHOD_CALL,
                    destination="org.freedesktop.DBus",
                    interface="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    member="GetConnectionUnixProcessID",
                    signature="s",  # Input: a string (service name)
                    body=[service_name],  # Pass the service name as the argument
                )
            )
            # Check if the reply is valid
            if reply.message_type == MessageType.METHOD_RETURN:
                pid = reply.body[0]  # Extract the PID from the reply
                return pid
            else:
                print(f"Failed to retrieve PID for {service_name}: Invalid reply")
                return -1

        except DBusError as e:
            print(f"DBus error while fetching PID for {service_name}: {e}")
            return -1  # Return -1 on error
        except Exception as e:
            print(f"Unexpected error while fetching PID for {service_name}: {e}")
            return -1  # Return -1 on error

    @signal()
    def StatusNotifierItemRegistered(self, service_name: "s"):
        print(f"Tray icon registered: {service_name}")

    @signal()
    def StatusNotifierItemUnregistered(self, service_and_path: "s") -> "s":
        """
        Signal emitted when a StatusNotifierItem is unregistered.
        Args:
            service_and_path (str): A string containing the service name and object path.
        """
        print(f"StatusNotifierItem unregistered: {service_and_path}")
        return service_and_path

    def handle_message(self, message):
        try:
            # Extract the object path from the message body
            raw_object_path = message.body[0] if message.body else None
            sender_bus_name = message.sender

            # Unwrap the Variant object if necessary
            if hasattr(raw_object_path, "value"):
                object_path = raw_object_path.value
            else:
                object_path = raw_object_path

            # Validate the object path and sender bus name
            if (
                not isinstance(object_path, str)
                or not sender_bus_name
                or not object_path.startswith("/")
            ):
                return

            # Skip system-specific services
            if sender_bus_name == "org.freedesktop.DBus":
                print(f"Ignoring system-specific service: {sender_bus_name}")
                return

            # Store the mapping of object_path to sender_bus_name
            self.object_path_to_bus_name[object_path] = sender_bus_name
            print(f"Stored mapping: {object_path} -> {sender_bus_name}")

            # Handle Ayatana-specific paths
            if object_path.startswith("/org/ayatana/NotificationItem"):
                print(f"Ayatana indicator detected: {sender_bus_name} at {object_path}")
                object_path = f"{object_path}/Menu"

        except Exception as e:
            print(f"Error handling DBus message: {e}")

    @method()
    async def RegisterStatusNotifierItem(self, service_or_path: "s"):
        if not service_or_path:
            print("No service or path provided. Ignoring registration.")
            return

        # Skip invalid or system-specific services
        if service_or_path == "org.freedesktop.DBus":
            print(f"Ignoring invalid registration: {service_or_path}")
            return

        if service_or_path.startswith(":"):  # It's a service name
            service_name = service_or_path
            object_path = "/StatusNotifierItem"
        else:  # It's an object path
            service_name = None
            object_path = service_or_path

        # Resolve the bus name if only the object path is provided
        if service_name is None:
            bus_name = await self.resolve_service_name_for_object_path(object_path)
            if not bus_name:
                print(f"Failed to resolve bus name for object path: {object_path}")
                return
            service_name = bus_name

        # Add the service-object path mapping
        self.service_name_to_object_path[service_name] = object_path

        # Create a StatusNotifierItem instance
        try:
            item = StatusNotifierItem(self.bus, service_name, object_path, self.obj)
            success = await item.initialize()
            if not success:
                print(
                    f"Failed to initialize StatusNotifierItem for {service_name}{object_path}"
                )
                return

            # Add the item to the list and emit the registered signal
            await self.host.register_item(self.bus, service_name, object_path)
            self.StatusNotifierItemRegistered(f"{service_name}  {object_path}")
        except Exception as e:
            print(
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
            # Check if the object_path exists in the dictionary
            if object_path in self.object_path_to_bus_name:
                bus_name = self.object_path_to_bus_name[object_path]
                print(
                    f"Resolved service name from dictionary: {bus_name} for object path: {object_path}"
                )
                return bus_name

            # Fallback to introspection if not found in the dictionary
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

            if reply.message_type == MessageType.METHOD_RETURN:
                bus_name = reply.body[0]
                self.object_path_to_bus_name[object_path] = bus_name
                print(
                    f"Resolved service name via introspection: {bus_name} for object path: {object_path}"
                )
                return bus_name
        except Exception as e:
            print(f"Error resolving service name for object path {object_path}: {e}")
        return None

    @method()
    def RegisterStatusNotifierHost(self, service_name: "s"):
        """Register a status notifier host."""
        print(f"StatusNotifierHost registered: {service_name}")

    @dbus_property(access=PropertyAccess.READ)
    def RegisteredStatusNotifierItems(self) -> "as":
        return [item[0] or item[1] for item in self._items]

    @dbus_property(access=PropertyAccess.READ)
    def IsStatusNotifierHostRegistered(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def ProtocolVersion(self) -> "i":
        return 0

    @signal()
    def StatusNotifierItemRegistered(self, service_and_path: "s") -> "s":
        return service_and_path

    @signal()
    def StatusNotifierItemUnregistered(self, service_and_path: "s") -> "s":
        print(f"StatusNotifierItem unregistered: {service_and_path}")
        return service_and_path


class StatusNotifierItem(BasePlugin):
    def __init__(self, bus, service_name: str, object_path: str, panel_instance):
        super().__init__(panel_instance)
        self.watcher = StatusNotifierWatcher(service_name, panel_instance)
        self.bus = bus
        self.ipc_client = self.plugins["event_manager"].ipc_client
        self.service_name = service_name
        self.object_path = object_path
        self.icon_name = None
        self.is_hidden = False  # Track the window's visibility state

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
                "item": self.item,
                "bus": self.bus,
            },
        }

    async def on_new_tray_icon(self):
        """
        Callback for the NewIcon signal.
        """
        # Broadcast the updated icon name via the IPC server
        message = self.get_new_icon_message()
        await self.broadcast_message(message)

    async def _tray_icon_removed(self):
        # Broadcast the removed icon name via the IPC server
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
        try:
            # Proceed with normal initialization
            introspection = await self.bus.introspect(
                self.service_name, self.object_path
            )
            self.proxy_object = self.bus.get_proxy_object(
                self.service_name, self.object_path, introspection=introspection
            )

            # Try to find matching interface
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
                self.logger.warning("No valid interface found.")
                return False

            # Fetch icon name and broadcast
            try:
                self.icon_name = await self.item.get_icon_name()
                if broadcast:
                    await self.on_new_tray_icon()
            except Exception as e:
                self.logger.error(f"Failed to fetch IconName: {e}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize StatusNotifierItem: {e}")
            return False
