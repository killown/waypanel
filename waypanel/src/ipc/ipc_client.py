import socket
import orjson as json
from gi.repository import GLib


class WayfireClientIPC:
    def __init__(self, handle_event, panel_instance):
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.client_socket = None
        self.source = None
        self.buffer = ""
        self.socket_path = None
        self.handle_event = handle_event  # Store the custom handle_event function

    def connect_socket(self, socket_path):
        try:
            self.socket_path = socket_path
            self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.client_socket.connect(socket_path)
            self.source = GLib.io_add_watch(
                self.client_socket,
                GLib.PRIORITY_DEFAULT,
                GLib.IO_IN,
                self.handle_socket_event,
            )
            self.logger.info("Successfully connected to the Unix socket.")
        except FileNotFoundError:
            self.logger.error(f"Socket file not found: {socket_path}")
        except ConnectionRefusedError:
            self.logger.error("Connection refused by the server.")
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to socket: {e}")
        finally:
            if "self.client_socket" in locals() and self.client_socket:
                self.client_socket.close()

    def handle_socket_event(self, fd, condition):
        """Read from the socket and process events with improved error handling."""
        try:
            chunk = fd.recv(1024).decode("utf-8", errors="replace")
            if not chunk:
                self.logger.warning("No data received from socket; removing source.")
                return GLib.SOURCE_REMOVE  # Remove source if no data is received

            self.buffer += chunk

            # Process the complete events in the buffer
            while "\n" in self.buffer:  # Assuming newline separates events
                event_str, self.buffer = self.buffer.split("\n", 1)
                if event_str.strip():  # Ignore empty strings
                    try:
                        event = json.loads(event_str)
                        self.process_event(event)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON decode error: {e}")
            return GLib.SOURCE_CONTINUE  # Continue receiving data
        except UnicodeDecodeError as e:
            self.logger.error(f"Unicode decode error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error handling socket event: {e}")
            return (
                GLib.SOURCE_REMOVE
            )  # Stop receiving data if an unexpected error occurs

    def process_event(self, event):
        self.handle_event(event)  # Call the custom handle_event function

    def disconnect_socket(self):
        if self.source:
            self.source.remove()
        if self.client_socket:
            self.client_socket.close()

    def wayfire_events_setup(self, socket_path):
        self.connect_socket(socket_path)
