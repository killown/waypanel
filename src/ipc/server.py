import os
import asyncio
import orjson as json
import time
from concurrent.futures import ThreadPoolExecutor
from src.core.compositor.ipc import IPC
from src.plugins.core._event_loop import global_loop
from src.ipc.utils import translate_ipc


class EventServer:
    def __init__(self, logger):
        self.logger = logger
        self.ipcet_paths = [
            self.get_socket_path(),
        ]
        self._cleanup_sockets()
        self.ipc = IPC()
        self.ipc.watch()
        self.compositor = None
        self.executor = ThreadPoolExecutor()
        self.event_queue = asyncio.Queue()
        self.clients = []
        self.event_subscribers = {}
        self.command_handlers = {}
        self.loop = global_loop

    def _cleanup_sockets(self) -> None:
        for path in self.ipcet_paths:
            if os.path.exists(path):
                os.remove(path)

    def reconnect_wayfire_socket(self) -> None:
        self.logger.info("reconnecting wayfire ipc")
        self.ipc = IPC()
        self.ipc.watch()
        self.ipc.connect_client(self.get_socket_path())
        self.ipc.watch()

    def is_socket_active(self) -> bool:
        if not self.ipc.is_connected():
            try:
                self.reconnect_wayfire_socket()
            except Exception as e:
                self.logger.error(f"Retrying in 10 seconds: {e}")
                time.sleep(10)
                return False
        return True

    def read_events(self) -> None:
        while True:
            if not self.is_socket_active():
                continue
            try:
                event = self.ipc.read_next_event()
                event = translate_ipc(event, self)
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
                try:
                    self.reconnect_wayfire_socket()
                except Exception as e:
                    self.logger.error(f"Retrying in 1 second: {e}")
                time.sleep(1)
                continue

    def register_command(self, command_name: str, handler) -> None:
        if command_name in self.command_handlers:
            self.logger.warning(f"Overwriting IPC command handler for: {command_name}")
        self.command_handlers[command_name] = handler
        self.logger.info(f"IPC command registered: {command_name}")

    def add_event_subscriber(self, event_type, callback) -> None:
        if event_type not in self.event_subscribers:
            self.event_subscribers[event_type] = []
        self.event_subscribers[event_type].append(callback)
        self.logger.info(f"new event: {event_type}")

    def handle_msg(self, msg) -> None:
        event_type = msg.get("event")
        self.logger.warning(msg)
        if event_type in self.event_subscribers:
            for callback in self.event_subscribers[event_type]:
                try:
                    asyncio.create_task(callback(msg))
                    self.logger.debug(f"Invoked callback for event: {event_type}")
                except Exception as e:
                    self.logger.error(
                        f"Error executing callback for event '{event_type}': {e}"
                    )
        else:
            self.logger.debug(f"No subscribers for event: {event_type}")

    async def handle_event(self) -> None:
        while True:
            event = await self.event_queue.get()
            serialized_event = json.dumps(event) + b"\n"
            for client in self.clients[:]:
                try:
                    client.write(serialized_event)
                    await client.drain()
                except (ConnectionResetError, BrokenPipeError):
                    self.clients.remove(client)
                    self.logger.warning("Removed disconnected client during broadcast.")
            if event:
                event_type = event.get("event")
                if event_type in self.event_subscribers:
                    for callback in self.event_subscribers[event_type]:
                        try:
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
        self.clients.append(writer)
        try:
            while True:
                message = {}
                raw_data = await reader.readline()
                if not raw_data:
                    break
                if not raw_data.strip():
                    continue
                response = {}
                try:
                    message = json.loads(raw_data)
                except Exception as e:
                    self.logger.error(f"Failed to parse client IPC message: {e}")
                    response = {"status": "error", "message": "Invalid JSON format."}
                command = message.get("command")
                args = message.get("args", [])
                if command:
                    if command in self.command_handlers:
                        self.logger.debug(f"Handling IPC command: {command}")
                        handler = self.command_handlers[command]
                        try:
                            response = handler(args)
                        except Exception as e:
                            self.logger.error(
                                f"Error executing command '{command}': {e}"
                            )
                            response = {
                                "status": "error",
                                "command": command,
                                "message": f"Handler error: {e}",
                            }
                    else:
                        response = {
                            "status": "error",
                            "command": command,
                            "message": f"Unknown command: {command}",
                        }
                if response:
                    if isinstance(response, dict):
                        response_bytes = json.dumps(response) + b"\n"
                        writer.write(response_bytes)
                        await writer.drain()
                    else:
                        self.logger.error(
                            f"Handler for {command} did not return a dictionary."
                        )
                        error_resp = {
                            "status": "error",
                            "command": command,
                            "message": "Server error: Handler did not return valid format.",
                        }
                        writer.write(json.dumps(error_resp) + b"\n")
                        await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            if writer in self.clients:
                self.clients.remove(writer)
            writer.close()
            await writer.wait_closed()

    async def start_server(self, path) -> None:
        server = await asyncio.start_unix_server(
            lambda r, w: self.handle_client(r, w), path=path
        )
        async with server:
            await server.serve_forever()

    async def main(self) -> None:
        servers = [self.start_server(path) for path in self.ipcet_paths]
        self.loop = asyncio.get_running_loop()
        self.executor.submit(self.read_events)
        try:
            await asyncio.gather(*servers, self.handle_event())
        finally:
            pass

    async def broadcast_message(self, message) -> None:
        serialized_message = json.dumps(message) + b"\n"
        for client in self.clients[:]:
            try:
                client.write(serialized_message)
                await client.drain()
            except (ConnectionResetError, BrokenPipeError):
                self.clients.remove(client)
                self.logger.warning("Removed disconnected client during broadcast.")

    def get_socket_path(self) -> str:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        socket_name = "waypanel.sock"
        return os.path.join(runtime_dir, socket_name)
