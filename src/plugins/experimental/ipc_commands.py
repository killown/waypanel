def get_plugin_metadata(panel_instance):
    about = "Registers IPC commands for remote debugging and status inspection."

    return {
        "id": "org.waypanel.plugin.ipc_commands",
        "name": "Developer IPC Data Exporter",
        "version": "1.0.0",
        "enabled": True,
        "index": 99,
        "priority": 99,
        "description": about,
    }


def get_plugin_class():
    import time
    from typing import Any
    from src.plugins.core._base import BasePlugin

    class _DevDataStore:
        def get_config_data(self, config_object):
            """Returns the actual loaded configuration data."""
            if hasattr(config_object, "as_dict"):
                return config_object.as_dict()
            elif isinstance(config_object, dict):
                return dict(config_object)
            return {
                "version": "Unknown",
                "log_level": "DEBUG",
                "modules_raw": str(config_object),
            }

        def get_plugin_data(self, plugins: dict):
            return list(plugins.keys())

        def get_status_data(self, ipc_server: Any):
            """Returns runtime status based on available ipc_server attributes."""
            return {
                "ipc_socket": ipc_server.get_socket_path()
                if hasattr(ipc_server, "get_socket_path")
                else "Unknown",
                "clients_connected": len(ipc_server.clients)
                if hasattr(ipc_server, "clients")
                else 0,
                "current_timestamp": int(time.time()),
                "wayfire_connected": ipc_server.is_socket_active()
                if hasattr(ipc_server, "is_socket_active")
                else False,
            }

    class DevIpcPlugin(BasePlugin):
        """
        background plugin that registers commands to expose internal state via IPC.
        """

        def __init__(self, panel_instance: Any):
            super().__init__(panel_instance)
            self.data_store = _DevDataStore()
            self._panel_instance = panel_instance

        def on_start(self):
            """Registers synchronous IPC commands when the panel starts."""
            if hasattr(self.ipc_server, "register_command"):
                self.ipc_server.register_command(
                    "get_config_data", self._handle_get_config
                )
                self.ipc_server.register_command(
                    "get_plugins_data", self._handle_get_plugins
                )
                self.ipc_server.register_command(
                    "get_status_data", self._handle_get_status
                )
                self.ipc_server.register_command(
                    "list_commands", self._handle_list_commands
                )
                self.ipc_server.register_command(
                    "plugin_control", self._handle_plugin_control
                )
                self.logger.info(
                    "Dev IPC commands registered successfully: get_config_data, get_plugins_data, get_status_data, list_commands, plugin_control"
                )
            else:
                self.logger.error(
                    "IPC server does not support 'register_command'. RPC commands cannot be exposed."
                )

        def _handle_get_config(self, args):
            """Handler for 'get_config_data' command: returns configuration data."""
            try:
                data = self._config_handler.config_data
                return {"status": "ok", "command": "get_config_data", "data": data}
            except Exception as e:
                self.logger.error(f"Error handling get_config_data: {e}")
                return {
                    "status": "error",
                    "command": "get_config_data",
                    "message": str(e),
                }

        def _handle_get_plugins(self, args):
            """Handler for 'get_plugins_data' command: returns loaded plugins."""
            try:
                data = self.data_store.get_plugin_data(self.plugins)
                return {"status": "ok", "command": "get_plugins_data", "data": data}
            except Exception as e:
                self.logger.error(f"Error handling get_plugins_data: {e}")
                return {
                    "status": "error",
                    "command": "get_plugins_data",
                    "message": str(e),
                }

        def _handle_get_status(self, args):
            """Handler for 'get_status_data' command: returns runtime status."""
            try:
                data = self.data_store.get_status_data(self.ipc_server)
                return {"status": "ok", "command": "get_status_data", "data": data}
            except Exception as e:
                self.logger.error(f"Error handling get_status_data: {e}")
                return {
                    "status": "error",
                    "command": "get_status_data",
                    "message": str(e),
                }

        def _handle_list_commands(self, args):
            """Handler for 'list_commands' command: returns a list of all registered IPC commands."""
            try:
                if hasattr(self.ipc_server, "command_handlers"):
                    commands = list(self.ipc_server.command_handlers.keys())
                    return {
                        "status": "ok",
                        "command": "list_commands",
                        "data": commands,
                    }
                else:
                    return {
                        "status": "error",
                        "command": "list_commands",
                        "message": "IPC Server does not expose command_handlers.",
                    }
            except Exception as e:
                self.logger.error(f"Error handling list_commands: {e}")
                return {
                    "status": "error",
                    "command": "list_commands",
                    "message": str(e),
                }

        def _handle_plugin_control(self, args):
            """Handler for 'plugin_control' command: enables or disables a plugin."""
            command_name = "plugin_control"
            if len(args) < 2:
                return {
                    "status": "error",
                    "command": command_name,
                    "message": "Missing arguments. Usage: [plugin_name, 'enable'/'disable']",
                }
            plugin_name = args[0]
            action = args[1].lower().strip()
            print(action, plugin_name)
            if action not in ["enable", "disable"]:
                return {
                    "status": "error",
                    "command": command_name,
                    "message": f"Invalid action '{action}'. Must be 'enable' or 'disable'.",
                }
            try:
                plugin_loader = self._panel_instance.plugin_loader
                metadata = plugin_loader.plugin_metadata_map[plugin_name]["metadata"]
                print(metadata)
                if action == "disable":
                    plugin_loader.disable_plugin(plugin_name)
                else:
                    plugin_loader.enable_plugin(plugin_name, metadata)
                return {
                    "status": "ok",
                    "command": command_name,
                    "data": f"Plugin '{plugin_name}' successfully set to state '{action}'.",
                }
            except Exception as e:
                self.logger.error(
                    f"Error handling {command_name} for {plugin_name}: {e}"
                )
                return {
                    "status": "error",
                    "command": command_name,
                    "message": str(e),
                }

        async def on_stop(self):
            """Cleanup IPC handlers if needed (optional, depends on core design)."""
            self.logger.info("DevIpcPlugin stopping.")

    return DevIpcPlugin
