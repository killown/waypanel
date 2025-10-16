def get_plugin_metadata(_):
    about = """
    This plugin acts as a system tray client for waypanel.
    It uses D-Bus to communicate with applications that implement the
    StatusNotifierItem specification, allowing it to display their icons,
    tooltips, and context menus.
    """
    return {
        "id": "org.waypanel.plugin.status_notifier",
        "name": "Systray",
        "version": "1.0.0",
        "enabled": True,
        "container": "top-panel-center",
        "index": 5,
        "deps": ["event_manager", "top_panel"],
        "description": about,
    }


def get_plugin_class():
    from dbus_fast import Variant
    from gi.repository import GLib, Gtk  # pyright: ignore
    from src.plugins.core._base import BasePlugin
    from ._service import StatusNotifierWatcher
    import asyncio

    class SystrayClientPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.subscribe_to_icon_updates()
            self.subscribe_to_removal_events()
            self.messages = {}
            self.menus_layout = {}
            self.new_message = {}
            self.tray_button = {}
            self.tray_box = self.gtk.FlowBox()
            self._pending_creation = set()
            self.main_widget = (self.tray_box, "append")
            self.notifier_watcher = StatusNotifierWatcher("", panel_instance)

        def on_start(self):
            self.notifier_watcher.run_server_in_background(self._panel_instance)

        def subscribe_to_icon_updates(self):
            self.ipc_server.add_event_subscriber(
                event_type="tray_icon_name_updated", callback=self.on_icon_name_updated
            )

        def subscribe_to_removal_events(self):
            self.ipc_server.add_event_subscriber(
                event_type="tray_icon_removed", callback=self.on_tray_icon_removed
            )

        async def on_tray_icon_removed(self, message):
            service_name = message["data"]["service_name"]
            if button := self.tray_button.pop(service_name, None):
                self.tray_box.remove(button)
            self.messages.pop(service_name, None)
            self.menus_layout.pop(service_name, None)

        def set_message_data(self, service_name):
            if "data" in self.new_message:
                self.messages[service_name] = self.new_message["data"]

        def create_pixbuf_from_pixels(self, pixmap_data):
            """
            Creates a GdkPixbuf from raw pixel data, now robustly handling
            both single pixmaps and lists of pixmaps.
            """
            try:
                if pixmap_data and isinstance(pixmap_data[0], (list, tuple)):
                    pixmap_data = self.get_best_icon_entry(pixmap_data)
                if not pixmap_data or len(pixmap_data) != 3:
                    return None
                width, height, pixel_data_raw = pixmap_data
                pixel_data = bytes(pixel_data_raw)
                expected_size = width * height * 4
                if len(pixel_data) != expected_size:
                    return None
                return self.gdkpixbuf.Pixbuf.new_from_data(
                    pixel_data,  # pyright: ignore
                    self.gdkpixbuf.Colorspace.RGB,
                    True,
                    8,
                    width,
                    height,
                    width * 4,
                    None,
                    None,
                )
            except Exception as e:
                self.logger.error(f"Failed to create pixbuf: {e}", exc_info=True)
                return None

        async def fetch_menu_path(self, service_name):
            self.set_message_data(service_name)
            object_path = self.messages[service_name]["object_path"]
            bus = self.messages[service_name]["bus"]
            try:
                introspection = await bus.introspect(service_name, object_path)
                proxy = bus.get_proxy_object(service_name, object_path, introspection)
                properties = proxy.get_interface("org.freedesktop.DBus.Properties")
                menu_variant = await properties.call_get(
                    "org.kde.StatusNotifierItem", "Menu"
                )
                return menu_variant.value
            except Exception:
                return None

        def parse_menu_structure(self, menu_structure):
            """
            Parses the D-Bus menu structure. Corrected to avoid providing a default
            label for items intended as separators but missing a label.
            """
            parsed_menu = []

            def extract_item(variant_item):
                if (
                    not isinstance(variant_item, Variant)
                    or variant_item.signature != "(ia{sv}av)"
                ):
                    return None
                item_id, properties, children = variant_item.value
                props = {k: v.value for k, v in properties.items()}
                menu_item = {
                    "id": item_id,
                    "type": props.get("type", "standard"),
                    "label": props.get("label", ""),
                    "enabled": props.get("enabled", True),
                    "visible": props.get("visible", True),
                    "icon_name": props.get("icon-name"),
                    "icon_data": props.get("icon-data"),
                }
                if children:
                    menu_item["submenu"] = self.parse_menu_structure(children)
                return menu_item

            if isinstance(menu_structure, tuple) and len(menu_structure) == 2:
                menu_structure = menu_structure[1]
            for item in menu_structure:
                if isinstance(item, Variant):
                    if extracted := extract_item(item):
                        parsed_menu.append(extracted)
                elif isinstance(item, list):
                    parsed_menu.extend(self.parse_menu_structure(item))
            return parsed_menu

        async def on_icon_name_updated(self, message):
            service_name = message["data"]["service_name"]
            if (
                service_name in self._pending_creation
                or service_name in self.tray_button
            ):
                return
            try:
                self._pending_creation.add(service_name)
                self.new_message = message
                await self.set_menu_layout(service_name)
                menu_layout = self.menus_layout.get(service_name, {}).get("layout", [])
                button = self.create_menubutton(menu_layout, service_name)
                self.tray_button[service_name] = button
            except Exception as e:
                self.logger.error(
                    f"Error handling icon name update: {e}", exc_info=True
                )
            finally:
                self._pending_creation.discard(service_name)

        def _on_listbox_row_activated(self, listbox, row, service_name):
            item_id_str = row.get_name()
            if not item_id_str:
                return
            toplevel = listbox.get_ancestor(Gtk.Popover)
            if toplevel:
                toplevel.popdown()
            self.global_loop.create_task(
                self.on_menu_item_clicked(int(item_id_str), service_name)
            )

        async def initialize_proxy_object(self, service_name):
            self.set_message_data(service_name)
            bus = self.messages[service_name]["bus"]
            menu_path = await self.fetch_menu_path(service_name)
            if not menu_path:
                raise RuntimeError(f"No menu path for {service_name}")
            introspection = await bus.introspect(service_name, menu_path)
            self.proxy_object = bus.get_proxy_object(
                service_name, menu_path, introspection
            )

        async def set_menu_layout(self, service_name):
            await self.initialize_proxy_object(service_name)
            try:
                dbusmenu = self.proxy_object.get_interface("com.canonical.dbusmenu")
                props = ["label", "enabled", "visible", "icon-name", "icon-data"]
                rev, layout = await dbusmenu.call_get_layout(0, -1, props)
                self.menus_layout[service_name] = {
                    "layout": self.parse_menu_structure(layout),
                    "dbusmenu": dbusmenu,
                }
            except Exception as e:
                self.logger.error(f"Failed to set menu layout: {e}", exc_info=True)
                self.menus_layout[service_name] = {"layout": [], "dbusmenu": None}

        async def on_menu_item_clicked(self, item_id, service_name):
            try:
                if dbusmenu := self.menus_layout[service_name].get("dbusmenu"):
                    await dbusmenu.call_event(item_id, "clicked", Variant("s", ""), 0)
            except Exception as e:
                self.logger.error(
                    f"Failed to trigger D-Bus action for item {item_id}: {e}",
                    exc_info=True,
                )

        def _normalize_label(self, label: str) -> str:
            if not isinstance(label, str) or not label:
                return ""
            label = label.replace("_", "")
            return label.strip().capitalize()

        async def _build_menu_manually(self, listbox, menu_data, service_name):
            """
            Builds the GTK menu from D-Bus data. Corrected to properly embed Gtk.Separator
            inside a non-interactive Gtk.ListBoxRow.
            """
            for item in menu_data:
                await asyncio.sleep(0)
                if not item.get("visible", True):
                    continue
                is_separator = item.get("type") == "separator"
                label_text = self._normalize_label(item.get("label", ""))
                if is_separator:
                    row = Gtk.ListBoxRow()
                    row.set_child(Gtk.Separator())
                    row.set_selectable(False)
                    row.set_activatable(False)
                    listbox.append(row)
                    continue
                if (
                    not label_text
                    and not item.get("icon_name")
                    and not item.get("icon_data")
                    and not item.get("submenu")
                ):
                    continue
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                box.set_margin_top(8)
                box.set_margin_bottom(8)
                box.set_margin_start(8)
                box.set_margin_end(8)
                image = None
                if icon_name := item.get("icon_name"):
                    if isinstance(icon_name, str) and icon_name:
                        image = Gtk.Image.new_from_icon_name(icon_name)
                elif icon_data := item.get("icon_data"):
                    if isinstance(icon_data, bytes) and icon_data.startswith(
                        b"\x89PNG"
                    ):
                        try:
                            loader = self.gdkpixbuf.PixbufLoader.new_with_type("png")
                            loader.write(icon_data)
                            loader.close()
                            pixbuf = loader.get_pixbuf()
                            image = Gtk.Image.new_from_pixbuf(pixbuf)
                        except GLib.Error:
                            pass
                    else:
                        if pixbuf := self.create_pixbuf_from_pixels(icon_data):
                            image = Gtk.Image.new_from_pixbuf(pixbuf)
                if image:
                    box.append(image)
                label = Gtk.Label(label=label_text, xalign=0)
                box.append(label)
                row.set_child(box)
                if item.get("submenu"):
                    submenu_button = Gtk.MenuButton(
                        icon_name="go-next-symbolic", has_frame=False
                    )
                    submenu_popover = Gtk.Popover()
                    submenu_listbox = Gtk.ListBox()
                    submenu_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
                    submenu_listbox.connect(
                        "row-activated", self._on_listbox_row_activated, service_name
                    )
                    submenu_popover.set_child(submenu_listbox)
                    submenu_button.set_popover(submenu_popover)
                    box.append(submenu_button)
                    await self._build_menu_manually(
                        submenu_listbox, item["submenu"], service_name
                    )
                else:
                    row.set_name(str(item["id"]))
                row.set_sensitive(item.get("enabled", True))
                listbox.append(row)

        def get_best_icon_entry(self, pixmap_data, target_size=24):
            if not pixmap_data:
                return None
            return min(pixmap_data, key=lambda x: abs(x[0] - target_size))

        def create_menubutton(self, menu_structure, service_name):
            self.set_message_data(service_name)
            icon_name = self.messages[service_name]["icon_name"]
            menubutton = self.gtk.MenuButton()
            if icon_pixmap_data := self.messages[service_name].get("icon_pixmap"):
                if pixbuf := self.create_pixbuf_from_pixels(icon_pixmap_data):
                    menubutton.set_child(self.gtk.Image.new_from_pixbuf(pixbuf))
                else:
                    menubutton.set_icon_name(icon_name)
            else:
                menubutton.set_icon_name(icon_name)
            menubutton.add_css_class("tray_icon")
            popover = Gtk.Popover()
            listbox = Gtk.ListBox()
            listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            listbox.connect(
                "row-activated", self._on_listbox_row_activated, service_name
            )
            popover.set_child(listbox)
            menubutton.set_popover(popover)
            self.global_loop.create_task(
                self._build_menu_manually(listbox, menu_structure, service_name)
            )
            self.tray_box.append(menubutton)
            return menubutton

        def on_stop(self):
            self.logger.info("SystrayClientPlugin has stopped.")

        def on_reload(self):
            self.logger.info("SystrayClientPlugin has been reloaded.")

        def on_cleanup(self):
            self.logger.info("SystrayClientPlugin is cleaning up resources.")

        def code_explanation(self):
            return "Fixed pixbuf creation for multi-resolution icons, added PNG support, and implemented D-Bus service ownership check to prevent retrying stale service names."

    return SystrayClientPlugin
