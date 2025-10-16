import typing
from dbus_fast.aio import MessageBus
from dbus_fast import Variant
from gi.repository import Gio  # pyright: ignore


class DBusMenuProxy:
    """
    Client for the com.canonical.dbusmenu interface using dbus-fast.
    This class handles the asynchronous call to GetLayout to retrieve the
    entire proprietary menu structure from a remote service.
    """

    INTERFACE: typing.Final[str] = "com.canonical.dbusmenu"
    """The D-Bus interface name for the menu protocol."""
    RECURSION_DEPTH_MAX: typing.Final[int] = 2147483647
    """Represents GLib.MAXINT32 for maximum recursion depth."""

    def __init__(
        self, bus: MessageBus, service_name: str, object_path: str, logger: typing.Any
    ):
        """
        Initializes the DBusMenuProxy client.
        Args:
            bus: The active dbus_fast.aio.MessageBus instance.
            service_name: The D-Bus service name (e.g., ':1.100').
            object_path: The D-Bus object path of the menu (from SNI.Menu property).
            logger: The logging object from the parent component.
        """
        self.bus: MessageBus = bus
        self.service_name: str = service_name
        self.object_path: str = object_path
        self.logger = logger
        self._proxy: typing.Any = None

    async def initialize(self) -> bool:
        """
        Asynchronously sets up the proxy object for the menu interface.
        Returns:
            True if initialization was successful, False otherwise.
        """
        try:
            introspection = await self.bus.introspect(
                self.service_name, self.object_path
            )
            proxy_object = self.bus.get_proxy_object(
                self.service_name, self.object_path, introspection=introspection
            )
            self._proxy = proxy_object.get_interface(self.INTERFACE)
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to initialize DBusMenuProxy for {self.object_path}: {e}"
            )
            return False

    async def fetch_menu_layout(self) -> typing.Optional[typing.List[typing.Tuple]]:
        """
        Calls the 'GetLayout' method to retrieve the entire menu tree recursively.
        Returns:
            A list of raw DBus menu item structures (list of tuples), or None on error.
        Complexity:
            Time: O(T_DBus) - dominated by the single asynchronous network I/O call.
            Space: O(N) - where N is the total number of menu items.
        """
        if not self._proxy:
            self.logger.error(
                "DBusMenuProxy not initialized before calling fetch_menu_layout."
            )
            return None
        try:
            menu_tuple: typing.Tuple[
                int, int, typing.Any
            ] = await self._proxy.call_get_layout(
                0,
                self.RECURSION_DEPTH_MAX,
                [],
            )
            root_structure = menu_tuple[2]
            dbus_menu_items: typing.List[typing.Tuple] = root_structure[4]
            return dbus_menu_items
        except Exception as e:
            self.logger.error(
                f"Failed to fetch menu layout from {self.object_path}: {e}"
            )
            return None


def dbus_menu_to_gio_model(dbus_menu_items: typing.List[typing.Tuple]) -> "typing.Any":
    """
    Recursively converts the raw dbus-fast native menu structure into a Gio.MenuModel.
    Args:
        dbus_menu_items: The list of menu item structures (tuples) from DBusMenuProxy.
    Returns:
        A Gio.MenuModel instance (typed as Any to defer gi.repository import).
    """
    root_menu_model = Gio.Menu.new()

    def _recursively_build(menu_model: Gio.Menu, items: typing.List[typing.Tuple]):
        for item_struct in items:
            item_id, item_type, label, properties_variant, children_array = item_struct
            properties: typing.Dict[str, Variant] = properties_variant
            if item_type & 0x02:
                menu_model.append_item(Gio.MenuItem.new(None, None))
                continue
            final_label: typing.Optional[str] = None
            if label:
                final_label = label
            if "label" in properties and properties["label"].value:
                final_label = str(properties["label"].value)
            menu_item = Gio.MenuItem.new(final_label, None)
            if item_type & 0x01:
                action_id_variant = properties.get("action-id")
                if action_id_variant and action_id_variant.value:
                    action_id: str = str(action_id_variant.value)
                    menu_item.set_attribute("action", action_id)  # pyright: ignore
            enabled_variant = properties.get("enabled", Variant("b", True))
            if enabled_variant.value is False:
                menu_item.set_attribute("enabled", "false")  # pyright: ignore
            if children_array and len(children_array) > 0:
                submenu = Gio.Menu.new()
                menu_item.set_submenu(submenu)
                _recursively_build(submenu, children_array)
            menu_model.append_item(menu_item)

    _recursively_build(root_menu_model, dbus_menu_items)
    return root_menu_model
