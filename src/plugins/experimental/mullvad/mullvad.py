import os
import random
import asyncio
import aiohttp
import json
from gi.repository import Gtk, Gio, GLib  # pyright: ignore
from src.plugins.core._base import BasePlugin
from ._mullvad_info import MullvadStatusDialog

ENABLE_PLUGIN = True
DEPS = ["top_panel", "network_manager"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-systray"
    order = 5
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the Mullvad plugin."""
    if ENABLE_PLUGIN:
        mullvad_plugin = MullvadPlugin(panel_instance)
        return mullvad_plugin


class MullvadPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.mullvad_version = None
        self.city_code = self.get_city_code()
        self.menubutton_mullvad = Gtk.MenuButton()
        self.status_label = None
        self.main_widget = (self.menubutton_mullvad, "append")

    def on_start(self):
        """Hook called when the plugin is initialized. Starts the async setup."""
        self.run_in_async_task(self._async_init_setup())

    def get_mullvad_version(self):
        """Retrieve the Mullvad version using the `mullvad --version` command."""
        try:
            version = os.popen("mullvad --version").read().strip()
            return version
        except Exception as e:
            self.logger.info(f"Error retrieving Mullvad version: {e}")
            return "Mullvad Version Unavailable"

    def get_city_code(self):
        """Get the city code from the plugin's config section in config.toml."""
        plugin_config = self.config_handler.config_data.get("plugins", {}).get(
            "mullvad", {}
        )
        return plugin_config.get("city_code", "sao")

    async def _async_init_setup(self):
        """
        Asynchronous setup for the plugin.
        """
        self.mullvad_version = await asyncio.to_thread(self.get_mullvad_version)
        self.icon_name = self.gtk_helper.icon_exist(
            "mullvad-tray-9", ["mullvad-vpn-symbolic", "mullvaddg"]
        )
        self.menubutton_mullvad.set_icon_name(self.icon_name)
        self.menubutton_mullvad.add_css_class("top_right_widgets")
        self.gtk_helper.add_cursor_effect(self.menubutton_mullvad)
        self.create_menu_model()
        if os.path.exists("/usr/bin/mullvad"):
            GLib.timeout_add(10000, self.update_vpn_status_async)

    def create_menu_model(self):
        """Create a Gio.Menu and populate it with options for Mullvad."""
        menu = Gio.Menu()
        connect_item = Gio.MenuItem.new("Connect", "app.connect")
        disconnect_item = Gio.MenuItem.new("Disconnect", "app.disconnect")
        status_item = Gio.MenuItem.new("Check Status", "app.status")
        random_item_city = Gio.MenuItem.new(
            f"Random {self.city_code.capitalize()} Relay", "app.random_city"
        )
        random_item_global = Gio.MenuItem.new(
            "Random Global Relay", "app.random_global"
        )
        menu.append_item(connect_item)
        menu.append_item(disconnect_item)
        menu.append_item(status_item)
        menu.append_item(random_item_city)
        menu.append_item(random_item_global)
        self.menubutton_mullvad.set_menu_model(menu)
        action_group = Gio.SimpleActionGroup()
        connect_action = Gio.SimpleAction.new("connect", None)
        disconnect_action = Gio.SimpleAction.new("disconnect", None)
        status_action = Gio.SimpleAction.new("status", None)
        random_action_city = Gio.SimpleAction.new("random_city", None)
        random_action_global = Gio.SimpleAction.new("random_global", None)
        connect_action.connect(
            "activate", lambda *args: self.run_in_async_task(self.connect_vpn())
        )
        disconnect_action.connect(
            "activate", lambda *args: self.run_in_async_task(self.disconnect_vpn())
        )
        status_action.connect("activate", self.check_status)
        random_action_city.connect(
            "activate",
            lambda *args: self.run_in_async_task(self.set_mullvad_relay_by_city()),
        )
        random_action_global.connect(
            "activate",
            lambda *args: self.run_in_async_task(
                self.set_mullvad_relay_random_global()
            ),
        )
        action_group.add_action(connect_action)
        action_group.add_action(disconnect_action)
        action_group.add_action(status_action)
        action_group.add_action(random_action_city)
        action_group.add_action(random_action_global)
        self.menubutton_mullvad.insert_action_group("app", action_group)
        self.popover_mullvad = Gtk.Popover()
        self.popover_mullvad.set_parent(self.menubutton_mullvad)
        self.popover_mullvad.set_has_arrow(False)
        self.create_popover_content()

    def create_popover_content(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        version_label = Gtk.Label(label=self.mullvad_version)  # pyright: ignore
        version_label.add_css_class("mullvad-header-label")
        vbox.append(version_label)
        self.status_label = Gtk.Label(label="Checking status...")
        vbox.append(self.status_label)
        vbox.append(Gtk.Separator())
        connect_button = Gtk.Button(label="Connect")
        connect_button.connect(
            "clicked", lambda *args: self.run_in_async_task(self.connect_vpn())
        )
        vbox.append(connect_button)
        disconnect_button = Gtk.Button(label="Disconnect")
        disconnect_button.connect(
            "clicked", lambda *args: self.run_in_async_task(self.disconnect_vpn())
        )
        vbox.append(disconnect_button)
        status_button = Gtk.Button(label="Check Status")
        status_button.connect("clicked", self.check_status)
        vbox.append(status_button)
        random_button_city = Gtk.Button(
            label=f"Random {self.city_code.capitalize()} Relay"
        )
        random_button_city.connect(
            "clicked",
            lambda *args: self.run_in_async_task(self.set_mullvad_relay_by_city()),
        )
        vbox.append(random_button_city)
        random_button_global = Gtk.Button(label="Random Global Relay")
        random_button_global.connect(
            "clicked",
            lambda *args: self.run_in_async_task(
                self.set_mullvad_relay_random_global()
            ),
        )
        vbox.append(random_button_global)
        self.popover_mullvad.set_child(vbox)

    def update_vpn_status_async(self):
        """Wrapper to call the async status update from GLib."""
        self.run_in_async_task(self.update_vpn_status())
        return True

    async def connect_vpn(self):
        """Connect to Mullvad VPN asynchronously."""
        self.logger.info("Connecting to Mullvad VPN...")
        await asyncio.create_subprocess_exec("mullvad", "connect")
        self.notifier.notify_send(
            "Mullvad VPN", "The VPN is connected now", "mullvad-vpn"
        )

    async def disconnect_vpn(self):
        """Disconnect from Mullvad VPN asynchronously."""
        self.logger.info("Disconnecting from Mullvad VPN...")
        await asyncio.create_subprocess_exec("mullvad", "disconnect")
        self.notifier.notify_send(
            "Mullvad VPN", "The VPN is disconnected now", "mullvad-vpn"
        )

    def check_status(self, action, parameter=None):
        """Check the status of the Mullvad VPN."""
        dialog = MullvadStatusDialog()
        dialog.present()

    async def get_current_relay_hostname(self) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "mullvad",
                "status",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if stdout:
                data = json.loads(stdout.decode())
                return data.get("relay", {}).get("hostname")
        except Exception as e:
            self.logger.error(f"Failed to get current relay: {e}")
        return ""

    async def set_mullvad_relay_by_city(self, *_):
        url = "https://api.mullvad.net/www/relays/wireguard/"
        try:
            self.logger.info(
                f"Mullvad is setting a random {self.city_code.capitalize()} relay..."
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    relays = await response.json()
            city_relays = [r for r in relays if r.get("city_code") == self.city_code]
            if not city_relays:
                raise RuntimeError(f"No relays found for city code '{self.city_code}'.")
            current = await self.get_current_relay_hostname()
            available = [r for r in city_relays if r["hostname"] != current]
            if not available:
                self.logger.error(
                    f"No new relays available in '{self.city_code}' different from current: {current}"
                )
                return
            relay_choice = random.choice(available)["hostname"]
            msg = f"Changing Mullvad relay to {relay_choice}"
            self.notifier.notify_send("Mullvad VPN", msg, "mullvad-vpn")
            await asyncio.create_subprocess_exec(
                "mullvad", "relay", "set", "location", relay_choice
            )
        except Exception as e:
            self.logger.error(f"Error: {e}")

    async def set_mullvad_relay_random_global(self, *_):
        """
        Set a random Mullvad relay from any city and country.
        """
        url = "https://api.mullvad.net/www/relays/wireguard/"
        try:
            self.logger.info("Mullvad is setting a random global relay...")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    relays = await response.json()
            if not relays:
                raise RuntimeError("No relays found in the relay list.")
            current = await self.get_current_relay_hostname()
            available = [r for r in relays if r["hostname"] != current]
            if not available:
                self.logger.error("No new relays available different from current.")
                return
            relay_choice = random.choice(available)["hostname"]
            msg = f"Changing Mullvad relay to {relay_choice}"
            self.notifier.notify_send("Mullvad VPN", msg, "mullvad-vpn")
            await asyncio.create_subprocess_exec(
                "mullvad", "relay", "set", "location", relay_choice
            )
        except Exception as e:
            self.logger.error(f"Error setting random global relay: {e}")

    async def update_vpn_status(self):
        """Check the status of the Mullvad VPN and update the UI."""
        try:
            net_files = await asyncio.to_thread(os.listdir, "/sys/class/net")
            is_mullvad_active = any(
                (file.startswith("wg") or file.startswith("tun")) for file in net_files
            )
            if not is_mullvad_active:
                is_mullvad_active = any(
                    file.startswith("tun") and "-mullvad" in file for file in net_files
                )
            status = await self.get_mullvad_status_string()

            def _update_ui():
                if is_mullvad_active:
                    self.menubutton_mullvad.set_icon_name(self.icon_name)
                else:
                    self.menubutton_mullvad.set_icon_name("stock_disconnect")
                if self.status_label:
                    self.status_label.set_text(status)

            self.schedule_in_gtk_thread(_update_ui)
        except Exception as e:
            self.logger.error(f"Error updating VPN status: {e}")

    async def get_mullvad_status_string(self):
        """Get the full status string from the mullvad command."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "mullvad",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip()
        except FileNotFoundError:
            return "Mullvad not installed"
        except Exception as e:
            return f"Error: {e}"

    def about(self):
        """
        This plugin provides a graphical user interface for managing the
        Mullvad VPN client directly from the Wayfire panel. It leverages
        asynchronous programming to interact with both the `mullvad`
        command-line tool and the Mullvad public API, allowing users to
        connect, disconnect, check status, and change relays without
        leaving their desktop environment.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The MullvadPlugin is an asynchronous, event-driven background service
        that integrates with the Wayfire compositor. It uses a GTK widget on
        the top panel to display the VPN's status and provides a popover
        menu for user interactions.
        The core logic is implemented through a series of asynchronous methods:
        1. **Concurrency Integration**: The plugin now utilizes the centralized
           BasePlugin methods: `on_start()` initiates the asynchronous setup,
           and `self.run_in_async_task()` replaces all direct `create_task`
           calls for better error handling and resource management.
        2. **GTK Safety**: The `update_vpn_status` coroutine uses
           `self.schedule_in_gtk_thread()` to ensure all UI updates (icon and label)
           are executed safely on the main GTK thread, preventing crashes
           from concurrent access.
        3. **Asynchronous Command Execution**: The plugin uses
           `asyncio.create_subprocess_exec` to run `mullvad` commands (connect,
           disconnect, relay set) and `asyncio.to_thread(os.listdir, ...)` to
           run blocking file system checks in a thread pool. This is crucial for
           non-blocking UI operation.
        4. **UI and State Management**:
           - **`on_start`**: This method is the primary setup function. It
             asynchronously retrieves the Mullvad version, sets up the main GTK widget,
             and starts a recurring `GLib.timeout_add` to update the VPN status.
           - **`update_vpn_status`**: This method is called periodically to
             check the VPN's connection state, inspecting network interfaces and
             updating the panel icon and status label accordingly.
        """
        return self.code_explanation.__doc__
