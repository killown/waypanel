import socket
import orjson as json
from gi.repository import GLib
from typing import Any, Dict, Optional


class WayfireClientIPC:
    def __init__(self, handle_event, panel_instance):
        """
        Initialize the Wayfire IPC client for communication with the compositor.

        Establishes an event-driven socket reader using GLib.

        Args:
            handle_event: Callback function to process incoming IPC events.
            panel_instance: Reference to the main panel instance.
        """
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.client_socket: Optional[socket.socket] = None
        self.source: Optional[int] = None
        # buffer must be bytes to handle partial multi-byte character streams correctly
        self.buffer: bytes = b""
        self.socket_path: Optional[str] = None
        self.handle_event = handle_event

        # Check connection status periodically
        GLib.timeout_add_seconds(3, self.is_connected)

    def is_connected(self) -> bool:
        """
        Checks connection status and attempts reconnection if necessary.
        """
        if not self.obj.ipc.is_connected():
            if self.socket_path:
                self.wayfire_events_setup(self.socket_path)
        return True

    def connect_socket(self, socket_path: str) -> None:
        """
        Establish a connection to the specified Unix domain socket.

        Args:
            socket_path: Path to the Unix socket file.
        """
        try:
            self.socket_path = socket_path
            self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.client_socket.connect(socket_path)
            self.client_socket.setblocking(
                False
            )  # Ensure non-blocking for GLib loop integration

            self.source = GLib.io_add_watch(
                self.client_socket,
                GLib.PRIORITY_DEFAULT,
                GLib.IO_IN,
                self.handle_socket_event,
            )
            self.logger.info(f"Successfully connected to Unix socket: {socket_path}")
        except FileNotFoundError:
            self.logger.error(f"Socket file not found: {socket_path}")
        except ConnectionRefusedError:
            self.logger.error(f"Connection refused by server: {socket_path}")
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to socket: {e}")
        finally:
            if not self.source and self.client_socket:
                self.client_socket.close()
                self.client_socket = None

    def handle_socket_event(self, fd: socket.socket, condition: int) -> int:
        """
        Reads raw bytes from the socket, buffers them, and extracts line-based JSON events.

        This method fixes the previous architectural flaw where partial multi-byte
        characters could be corrupted by premature decoding.

        Args:
            fd: The socket file descriptor.
            condition: The GLib.IO condition.

        Returns:
            int: GLib.SOURCE_CONTINUE (True) or GLib.SOURCE_REMOVE (False).
        """
        try:
            # Read raw bytes. 4096 is a standard page size, better for throughput than 1024.
            chunk: bytes = fd.recv(4096)

            if not chunk:
                self.logger.warning("Socket closed by peer; removing source.")
                return GLib.SOURCE_REMOVE

            self.buffer += chunk

            # Process all complete messages currently in the buffer
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)

                # strip() on bytes removes whitespace bytes like \r, \t, etc.
                line = line.strip()
                if not line:
                    continue

                try:
                    # Direct bytes-to-dict parsing via orjson (Zero-Copy optimization)
                    event: Dict[str, Any] = json.loads(line)
                    self.process_event(event)
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON decode error: {e}")
                    # Log the raw bytes for debugging, safely decoded
                    self.logger.debug(
                        f"Failed payload: {line.decode('utf-8', errors='replace')}"
                    )

            return GLib.SOURCE_CONTINUE

        except BlockingIOError:
            # Resource temporarily unavailable (normal in non-blocking mode)
            return GLib.SOURCE_CONTINUE

        except Exception as e:
            self.logger.error(f"Critical socket error: {e}", exc_info=True)
            return GLib.SOURCE_REMOVE

    def process_event(self, event: Dict[str, Any]) -> None:
        """
        Forward the processed event to the handler.
        """
        try:
            self.handle_event(event)
        except Exception as e:
            self.logger.error(f"Error in event handler callback: {e}")

    def disconnect_socket(self) -> None:
        """
        Gracefully disconnect and cleanup resources.
        """
        if self.source:
            GLib.source_remove(self.source)
            self.source = None

        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
            self.client_socket = None

        self.buffer = b""

    def wayfire_events_setup(self, socket_path: str) -> None:
        """
        Proxy method to initiate connection.
        """
        self.connect_socket(socket_path)
