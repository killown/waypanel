import os
import asyncio
import orjson as json
import time
from concurrent.futures import ThreadPoolExecutor
from src.core.compositor.ipc import IPC
from src.plugins.core._event_loop import global_loop


class EventServer:
    """
    The goal of this additional IPC server:
    is to handle compositor IPC issues and prevent code from hanging.
    """

    def __init__(self, logger):
        self.logger = logger
        self.ipcet_paths = [
            self.get_socket_path(),
        ]
        self._cleanup_sockets()
        self.ipc = IPC()
        self.ipc.watch()

        self.executor = ThreadPoolExecutor()
        self.event_queue = asyncio.Queue()
        self.clients = []
        self.event_subscribers = {}
        self.loop = global_loop

    def _cleanup_sockets(self) -> None:
        """Remove existing socket files"""
        for path in self.ipcet_paths:
            if os.path.exists(path):
                os.remove(path)

    def reconnect_wayfire_socket(self) -> None:
        """Reconnect to Wayfire socket"""
        self.logger.info("reconnecting wayfire ipc")
        self.ipc.close()
        self.ipc.watch()

    def is_socket_active(self) -> bool:
        """Check if socket is connected, reconnect if not"""
        if not self.ipc.is_connected():
            try:
                self.reconnect_wayfire_socket()
            except Exception as e:
                self.logger.error(f"Retrying in 10 seconds: {e}")
                time.sleep(10)
                return False
        return True

    # FIXME: need to move this function for some new file
    def sway_translate_ipc(self, ev):
        translated_signal = None
        event = None
        if "container" in ev:
            if (
                ev["container"]["type"] == "con"
                or ev["container"]["type"] == "floating_con"
            ):
                if ev["change"] == "focus":
                    translated_signal = "view-focused"
                    event = {"event": translated_signal, "view": ev["container"]}
                if ev["change"] == "new":
                    translated_signal = "view-mapped"
                    event = {"event": translated_signal, "view": ev["container"]}
                if ev["change"] == "title":
                    translated_signal = "view-title-changed"
                    event = {"event": translated_signal, "view": ev["container"]}
                if ev["change"] == "close":
                    translated_signal = "view-closed"
                    event = {"event": translated_signal, "view": ev["container"]}

        if "old" in ev:
            if ev["change"] == "focus" and ev["old"] is not None:
                if ev["old"]["type"] == "workspace":
                    translated_signal = "workspace-lose-focus"
                    event = {"event": translated_signal, "workspace": ev["old"]}
        return event

    def read_events(self) -> None:
        """Read events from Wayfire socket in background thread"""
        while True:
            if not self.is_socket_active():
                continue

            try:
                event = self.ipc.read_next_event()

                # translate events from sway ipc
                if "change" in event:
                    event = self.sway_translate_ipc(event)

                if self.loop and not self.loop.is_closed():
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.event_queue.put(event), self.loop
                        )
                    except RuntimeError as e:
                        if "This event loop is closed" in str(e):
                            self.logger.warning(
                                "Event loop is closed. Cannot put event in queue."
                            )
                        else:
                            raise
                else:
                    self.logger.warning(
                        "Event loop not available or already closed. Skipping event."
                    )
            except Exception as e:
                self.logger.error(f"Event read failed: {e}")
                if not self.ipc.is_connected():
                    time.sleep(1)
                    continue

    def add_event_subscriber(self, event_type, callback) -> None:
        """
        Add a subscriber for a specific event type.
        Args:
            event_type (str): The type of event to subscribe to.
            callback (function): The callback to invoke when the event occurs.
        """
        if event_type not in self.event_subscribers:
            self.event_subscribers[event_type] = []
        self.event_subscribers[event_type].append(callback)
        self.logger.info(f"new event: {event_type}")

    def handle_msg(self, msg) -> None:
        # Notify subscribers for the specific event type
        event_type = msg.get("event")
        if event_type in self.event_subscribers:
            for callback in self.event_subscribers[event_type]:
                try:
                    # Execute the callback asynchronously
                    asyncio.create_task(callback(msg))
                    self.logger.debug(f"Invoked callback for event: {event_type}")
                except Exception as e:
                    self.logger.error(
                        f"Error executing callback for event '{event_type}': {e}"
                    )
        else:
            self.logger.debug(f"No subscribers for event: {event_type}")

    async def handle_event(self) -> None:
        """
        Process and broadcast events to connected clients.
        Also invoke callbacks for subscribed event types.
        """
        while True:
            # Get the next event from the queue
            event = await self.event_queue.get()

            # Serialize the event to JSON
            serialized_event = json.dumps(event) + b"\n"

            # Broadcast the serialized event to all connected clients
            for client in self.clients[:]:  # Iterate over a copy of the list
                try:
                    client.write(serialized_event)
                    await client.drain()
                except (ConnectionResetError, BrokenPipeError):
                    # Remove disconnected clients
                    self.clients.remove(client)
                    self.logger.warning("Removed disconnected client during broadcast.")

            # Notify subscribers for the specific event type
            if event:
                event_type = event.get("event")
                if event_type in self.event_subscribers:
                    for callback in self.event_subscribers[event_type]:
                        try:
                            # Execute the callback asynchronously
                            asyncio.create_task(callback(event))
                            self.logger.debug(
                                f"Invoked callback for event: {event_type}"
                            )
                        except Exception as e:
                            self.logger.error(
                                f"Error executing callback for event '{event_type}': {e}"
                            )
            else:
                self.logger.debug(f"No subscribers for event: {event}")

    async def handle_client(self, reader, writer) -> None:
        """Manage individual client connections"""
        self.clients.append(writer)
        try:
            while True:
                await asyncio.sleep(3600)  # Keep connection alive
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.clients.remove(writer)
            writer.close()
            await writer.wait_closed()

    async def start_server(self, path) -> None:
        """Start UNIX socket server on specified path"""
        server = await asyncio.start_unix_server(
            lambda r, w: self.handle_client(r, w), path=path
        )
        async with server:
            await server.serve_forever()

    async def main(self) -> None:
        """Main server entry point"""
        servers = [self.start_server(path) for path in self.ipcet_paths]
        self.loop = asyncio.get_running_loop()
        self.executor.submit(self.read_events)

        try:
            await asyncio.gather(*servers, self.handle_event())
        finally:
            # Cleanup logic if needed
            pass

    async def broadcast_message(self, message) -> None:
        """
        Broadcast a custom message to all connected clients.
        Args:
            message (dict): The message to broadcast.
        """
        serialized_message = json.dumps(message) + b"\n"
        for client in self.clients[:]:  # Iterate over a copy of the list
            try:
                await client.write(serialized_message)
                await client.drain()
            except (ConnectionResetError, BrokenPipeError):
                self.clients.remove(client)
                self.logger.warning("Removed disconnected client during broadcast.")

    def get_socket_path(self) -> str:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        socket_name = "waypanel.sock"
        return os.path.join(runtime_dir, socket_name)
