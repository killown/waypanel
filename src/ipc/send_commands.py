"""
Waypanel IPC Client Module.
This module provides a class to connect to a running Waypanel instance
via its UNIX domain socket and execute registered IPC commands (RPC).
Usage Example:
    from waypanel_ipc_client import WaypanelIpcClient, format_response
    client = WaypanelIpcClient()
    response = client.run_command("list_commands")
    format_response(response)
"""

import asyncio
import json
import os
import sys
from typing import Dict, List, Any


def get_socket_path() -> str:
    """
    Replicates the socket path derivation logic from the Waypanel EventServer.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    socket_name = "waypanel.sock"
    return os.path.join(runtime_dir, socket_name)


class Commands:
    """
    Client for communicating with the Waypanel IPC server over a UNIX domain socket.
    """

    def __init__(self, socket_path: str = None):  # pyright: ignore
        """
        Initializes the client.
        :param socket_path: Optional, explicitly set the socket path. Defaults to get_socket_path().
        """
        self.socket_path = socket_path if socket_path is not None else get_socket_path()

    async def _run_command_async(self, command: str, args: List[Any]) -> Dict[str, Any]:
        """
        [ASYNC] Connects to the Waypanel socket, sends an RPC command, and returns the response.
        """
        try:
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
        except FileNotFoundError:
            print(f"Error: Waypanel socket not found at {self.socket_path}")
            print("Ensure Waypanel is running and the socket exists.")
            return {
                "status": "error",
                "message": f"Socket not found at {self.socket_path}",
                "command": command,
            }
        except ConnectionRefusedError:
            print(f"Error: Connection refused by socket at {self.socket_path}")
            return {
                "status": "error",
                "message": "Connection refused.",
                "command": command,
            }
        except Exception as e:
            print(f"An unexpected connection error occurred: {e}")
            return {
                "status": "error",
                "message": f"Connection failed: {e}",
                "command": command,
            }
        request = {"command": command, "args": args}
        request_data = json.dumps(request).encode() + b"\n"
        try:
            writer.write(request_data)
            await writer.drain()
        except Exception as e:
            writer.close()
            await writer.wait_closed()
            return {
                "status": "error",
                "message": f"Failed to send data: {e}",
                "command": command,
            }
        try:
            response_data = await reader.readline()
            if not response_data:
                return {
                    "status": "error",
                    "message": "Connection closed by server before response.",
                    "command": command,
                }
            response_text = response_data.decode().strip()
            response = json.loads(response_text)
            if "command" not in response and response.get("status") == "ok":
                response["command"] = command
            return response
        except json.JSONDecodeError:
            return {
                "status": "error",
                "message": "Invalid JSON response from server.",
                "command": command,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to read/process response: {e}",
                "command": command,
            }
        finally:
            writer.close()
            await writer.wait_closed()

    def run_command(self, command: str, args: List[Any] = None) -> Dict[str, Any]:
        """
        [SYNC] Executes an IPC command synchronously by running the async loop.
        :param command: The IPC command name (e.g., 'get_status_data').
        :param args: A list of arguments for the command. Defaults to [].
        :return: The JSON response dictionary from the server.
        """
        if args is None:
            args = []
        return asyncio.run(self._run_command_async(command, args))


def format_response(response: Dict[str, Any]):
    """Formats and prints the response dictionary."""
    print("\n--- Response ---")
    if response.get("status") == "ok":
        print(f"✅ Status: {response['status'].upper()}")
        print(f"   Command: {response.get('command', 'N/A')}")
        data = response.get("data")
        if data:
            print("\n   Payload (Data):")
            print(json.dumps(data, indent=4))
        else:
            print("   Payload: (Empty)")
    elif response.get("status") == "error":
        print(f"❌ Status: {response['status'].upper()}")
        print(f"   Message: {response.get('message', 'Unknown Error')}")
        print(f"   Command: {response.get('command', 'N/A')}")
    else:
        print(f"⚠️ Unrecognized Response Format: {response}")
    print("----------------")


def main():
    """Entry point for command-line execution."""
    if len(sys.argv) < 2:
        print("Usage: python3 waypanel_ipc_client.py <command> [arg1 arg2 ...]")
        print("Use list_commands to get the available commands")
        sys.exit(1)
    command_to_run = sys.argv[1]
    command_args = sys.argv[2:]
    client = Commands()
    print(f"Attempting to connect to Waypanel at {client.socket_path}...")
    response = client.run_command(command_to_run, command_args)
    format_response(response)


if __name__ == "__main__":
    main()
