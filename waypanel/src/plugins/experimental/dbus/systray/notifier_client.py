from gi.repository import Gtk, Gio, Gdk, GdkPixbuf, GLib
from src.plugins.core._event_loop import global_loop
from dbus_fast import Variant
import re
from unidecode import unidecode

# Local imports
from src.plugins.core._base import BasePlugin
from ._notifier_watcher import (
    StatusNotifierWatcher,
)
import psutil

# Enable or disable the plugin
ENABLE_PLUGIN = True

# Define plugin dependencies (if any)
DEPS = [
    "event_manager",
    "top_panel",
]


def get_plugin_placement(panel_instance):
    return "top-panel-right", 10, 10


def initialize_plugin(panel_instance):
    """
    Initialize the plugin and return its instance.
    Args:
        panel_instance: The main panel object from panel.py.
    """
    if not ENABLE_PLUGIN:
        panel_instance.logger.info("SystrayClientPlugin is disabled.")
        return None

    # Ensure EventManagerPlugin is loaded
    if "event_manager" not in panel_instance.plugins:
        panel_instance.logger.erro("EventManagerPlugin is not loaded. Cannot proceed.")
        return None

    # Create and return the plugin instance
    plugin = SystrayClientPlugin(panel_instance)
    return plugin


class SystrayClientPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.subscribe_to_icon_updates()
        self.subscribe_to_removal_events()
        self.messages = {}
        self.menus = {}
        self.menus_layout = {}
        self.new_message = {}
        self.tray_button = {}
        self.tray_box = Gtk.FlowBox()
        self.items = {}
        self.loop = global_loop
        self.main_widget = (self.tray_box, "append")
        self.notifier_watcher = StatusNotifierWatcher("", panel_instance)
        self.notifier_watcher.run_server_in_background(panel_instance)

    def subscribe_to_icon_updates(self):
        """
        Subscribe to 'icon_name_updated' events from the IPC server.
        """
        self.ipc_server.add_event_subscriber(
            event_type="tray_icon_name_updated", callback=self.on_icon_name_updated
        )

    def subscribe_to_removal_events(self):
        """
        Subscribe to tray icon removal events.
        """
        self.ipc_server.add_event_subscriber(
            event_type="tray_icon_removed", callback=self.on_tray_icon_removed
        )

    async def on_tray_icon_removed(self, message):
        service_name = message["data"]["service_name"]
        self.logger.info(f"Tray icon removed for service: {service_name}")

        if service_name in self.tray_button:
            button = self.tray_button[service_name]
            self.tray_box.remove(button)
            del self.tray_button[service_name]
            del self.messages[service_name]
            del self.menus_layout[service_name]
            del self.menus[service_name]

    def set_message_data(self, service_name):
        self.messages[service_name] = {
            "bus": self.new_message["data"]["bus"],
            "service_name": self.new_message["data"]["service_name"],
            "object_path": self.new_message["data"]["object_path"],
            "item": self.new_message["data"]["item"],
            "icon_name": self.new_message["data"]["icon_name"],
            "icon_pixmap": self.new_message["data"]["icon_pixmap"],
        }

    def create_pixbuf_from_pixels(self, pixmap_data):
        try:
            if (
                not pixmap_data
                or not isinstance(pixmap_data, (list, tuple))
                or len(pixmap_data) == 0
            ):
                raise ValueError("Invalid pixmap data")

            width = int(pixmap_data[0])
            height = int(pixmap_data[1])
            pixel_data = pixmap_data[2]

            # Ensure pixel_data is a bytes object
            if isinstance(pixel_data, list):
                pixel_data = bytes(pixel_data)
            elif isinstance(pixel_data, str):
                pixel_data = pixel_data.encode("latin1")
            elif not isinstance(pixel_data, bytes):
                raise ValueError(f"Unsupported pixel data type: {type(pixel_data)}")

            rowstride = width * 4  # Assuming RGBA format
            has_alpha = True

            return GdkPixbuf.Pixbuf.new_from_data(
                pixel_data,
                GdkPixbuf.Colorspace.RGB,
                has_alpha,
                8,
                width,
                height,
                rowstride,
                None,
                None,
            )
        except Exception as e:
            self.logger.error(f"Failed to create pixbuf: {e}")
            return None

    async def fetch_menu_path(self, service_name):
        """
        Fetch the menu object path dynamically using the Menu property.

        Args:
            bus: The D-Bus connection.
            service_name (str): The D-Bus service name.
            object_path (str): The object path for the StatusNotifierItem.

        Returns:
            str: The menu object path, or None if not available.
        """
        self.set_message_data(service_name)
        object_path = self.messages[service_name]["object_path"]
        bus = self.messages[service_name]["bus"]
        try:
            self.introspection = await bus.introspect(service_name, object_path)
            proxy_object = bus.get_proxy_object(
                service_name, object_path, introspection=self.introspection
            )

            # Get the org.freedesktop.DBus.Properties interface
            properties = proxy_object.get_interface("org.freedesktop.DBus.Properties")

            # Fetch the Menu property
            menu_variant = await properties.call_get(
                "org.kde.StatusNotifierItem", "Menu"
            )

            # Extract the actual path from the Variant object
            if isinstance(menu_variant, Variant):
                menu_path = menu_variant.value  # Unpack the Variant
            else:
                menu_path = menu_variant
            return menu_path

        except Exception as e:
            self.log_error(
                f"Failed to fetch Menu property for service: {service_name} and path {object_path}: {e}"
            )
            return None

    def parse_menu_structure(self, menu_structure):
        """Parse the raw D-Bus menu structure into a nested Python dictionary format."""
        self.logger.debug(f"Raw menu structure: {menu_structure}")
        parsed_menu = []

        def extract_item(variant_item):
            """Extract a single menu item from a Variant object."""
            # Validate the Variant object
            if (
                not isinstance(variant_item, Variant)
                or variant_item.signature != "(ia{sv}av)"
            ):
                self.logger.warning(f"Skipping invalid menu item: {variant_item}")
                return None

            # Unpack the Variant structure: (ia{sv}av)
            item_data = variant_item.value
            if not isinstance(item_data, list) or len(item_data) != 3:
                self.logger.warning(f"Invalid item data format: {item_data}")
                return None

            item_id, properties, children = item_data

            # Convert properties from {sv} dict to regular dict
            props = {}
            for key, variant_value in properties.items():
                if isinstance(variant_value, Variant):
                    props[key] = variant_value.value
                else:
                    props[key] = variant_value

            menu_item = {
                "id": item_id,
                "type": props.get("type", "item"),
                "label": props.get("label", f"Item {item_id}"),
                "enabled": props.get(
                    "enabled", True
                ),  # Default to True if not specified
            }

            # Recursively parse submenu
            if children:
                menu_item["submenu"] = self.parse_menu_structure(children)

            return menu_item

        # Process each item in the raw menu structure
        for item in menu_structure:
            if isinstance(item, Variant):
                extracted_item = extract_item(item)
                if extracted_item:
                    parsed_menu.append(extracted_item)
            elif isinstance(item, list):
                # Handle lists of Variants (nested menus)
                parsed_menu.extend(self.parse_menu_structure(item))
            else:
                self.logger.warning(f"Skipping invalid menu item: {item}")

        return parsed_menu

    async def on_icon_name_updated(self, message):
        """Handle updates to the icon name of a tray icon.

        Args:
            message (dict): The event message containing details about the updated icon.
        """
        self.new_message = message
        try:
            service_name = message["data"]["service_name"]
            await self.set_menu_layout(service_name)
            self.set_message_data(service_name)
            menu_layout = self.menus_layout[service_name]["layout"]
            if service_name not in self.tray_button:
                button = self.create_menubutton(menu_layout, service_name)

                self.tray_button[service_name] = button
                self.logger.info(f"Created button for {service_name}")
        except Exception as e:
            self.log_error(f"Error handling icon name update {e}")

    def _on_menu_item_clicked_wrapper(self, *args):
        """
        Wrapper function to schedule the async `on_menu_item_clicked` coroutine.
        """
        action, parameter, label_index, service_name = args
        # Use self.loop.create_task to schedule the coroutine
        self.loop.create_task(
            self.on_menu_item_clicked(action, parameter, label_index, service_name)
        )

    async def initialize_proxy_object(self, service_name):
        """
        Initialize the D-Bus proxy object for interacting with the menu.
        """
        self.set_message_data(service_name)
        bus = self.messages[service_name]["bus"]
        try:
            # Fetch the menu path dynamically
            self.menu_path = await self.fetch_menu_path(service_name)
            if not self.menu_path:
                raise RuntimeError(f"No menu path found for {service_name}")

            try:
                self.introspection = await bus.introspect(service_name, self.menu_path)
            except Exception as e:
                self.log_error(
                    f"Introspection failed for {service_name}{self.menu_path}: {e}"
                )
                return None

            # Create the proxy object with introspection data
            self.proxy_object = bus.get_proxy_object(
                service_name, self.menu_path, introspection=self.introspection
            )
            self.logger.info(
                f"Proxy object initialized for {service_name}{self.menu_path}"
            )
        except Exception as e:
            self.log_error(f"Failed to initialize proxy object: {e}")
            raise

    async def set_menu_layout(self, service_name):
        """Fetch and log the full menu structure from com.canonical.dbusmenu."""
        await self.initialize_proxy_object(service_name)
        self.set_message_data(service_name)
        bus = self.messages[service_name]["bus"]
        try:
            dbusmenu = self.proxy_object.get_interface("com.canonical.dbusmenu")

            # Fetch the menu layout
            start_id = 0  # Root of the menu
            recursion_depth = -1  # Full depth (-1 means no limit)
            property_names = [
                "label",
                "enabled",
                "children-display",
            ]  # Properties to fetch

            layout = None
            revision = None
            try:
                revision, layout = await dbusmenu.call_get_layout(
                    start_id, recursion_depth, property_names
                )
            except Exception as e:
                self.log_error(
                    f"Trying fallback for dbusmenu.call_get_layout: {layout} {e}"
                )
                revision, layout = await dbusmenu.call_get_layout(0, -1, [])

            if not layout:
                self.log_error(
                    f"no menu layout was created for the new tray icon {service_name}"
                )

            # Log the revision and layout
            self.logger.info(f"Menu Revision: {revision}")
            self.logger.debug("Raw Menu Layout:")
            self.logger.debug(layout)

            # Parse and display the menu structure in a readable format
            parsed_structure = self.parse_menu_structure(layout)
            self.logger.info("Parsed Menu Structure:")
            self.logger.info(parsed_structure)
            self.menus_layout[service_name] = {
                "layout": parsed_structure,
                "dbusmenu": dbusmenu,
            }

        except Exception as e:
            self.log_error(f"Failed to debug menu structure: {e}")

    async def on_menu_item_clicked(self, *args):
        """
        Handle menu item clicks by triggering the corresponding DBus action.
        Args:
            *args: Variable-length arguments passed by the signal handler.
        """
        # update menu structure and proxy object

        try:
            action, parameter, self.label_index, self.service_name = args
            object_path = self.messages[self.service_name]["object_path"]
            event_id = "clicked"
            timestamp = Gdk.CURRENT_TIME
            await self.set_menu_layout(self.service_name)
            dbusmenu = self.menus_layout[self.service_name]["dbusmenu"]
            layout = self.menus_layout[self.service_name]["layout"]
            self.item_id = layout[self.label_index]["id"]
            await dbusmenu.call_event(
                self.item_id, event_id, Variant("s", ""), timestamp
            )
            self.logger.info(f"Action triggered for menu item: {self.item_id}")

        except Exception as e:
            print(
                f"Failed to trigger action for menu item and service_name: {self.service_name} : {e}"
            )

    def sanitize_gio_action_name(self, name: str) -> str:
        """
        Sanitize a string to be a valid Gio.SimpleAction or GMenu detailed action name.
        - Removes all special characters except letters and numbers.
        - Ensures no invalid sequences like leading digits or repeated dots.
        """

        # Step 1: Normalize Unicode (optional but recommended)
        name = unidecode(name)

        # Step 2: Convert to lowercase
        name = name.lower()

        # Step 3: Remove all non-alphanumeric characters
        name = re.sub(r"[^a-z0-9]", "", name)

        # Step 4: Ensure starts with a letter
        if not name or not name[0].isalpha():
            name = "action" + name

        # Step 5: Prevent empty result
        if not name:
            return "empty"

        return name

    def create_menu_item(self, menu, name, label_index, service_name, panel_instance):
        """Create a menu item with the specified name and command."""
        name_for_action = self.sanitize_gio_action_name(name)
        action_name = f"app.run-command-{name_for_action}"
        action = Gio.SimpleAction.new(action_name, None)
        # quick reminder, the issue of not call_event working, is here
        action.connect(
            "activate", self._on_menu_item_clicked_wrapper, label_index, service_name
        )
        panel_instance.add_action(action)
        menu_item = Gio.MenuItem.new(name, f"app.{action_name}")
        menu.append_item(menu_item)

    def set_menu_items(self, menu_data, service_name):
        """
        Process the menu data and populate the internal menu structure.

        Args:
            menu_data (list): List of menu items as dictionaries.
            service_name (str): The name of the service associated with the menu.
        """
        # TODO: add support for submenus
        # Ensure the service_name exists in self.menus
        if service_name not in self.menus:
            self.menus[service_name] = []

        # Clear existing menu items for the service
        self.menus[service_name].clear()

        # Process each menu item
        index = 0
        for item in menu_data:
            try:
                # Extract properties from the item
                item_id = item.get("id")
                item_type = item.get(
                    "type", "item"
                )  # Default to "item" if type is missing
                label = item.get("label", f"Item {item_id}")
                enabled = item.get(
                    "enabled", True
                )  # Default to True if enabled is missing

                # Append the parsed menu item to the internal structure
                self.menus[service_name].append(
                    {
                        "id": item_id,
                        "type": item_type,
                        "label": label,
                        "label_id": index,
                        "enabled": enabled,
                    }
                )
                index += 1
            except Exception as e:
                self.log_error(f"Error processing menu item: {item}. Error: {e}")

    def get_best_icon_entry(self, pixmap_data, target_size=24):
        for entry in sorted(pixmap_data, key=lambda x: abs(x[0] - target_size)):
            return entry
        return pixmap_data[0]  # fallback

    def create_menubutton(self, menu_structure, service_name):
        """
        Create a MenuButton with the given menu structure.

        Args:
            menu_structure (list): The raw menu structure from D-Bus.

        Returns:
            Gtk.MenuButton: A MenuButton with the parsed menu structure.
        """
        icon_name = self.messages[service_name]["icon_name"]
        icon_pixmap = None
        menubutton = Gtk.MenuButton()
        if self.messages[service_name]["icon_pixmap"] is not None:
            icon_pixmap = self.messages[service_name]["icon_pixmap"]
            icon_pixmap = self.get_best_icon_entry(icon_pixmap, target_size=32)
            icon_pixmap = self.create_pixbuf_from_pixels(icon_pixmap)
            icon = Gtk.Image.new_from_pixbuf(icon_pixmap)

            # icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_halign(Gtk.Align.CENTER)
            icon.set_valign(Gtk.Align.CENTER)

            menubutton.set_child(icon)

        else:
            menubutton.set_icon_name(icon_name)

        menubutton.add_css_class("tray_icon")

        # Create a Gio.Menu
        menu = Gio.Menu()

        # Parse the menu structure recursively
        def parse_menu(menu_data, gio_menu):
            # Ensure the menu_data is iterable
            if not isinstance(menu_data, (list, tuple)):
                print("Invalid menu data format:", menu_data)
                return

            # The first two elements are metadata; skip them
            self.set_menu_items(menu_data, service_name)
            items = self.menus[service_name]
            last_item_was_separator = False
            for item in items:
                if item["type"] == "separator":
                    if last_item_was_separator:
                        last_item_was_separator = False
                        continue
                    menu_item = Gio.MenuItem.new("-" * 30, "app.separator")
                    menu.append_item(menu_item)
                    last_item_was_separator = True
                    continue
                # FIXME: identify why apps like steam create labels like: "Item 1", "Item 100"
                if (
                    len(item["label"].split()) == 2
                    and item["label"].split()[0].startswith("Item")
                    and item["label"].split()[-1].isalnum()
                ):
                    menu_item = Gio.MenuItem.new("-" * 30, "app.separator")
                    menu.append_item(menu_item)
                    continue

                self.create_menu_item(
                    gio_menu, item["label"], item["label_id"], service_name, self.obj
                )

        # Populate the menu based on the menu_structure
        parse_menu(menu_structure, menu)

        # Set the menu model and insert the action group into the MenuButton
        menubutton.set_menu_model(menu)
        menubutton.add_css_class("tray-menu-button")
        # Add the MenuButton to the tray box
        self.tray_box.append(menubutton)
        return menubutton

    def on_start(self):
        """
        Called when the plugin is started.
        """
        self.logger.info("SystrayClientPlugin has started.")

    def on_stop(self):
        """
        Called when the plugin is stopped or unloaded.
        """
        self.logger.info("SystrayClientPlugin has stopped.")

    def on_reload(self):
        """
        Called when the plugin is reloaded dynamically.
        """
        self.logger.info("SystrayClientPlugin has been reloaded.")

    def on_cleanup(self):
        """
        Called before the plugin is completely removed.
        """
        self.logger.info("SystrayClientPlugin is cleaning up resources.")
