import os
import asyncio
import orjson as json
import time
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils

# Remove existing socket files
socket_paths = ['/tmp/waypanel.sock', '/tmp/waypanel-dockbar.sock', '/tmp/waypanel-utils.sock']
for path in socket_paths:
    if os.path.exists(path):
        os.remove(path)

# Initialize Wayfire socket and utils
sock = WayfireSocket()
utils = WayfireUtils(sock)
sock.watch()

# Thread pool for blocking operations
executor = ThreadPoolExecutor()

# Event queue for handling Wayfire events
event_queue = asyncio.Queue()

# Watchdog observer for monitoring wayfire.ini
class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def on_modified(self, event):
        if event.src_path == os.path.expanduser("~/.config/wayfire.ini"):
            self.callback()

def start_watchdog(callback):
    observer = Observer()
    event_handler = ConfigChangeHandler(callback)
    observer.schedule(event_handler, path=os.path.dirname(os.path.expanduser("~/.config/wayfire.ini")), recursive=False)
    observer.start()
    return observer

def reconnect_wayfire_socket():
    global sock, utils
    sock.close()
    sock = WayfireSocket()
    utils = WayfireUtils(sock)
    sock.watch()

def is_socket_active():
    if not sock.is_connected():
        try:
            reconnect_wayfire_socket()
        except Exception as e:
            print(f"Retrying in 10 seconds: {e}")
            time.sleep(10)
            return False
    return True

def read_events():
    while True:
        if not is_socket_active():
            continue

        try:
            event = sock.read_next_event()  # Blocking call
            asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
        except Exception as e:
            print(f"Skipping the event: {e}")
            continue

async def handle_event(clients):
    while True:
        event = await event_queue.get()
        serialized_event = json.dumps(event)
        # Broadcast the event to all connected clients
        for client in clients:
            try:
                client.write((serialized_event + b'\n'))
                await client.drain()
            except (ConnectionResetError, BrokenPipeError):
                clients.remove(client)  # Remove disconnected clients

async def handle_client(reader, writer, clients):
    clients.append(writer)
    try:
        while True:
            await asyncio.sleep(3600)  # Keep the client connection alive
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        clients.remove(writer)
        writer.close()
        await writer.wait_closed()

async def start_server(path, clients):
    server = await asyncio.start_unix_server(lambda r, w: handle_client(r, w, clients), path=path)
    async with server:
        await server.serve_forever()

async def main():
    clients = []
    servers = [start_server(path, clients) for path in socket_paths]
    
    # Start the event reader in a separate thread
    global loop
    loop = asyncio.get_running_loop()
    executor.submit(read_events)
    
    # Start the watchdog observer
    watchdog_observer = start_watchdog(reconnect_wayfire_socket)
    
    try:
        await asyncio.gather(*servers, handle_event(clients))
    finally:
        watchdog_observer.stop()
        watchdog_observer.join()

if __name__ == '__main__':
    asyncio.run(main())
