import socket
import orjson as json
from gi.repository import GLib
from typing import Any, Dict


class WayfireClientIPC:
    def __init__(self, handle_event, panel_instance):
        """Initialize the Wayfire IPC client for communication with the compositor.
        Sets up core components for socket communication and event handling,
        including initial configuration of the event buffer and socket state.

        Args:
            handle_event: Callback function to process incoming IPC events
            panel_instance: Reference to the main panel instance providing context
                           and access to shared resources like logger
        """

        self.obj = panel_instance
        self.logger = self.obj.logger
        self.client_socket = None
        self.source = None
        self.buffer = ""
        self.socket_path = None
        self.handle_event = handle_event
        GLib.timeout_add_seconds(3, self.is_connected)

    def is_connected(self):
        if not self.obj.ipc.is_connected():
            self.wayfire_events_setup(self.socket_path)

    def connect_socket(self, socket_path) -> None:
        """Establish a connection to the specified Unix domain socket.
        Sets up a UNIX socket connection and configures GLib IO watch for incoming data events.
        If connection fails, logs appropriate error messages and ensures socket cleanup.

        Args:
            socket_path: Path to the Unix socket file to connect to.

        Raises:
            FileNotFoundError: If the specified socket file does not exist.
            ConnectionRefusedError: If the server refuses the connection.
            Exception: For any other unexpected errors during connection setup.
        """
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

    def handle_socket_event(self, fd: socket.socket, condition: int) -> int:
        """Read from the socket and process events with improved error handling.

        Args:
            fd: The socket file descriptor to read from
            condition: The GLib.IO condition that triggered this callback

        Returns:
            int: GLib.SOURCE_CONTINUE (1) to keep watching or GLib.SOURCE_REMOVE (0) to stop
        """
        try:
            # Read data from socket
            chunk: str = fd.recv(1024).decode("utf-8", errors="replace")
            if not chunk:
                self.logger.warning("No data received from socket; removing source.")
                return GLib.SOURCE_REMOVE  # Remove source if no data is received

            self.buffer += chunk

            # Process complete events in buffer
            while "\n" in self.buffer:  # Assuming newline separates events
                event_str: str
                event_str, self.buffer = self.buffer.split("\n", 1)
                if event_str.strip():  # Ignore empty strings
                    try:
                        event: Dict[str, Any] = json.loads(event_str)
                        if hasattr(event, "get"):
                            self.process_event(event)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON decode error: {e}")
                        self.logger.debug(f"Failed to decode: {event_str}")

            return GLib.SOURCE_CONTINUE  # Continue receiving data

        except UnicodeDecodeError as e:
            self.logger.error(f"Unicode decode error: {e}")
            return GLib.SOURCE_CONTINUE  # Try to continue despite decode errors

        except socket.error as e:
            self.logger.error(f"Socket error: {e}")
            return GLib.SOURCE_REMOVE  # Remove on socket errors

        except Exception as e:
            self.logger.error(
                f"Unexpected error handling socket event: {e}", exc_info=True
            )
            return GLib.SOURCE_REMOVE  # Stop on unexpected errors

    def process_event(self, event) -> None:
        """Process an incoming event by forwarding it to the custom handle_event function.
        Args:
            event: A dictionary containing event data to be processed.
        """
        self.handle_event(event)  # Call the custom handle_event function

    def disconnect_socket(self) -> None:
        """Gracefully disconnect the Unix socket connection.
        Removes the GLib IO watch source if active and closes the client socket
        if it exists, ensuring proper cleanup of resources.
        """
        if self.source:
            self.source.remove()
        if self.client_socket:
            self.client_socket.close()

    def wayfire_events_setup(self, socket_path) -> None:
        """Set up event listeners for Wayfire IPC events by establishing a socket connection.
        Args:
            socket_path: Path to the Unix socket used for connecting to the Wayfire compositor.
        """
        self.connect_socket(socket_path)
