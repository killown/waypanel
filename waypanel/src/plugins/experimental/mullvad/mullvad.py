import os
import random
import asyncio
import aiohttp
import json
from gi.repository import Gtk, Gio, GLib
from subprocess import Popen, check_output
from src.plugins.core._base import BasePlugin
from .mullvad_info import MullvadStatusDialog
from src.plugins.core._event_loop import global_loop

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
# load the plugin only after essential plugins is loaded
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "top-panel-systray"
    order = 5
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the Mullvad plugin."""
    if ENABLE_PLUGIN:
        mullvad_plugin = MullvadPlugin(panel_instance)
        mullvad_plugin.create_menu_popover_mullvad()
        return mullvad_plugin


class MullvadPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.mullvad_version = self.get_mullvad_version()
        self.loop = global_loop
        self.city_code = self.get_city_code()

    def get_mullvad_version(self):
        """Retrieve the Mullvad version using the `mullvad --version` command."""
        try:
            version = check_output(["mullvad", "--version"]).decode().strip()
            return version
        except Exception as e:
            self.logger.info(f"Error retrieving Mullvad version: {e}")
            return "Mullvad Version Unavailable"

    def get_city_code(self):
        """Get the city code from the plugin's config section in waypanel.toml."""
        plugin_config = self.config.get("plugins", {}).get("mullvad", {})
        # more infor: https://api.mullvad.net/www/relays/wireguard/
        # waypanel.toml config example:
        # [plugins.mullvad]
        # city_code = "sao"
        return plugin_config.get("city_code", "sao")

    def create_menu_popover_mullvad(self):
        """Create a menu button and attach it to the panel."""
        # Create the MenuButton
        self.menubutton_mullvad = Gtk.MenuButton()
        self.menubutton_mullvad.set_icon_name("mullvad-vpn")
        self.menubutton_mullvad.add_css_class("top_right_widgets")
        self.main_widget = (self.menubutton_mullvad, "append")

        # Add the MenuButton to the systray

        # Create and set the menu model
        self.create_menu_model()

        # Start periodic status updates
        if os.path.exists("/usr/bin/mullvad"):
            GLib.timeout_add(10000, self.update_vpn_status)

    def create_menu_model(self):
        """Create a Gio.Menu and populate it with options for Mullvad."""
        menu = Gio.Menu()

        # Add menu items
        connect_item = Gio.MenuItem.new("Connect", "app.connect")
        disconnect_item = Gio.MenuItem.new("Disconnect", "app.disconnect")
        status_item = Gio.MenuItem.new("Check Status", "app.status")
        random_br_item = Gio.MenuItem.new("Random BR Relay", "app.random_br")

        menu.append_item(connect_item)
        menu.append_item(disconnect_item)
        menu.append_item(status_item)
        menu.append_item(random_br_item)

        # Set the menu model to the MenuButton
        self.menubutton_mullvad.set_menu_model(menu)

        # Create and connect actions
        action_group = Gio.SimpleActionGroup()
        connect_action = Gio.SimpleAction.new("connect", None)
        disconnect_action = Gio.SimpleAction.new("disconnect", None)
        status_action = Gio.SimpleAction.new("status", None)
        random_br_action = Gio.SimpleAction.new("random_br", None)

        connect_action.connect("activate", self.connect_vpn)
        disconnect_action.connect("activate", self.disconnect_vpn)
        status_action.connect("activate", self.check_status)
        random_br_action.connect(
            "activate",
            lambda *args: self.loop.create_task(self.set_mullvad_relay_by_city()),
        )
        action_group.add_action(connect_action)
        action_group.add_action(disconnect_action)
        action_group.add_action(status_action)
        action_group.add_action(random_br_action)

        self.menubutton_mullvad.insert_action_group("app", action_group)

        # Create and attach the popover
        self.popover_mullvad = Gtk.Popover()
        self.popover_mullvad.set_parent(self.menubutton_mullvad)
        self.popover_mullvad.set_has_arrow(False)

        # Populate the popover with widgets
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Add the version header
        version_label = Gtk.Label(label=self.mullvad_version)
        version_label.add_css_class("mullvad-header-label")
        vbox.append(version_label)

        # Add status label
        self.status_label = Gtk.Label(label="Checking status...")
        vbox.append(self.status_label)

        # Add separator
        vbox.append(Gtk.Separator())

        # Add buttons for actions
        connect_button = Gtk.Button(label="Connect")
        connect_button.connect("clicked", self.connect_vpn)
        vbox.append(connect_button)

        disconnect_button = Gtk.Button(label="Disconnect")
        disconnect_button.connect("clicked", self.disconnect_vpn)
        vbox.append(disconnect_button)

        status_button = Gtk.Button(label="Check Status")
        status_button.connect("clicked", self.check_status)
        vbox.append(status_button)

        random_br_button = Gtk.Button(label="Random BR Relay")
        random_br_button.connect(
            "clicked",
            lambda *args: self.loop.create_task(self.set_mullvad_relay_by_city()),
        )
        vbox.append(random_br_button)

        self.popover_mullvad.set_child(vbox)

    def connect_vpn(self, action, parameter=None):
        """Connect to Mullvad VPN."""
        self.logger.info("Connecting to Mullvad VPN...")
        Popen(["mullvad", "connect"])
        Popen(["notify-send", "The VPN is connected now"])

    def disconnect_vpn(self, action, parameter=None):
        """Disconnect from Mullvad VPN."""
        self.logger.info("Disconnecting from Mullvad VPN...")
        Popen(["mullvad", "disconnect"])
        Popen(["notify-send", "The VPN is disconnected now"])

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
            print(f"Failed to get current relay: {e}")
        return ""

    async def set_mullvad_relay_by_city(self, *_):
        url = "https://api.mullvad.net/www/relays/wireguard/"
        try:
            self.logger.info(f"Mullvad is setting a random {self.city_code} relay...")
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
                print(
                    f"No new relays available in '{self.city_code}' different from current: {current}"
                )
                return

            relay_choice = random.choice(available)["hostname"]
            msg = f"Changing Mullvad relay to {relay_choice}"
            Popen(["notify-send", msg])
            await asyncio.create_subprocess_exec(
                "mullvad", "relay", "set", "location", relay_choice
            )
        except Exception as e:
            print(f"Error: {e}")

    def update_vpn_status(self):
        """Check the status of the Mullvad VPN and update the UI."""
        net_files = os.listdir("/sys/class/net")
        is_mullvad_active = any(
            (file.startswith("wg") or file.startswith("tun")) for file in net_files
        )
        if not is_mullvad_active:
            is_mullvad_active = any(
                file.startswith("tun") and "-mullvad" in file for file in net_files
            )

        if is_mullvad_active:
            self.menubutton_mullvad.set_icon_name("mullvad-vpn")
        else:
            self.menubutton_mullvad.set_icon_name("stock_disconnect")

        return True  # Keep the timeout active
