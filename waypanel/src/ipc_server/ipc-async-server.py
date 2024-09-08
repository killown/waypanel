import asyncio
import os
import orjson as json
import time
from concurrent.futures import ThreadPoolExecutor
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils


#why forward ipc for socket files, why not just one?
#because this is the most reliable way to provide ipc through GLib which in rare cases the code would break/hang
#this is the best choice until there is a more reliable way to provide IPC without breaking the GTK main loop with freezing issues.

socket_paths = ['/tmp/waypanel.sock', '/tmp/waypanel-dockbar.sock', '/tmp/waypanel-utils.sock']

for path in socket_paths:
    if os.path.exists(path):
        os.remove(path)

sock = WayfireSocket()
utils = WayfireUtils(sock)
sock.watch()

executor = ThreadPoolExecutor()

event_queue = asyncio.Queue()


def reconnect_wayfire_socket():
    sock = WayfireSocket()
    utils = WayfireUtils(sock)
    sock.watch()

def is_socket_active():
    if not sock.is_connected():
        try:
            reconnect_wayfire_socket()
        except Exception as e:
            print(f"retrying in 10 seconds: {e}")
            time.sleep(10)
            return False
    return True

def read_events():
    while True:
        if not is_socket_active():
            continue

        try:
            event = sock.read_next_event()  # blocking call
            asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
        except Exception as e:
            print(f"skiping the event: {e}")
            continue

# handle events and send them to connected clients
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
                clients.remove(client)  # Remove clients that have disconnected

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

# start a server for a given path
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
    await asyncio.gather(*servers, handle_event(clients))

if __name__ == '__main__':
    asyncio.run(main())

