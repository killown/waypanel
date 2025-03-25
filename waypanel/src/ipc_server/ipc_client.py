import socket

import orjson
from gi.repository import GLib


class WayfireClientIPC:
    def __init__(self, handle_event):
        self.client_socket = None
        self.source = None
        self.buffer = ""
        self.socket_path = None
        self.handle_event = handle_event  # Store the custom handle_event function

    def connect_socket(self, socket_path):
        self.socket_path = socket_path
        self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.client_socket.connect(socket_path)
        self.source = GLib.io_add_watch(self.client_socket, GLib.PRIORITY_DEFAULT, GLib.IO_IN, self.handle_socket_event)

    def handle_socket_event(self, fd, condition):
        # try decode before actually handle the event
        # if the code fail, glib will stop watching
        try:
            chunk = fd.recv(1024).decode()
            if not chunk:
                return GLib.SOURCE_REMOVE

            self.buffer += chunk

            while '\n' in self.buffer:
                event_str, self.buffer = self.buffer.split('\n', 1)
                if event_str:
                    try:
                        event = orjson.loads(event_str)
                        self.process_event(event)
                    except orjson.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
        except UnicodeDecodeError as e:
            print(f"{e}")

        return GLib.SOURCE_CONTINUE

    def process_event(self, event):
        self.handle_event(event)  # Call the custom handle_event function

    def disconnect_socket(self):
        if self.source:
            self.source.remove()
        if self.client_socket:
            self.client_socket.close()

    def wayfire_events_setup(self, socket_path):
        self.connect_socket(socket_path)
