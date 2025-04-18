import os
import asyncio
import orjson as json
import time
from concurrent.futures import ThreadPoolExecutor
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils


class WayfireEventServer:
    """
    The goal of this additional IPC server:
    is to handle compositor IPC issues and prevent code from hanging.
    """

    def __init__(self):
        self.socket_paths = [
            "/tmp/waypanel.sock",
        ]
        self._cleanup_sockets()

        self.sock = WayfireSocket()
        self.utils = WayfireUtils(self.sock)
        self.sock.watch()

        self.executor = ThreadPoolExecutor()
        self.event_queue = asyncio.Queue()
        self.clients = []
        self.loop = None

    def _cleanup_sockets(self):
        """Remove existing socket files"""
        for path in self.socket_paths:
            if os.path.exists(path):
                os.remove(path)

    def reconnect_wayfire_socket(self):
        """Reconnect to Wayfire socket"""
        print("reconnecting wayfire ipc")
        self.sock.close()
        self.sock = WayfireSocket()
        self.utils = WayfireUtils(self.sock)
        self.sock.watch()

    def is_socket_active(self):
        """Check if socket is connected, reconnect if not"""
        if not self.sock.is_connected():
            try:
                self.reconnect_wayfire_socket()
            except Exception as e:
                print(f"Retrying in 10 seconds: {e}")
                time.sleep(10)
                return False
        return True

    def read_events(self):
        """Read events from Wayfire socket in background thread"""
        while True:
            if not self.is_socket_active():
                continue

            try:
                event = self.sock.read_next_event()
                asyncio.run_coroutine_threadsafe(self.event_queue.put(event), self.loop)
            except Exception as e:
                print(f"Event read failed: {e}")
                if not self.sock.is_connected():
                    time.sleep(1)
                    continue

    async def handle_event(self):
        """Process and broadcast events to connected clients"""
        while True:
            event = await self.event_queue.get()
            serialized_event = json.dumps(event)
            for client in self.clients:
                try:
                    client.write(serialized_event + b"\n")
                    await client.drain()
                except (ConnectionResetError, BrokenPipeError):
                    self.clients.remove(client)

    async def handle_client(self, reader, writer):
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

    async def start_server(self, path):
        """Start UNIX socket server on specified path"""
        server = await asyncio.start_unix_server(
            lambda r, w: self.handle_client(r, w), path=path
        )
        async with server:
            await server.serve_forever()

    async def main(self):
        """Main server entry point"""
        servers = [self.start_server(path) for path in self.socket_paths]
        self.loop = asyncio.get_running_loop()
        self.executor.submit(self.read_events)

        try:
            await asyncio.gather(*servers, self.handle_event())
        finally:
            # Cleanup logic if needed
            pass


if __name__ == "__main__":
    server = WayfireEventServer()
    asyncio.run(server.main())
