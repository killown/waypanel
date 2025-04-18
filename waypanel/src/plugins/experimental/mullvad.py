import os
import random
from gi.repository import Gtk, Gio, GLib
from subprocess import Popen, check_output

# Set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    """Define the plugin's position and order."""
    position = "systray"
    order = 5
    return position, order


def initialize_plugin(panel_instance):
    """Initialize the Mullvad plugin."""
    if ENABLE_PLUGIN:
        mullvad_plugin = MullvadPlugin(panel_instance)
        mullvad_plugin.create_menu_popover_mullvad()
        return mullvad_plugin


class MullvadPlugin:
    def __init__(self, panel_instance):
        self.obj = panel_instance
        self.logger = self.obj.logger
        self._setup_config_paths()
        self.mullvad_version = self.get_mullvad_version()

    def append_widget(self):
        return self.menubutton_mullvad

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.waypanel_cfg = os.path.join(self.config_path, "waypanel.toml")

    def get_mullvad_version(self):
        """Retrieve the Mullvad version using the `mullvad --version` command."""
        try:
            version = check_output(["mullvad", "--version"]).decode().strip()
            return version
        except Exception as e:
            self.logger.info(f"Error retrieving Mullvad version: {e}")
            return "Mullvad Version Unavailable"

    def create_menu_popover_mullvad(self):
        """Create a menu button and attach it to the panel."""
        # Create the MenuButton
        self.menubutton_mullvad = Gtk.MenuButton()
        self.menubutton_mullvad.set_icon_name("mullvad-vpn")
        self.menubutton_mullvad.add_css_class("top_right_widgets")

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
        random_br_action.connect("activate", self.random_br_relay)

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
        random_br_button.connect("clicked", self.random_br_relay)
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
        self.logger.info("Checking Mullvad VPN status...")
        try:
            status = check_output(["mullvad", "status"]).decode().strip()
            self.status_label.set_text(status)
            Popen(["notify-send", status])
        except Exception as e:
            self.logger.info(f"Error checking Mullvad status: {e}")

    def random_br_relay(self, action, parameter=None):
        """Set a random Brazilian relay for Mullvad."""
        self.logger.info("Setting random Brazilian relay...")
        try:
            # Fetch the list of relays
            mullvad_list = check_output(["mullvad", "relay", "list"]).decode()
            mullvad_list = (
                mullvad_list.split("Brazil (br)")[-1].split("Bulgaria")[0].strip()
            )
            mullvad_list = mullvad_list.split("\n")
            mullvad_list = [i.split(" ")[0].strip() for i in mullvad_list[1:]]

            # Get the current status
            status = check_output(["mullvad", "status"]).decode().strip()
            try:
                current_relay = status.split(" ")[2].strip()
            except IndexError:
                current_relay = None

            # Choose a random relay that is not the current one
            relay_choice = random.choice(
                [i for i in mullvad_list if i != current_relay]
            )
            Popen(["mullvad", "relay", "set", "location", relay_choice])
            Popen(["mullvad", "disconnect"])
            Popen(["mullvad", "connect"])
            msg = f"Mudando para {relay_choice}"
            Popen(["notify-send", msg])
        except Exception as e:
            self.logger.error(f"Error setting random Brazilian relay: {e}")

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
