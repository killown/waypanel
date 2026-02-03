def get_plugin_metadata(panel_instance):
    container = panel_instance.config_handler.get_root_setting(
        ["org.waypanel.plugin.status_notifier", "panel"], None
    )

    if container is None:
        container = "top-panel-center"
        plugin_id = ["org.waypanel.plugin.status_notifier"]
        panel_instance.config_handler.set_root_setting(plugin_id, container)

    about = (
        "This plugin acts as a system tray client for waypanel.",
        "It uses D-Bus to communicate with applications that implement the",
        "StatusNotifierItem specification, allowing it to display their icons,",
        "tooltips, and context menus.",
    )

    return {
        "id": "org.waypanel.plugin.status_notifier",
        "name": "Systray",
        "version": "1.0.0",
        "enabled": True,
        "container": container,
        "index": 5,
        "deps": ["event_manager", "css_generator"],
        "description": about,
    }


def get_plugin_class():
    import asyncio
    from dbus_fast import Variant
    from gi.repository import GLib, Gtk  # pyright: ignore
    from src.plugins.core._base import BasePlugin
    from ._service import StatusNotifierWatcher

    class SystrayClientPlugin(BasePlugin):
        """
        Implements a D-Bus StatusNotifierItem client (system tray).
        This plugin discovers services on D-Bus, creates corresponding
        Gtk.MenuButton widgets, and builds their context menus dynamically
        by introspecting the service's D-Bus interface.
        It is designed to be robust against D-Bus service churn, where
        services may appear and disappear rapidly.
        """

        DEBOUNCE_DELAY = 0.25

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.subscribe_to_icon_updates()
            self.subscribe_to_removal_events()
            self.messages = {}
            self.menus_layout = {}
            self.tray_button = {}

            container_id = "org.waypanel.plugin.status_notifier"
            default_container_name = "top_panel_box_center"

            target_container_name, _ = (
                panel_instance.config_handler.get_plugin_container(
                    default_container_name, container_id
                )
            )

            attr_name = target_container_name.replace("-", "_")
            target_container = getattr(self._panel_instance, attr_name, None)

            self.tray_box = self.gtk.Box(
                orientation=self.gtk.Orientation.HORIZONTAL, spacing=0
            )
            self.tray_box.add_css_class("tray-box")
            self.tray_box.set_valign(self.gtk.Align.CENTER)
            self.tray_box.set_vexpand(False)

            if target_container and hasattr(target_container, "append"):
                target_container.append(self.tray_box)
            else:
                self._panel_instance.top_panel_box_center.append(self.tray_box)

            self.main_widget = (self.tray_box, "append")

            self._pending_creation = set()
            self._rebuild_pending = set()
            self.notifier_watcher = StatusNotifierWatcher("", panel_instance)

        def on_start(self):
            """
            Starts the background D-Bus watcher service.
            """
            self.notifier_watcher.run_server_in_background(self._panel_instance)
            self.plugins["css_generator"].install_css("status-notifier.css")

        def subscribe_to_icon_updates(self):
            """
            Subscribes to the event for new tray icons.
            """
            self.ipc_server.add_event_subscriber(
                event_type="tray_icon_name_updated", callback=self.on_icon_name_updated
            )

        def subscribe_to_removal_events(self):
            """
            Subscribes to the event for removed tray icons.
            """
            self.ipc_server.add_event_subscriber(
                event_type="tray_icon_removed", callback=self.on_tray_icon_removed
            )

        async def on_tray_icon_removed(self, message: dict):
            """
            Handles the removal of a tray icon widget and its state.
            """
            service_name = message["data"]["service_name"]
            if button := self.tray_button.pop(service_name, None):
                self.tray_box.remove(button)
            self.messages.pop(service_name, None)
            self.menus_layout.pop(service_name, None)
            self._rebuild_pending.discard(service_name)

        def create_pixbuf_from_pixels(self, pixmap_data):
            """
            Creates a GdkPixbuf from raw ARGB pixel data.
            Handles both single pixmaps and lists of pixmaps (choosing the best fit).
            """
            try:
                if not pixmap_data:
                    return None
                if isinstance(pixmap_data[0], (list, tuple)):
                    pixmap_data = self.get_best_icon_entry(pixmap_data)
                if len(pixmap_data) != 3:  # pyright: ignore
                    self.logger.warning(
                        f"Invalid pixmap data structure: length is {len(pixmap_data)}"  # pyright: ignore
                    )
                    return None
                width, height, pixel_data_raw = pixmap_data  # pyright: ignore
                if (
                    not isinstance(width, int)
                    or not isinstance(height, int)
                    or width <= 0
                    or height <= 0
                ):
                    self.logger.warning(f"Invalid pixmap dimensions: {width}x{height}")
                    return None
                pixel_data = bytes(pixel_data_raw)
                expected_size = width * height * 4
                if len(pixel_data) != expected_size:
                    self.logger.warning(
                        f"Pixel data size mismatch. "
                        f"Expected: {expected_size}, Got: {len(pixel_data)}"
                    )
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

        async def fetch_menu_path(self, service_name: str):
            """
            Fetches the D-Bus object path for the menu from the service properties.
            """
            if service_name not in self.messages:
                self.logger.warning(
                    f"No message data for {service_name} in fetch_menu_path"
                )
                raise RuntimeError(f"No message data for {service_name}")
            message_data = self.messages[service_name]
            object_path = message_data["object_path"]
            bus = message_data["bus"]
            try:
                introspection = await bus.introspect(service_name, object_path)
                proxy = bus.get_proxy_object(service_name, object_path, introspection)
                properties = proxy.get_interface("org.freedesktop.DBus.Properties")
                menu_variant = await properties.call_get(
                    "org.kde.StatusNotifierItem", "Menu"
                )
                return menu_variant.value
            except Exception as e:
                self.logger.error(f"Failed to fetch menu path for {service_name}: {e}")
                return None

        def parse_menu_structure(self, menu_structure: tuple | list):
            """
            Recursively parses the D-Bus menu structure into a Python list.
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

        async def on_icon_name_updated(self, message: dict):
            """
            Handles the creation of a new tray icon button and its menu.
            """
            service_name = message["data"]["service_name"]
            if (
                service_name in self._pending_creation
                or service_name in self.tray_button
            ):
                return
            try:
                self._pending_creation.add(service_name)
                self.messages[service_name] = message["data"]
                await self.set_menu_layout(service_name)
                menu_layout = self.menus_layout.get(service_name, {}).get("layout", [])
                button = self.create_menubutton(menu_layout, service_name)
                if button:
                    self.tray_button[service_name] = button
                else:
                    raise RuntimeError("MenuButton creation failed.")
            except Exception as e:
                self.logger.error(
                    f"Error handling icon name update for {service_name}: {e}",
                    exc_info=True,
                )
                self.messages.pop(service_name, None)
                self.menus_layout.pop(service_name, None)
                self.tray_button.pop(service_name, None)
            finally:
                self._pending_creation.discard(service_name)

        def _on_listbox_row_activated(self, listbox, row, service_name: str):
            """
            Handles row activation: opens a submenu or triggers a D-Bus click.
            """
            if hasattr(row, "_submenu_popover") and row._submenu_popover:
                row._submenu_popover.popup()
                return
            item_id_str = row.get_name()
            if not item_id_str:
                return
            if toplevel := listbox.get_ancestor(Gtk.Popover):
                toplevel.popdown()
            self.global_loop.create_task(
                self.on_menu_item_clicked(int(item_id_str), service_name)
            )

        async def initialize_proxy_object(self, service_name: str):
            """
            Fetches and initializes a fresh D-Bus proxy object for the menu service.
            """
            if service_name not in self.messages:
                self.logger.warning(
                    f"No message data found for service {service_name}. Action aborted."
                )
                raise RuntimeError(f"No message data for {service_name}")
            bus = self.messages[service_name]["bus"]
            menu_path = await self.fetch_menu_path(service_name)
            if not menu_path:
                raise RuntimeError(f"No menu path for {service_name}")
            introspection = await bus.introspect(service_name, menu_path)
            self.proxy_object = bus.get_proxy_object(
                service_name, menu_path, introspection
            )

        async def set_menu_layout(self, service_name: str):
            """
            Fetches the D-Bus menu layout and subscribes to layout updates.
            """
            try:
                await self.initialize_proxy_object(service_name)
                dbusmenu = self.proxy_object.get_interface("com.canonical.dbusmenu")
                if not dbusmenu:
                    self.logger.warning(
                        f"Service {service_name} has no com.canonical.dbusmenu interface."
                    )
                    self.menus_layout[service_name] = {"layout": [], "dbusmenu": None}
                    return

                def layout_updated_handler(revision: int, parent_id: int):
                    self.logger.info(
                        f"D-Bus signal LayoutUpdated received for {service_name}. Scheduling menu rebuild."
                    )
                    self.global_loop.create_task(
                        self.schedule_menu_rebuild(service_name)
                    )

                dbusmenu.on_layout_updated(layout_updated_handler)
                props = [
                    "label",
                    "enabled",
                    "visible",
                    "icon-name",
                    "icon-data",
                    "type",
                ]
                rev, layout = await dbusmenu.call_get_layout(0, -1, props)
                self.menus_layout[service_name] = {
                    "layout": self.parse_menu_structure(layout),
                    "dbusmenu": dbusmenu,
                }
            except Exception as e:
                self.logger.error(
                    f"Failed to set menu layout for {service_name}: {e}", exc_info=True
                )
                self.menus_layout[service_name] = {"layout": [], "dbusmenu": None}

        async def schedule_menu_rebuild(self, service_name: str) -> None:
            """
            Debounces menu rebuild requests to prevent event loops.
            """
            if service_name in self._rebuild_pending:
                self.logger.info(
                    f"Debouncing rebuild for {service_name}. Request ignored."
                )
                return
            if service_name not in self.tray_button:
                self.logger.warning(
                    f"Cannot schedule rebuild for {service_name}: No tray button."
                )
                return
            self._rebuild_pending.add(service_name)
            try:
                await asyncio.sleep(self.DEBOUNCE_DELAY)
                self.logger.info(
                    f"Debounce window over. Rebuilding menu for {service_name}."
                )
                await self.rebuild_menu_for_service(service_name)
            except Exception as e:
                self.logger.error(
                    f"Error during debounced rebuild for {service_name}: {e}",
                    exc_info=True,
                )
            finally:
                self._rebuild_pending.discard(service_name)

        async def rebuild_menu_for_service(self, service_name: str) -> None:
            """
            Forces a full D-Bus menu layout re-fetch and rebuilds the Gtk.ListBox.
            This function is now called by the debouncer.
            """
            menubutton = self.tray_button[service_name]
            popover = menubutton.get_popover()
            if not popover:
                return
            listbox = popover.get_child()
            if not isinstance(listbox, Gtk.ListBox):
                self.logger.warning(
                    f"Child of popover for {service_name} is not a Gtk.ListBox."
                )
                return
            while child := listbox.get_first_child():
                listbox.remove(child)
            try:
                await self.set_menu_layout(service_name)
                menu_layout = self.menus_layout.get(service_name, {}).get("layout", [])
                await self._build_menu_manually(listbox, menu_layout, service_name)
                self.logger.info(f"Menu rebuilt for service: {service_name}")
            except Exception as e:
                self.logger.error(
                    f"Failed to rebuild menu for {service_name}: {e}", exc_info=True
                )

        async def on_menu_item_clicked(self, item_id: int, service_name: str):
            """
            Triggers a D-Bus 'clicked' event for a specific menu item.
            """
            try:
                await self.initialize_proxy_object(service_name)
                dbusmenu = self.proxy_object.get_interface("com.canonical.dbusmenu")
                if not dbusmenu:
                    self.logger.error(
                        f"D-Bus menu interface unavailable for {service_name}"
                    )
                    return
                await dbusmenu.call_event(item_id, "clicked", Variant("s", ""), 0)
                self.global_loop.create_task(self.schedule_menu_rebuild(service_name))
            except RuntimeError as e:
                self.logger.warning(
                    f"D-Bus menu action aborted. Service proxy failed for {service_name}: {e}"
                )
            except Exception as e:
                error_msg = str(e)
                if "does not refer to a menu item" in error_msg:
                    self.logger.warning(
                        f"Stale menu ID {item_id} in {service_name}. Forcing rebuild."
                    )
                    self.global_loop.create_task(
                        self.schedule_menu_rebuild(service_name)
                    )
                    self.logger.info(
                        f"Menu rebuild scheduled for {service_name}. Please re-click."
                    )
                else:
                    self.logger.error(
                        f"Failed to trigger D-Bus action for item {item_id}: {e}",
                        exc_info=True,
                    )

        def _normalize_label(self, label: str) -> str:
            """
            Cleans up D-Bus menu item labels, removing mnemonics.
            """
            if not isinstance(label, str) or not label:
                return ""
            label = label.replace("_", "")
            return label.strip().capitalize()

        async def _build_menu_manually(
            self, listbox, menu_data: list, service_name: str
        ):
            """
            Builds the Gtk.ListBox and Gtk.ListBoxRows from the parsed menu data.
            """
            if not menu_data:
                row = Gtk.ListBoxRow()
                row.set_child(Gtk.Label(label="No actions available", xalign=0.5))
                row.set_sensitive(False)
                row.set_margin_top(8)
                row.set_margin_bottom(8)
                listbox.append(row)
                return
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
                    if not image:
                        if pixbuf := self.create_pixbuf_from_pixels(icon_data):
                            image = Gtk.Image.new_from_pixbuf(pixbuf)
                if image:
                    box.append(image)
                label = Gtk.Label(label=label_text, xalign=0)
                label.set_hexpand(True)
                box.append(label)
                row.set_child(box)
                if submenu_data := item.get("submenu"):
                    submenu_popover = Gtk.Popover()
                    submenu_listbox = Gtk.ListBox()
                    submenu_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
                    submenu_listbox.connect(
                        "row-activated", self._on_listbox_row_activated, service_name
                    )
                    submenu_popover.set_child(submenu_listbox)
                    submenu_arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
                    box.append(submenu_arrow)
                    submenu_popover.set_parent(row)
                    row._submenu_popover = submenu_popover  # pyright: ignore
                    await self._build_menu_manually(
                        submenu_listbox, submenu_data, service_name
                    )
                row.set_name(str(item["id"]))
                row.set_sensitive(item.get("enabled", True))
                row.set_activatable(item.get("enabled", True))
                listbox.append(row)

        def get_best_icon_entry(self, pixmap_data: list, target_size: int = 24):
            """
            Selects the best icon from a list of (width, height, data) tuples.
            """
            if not pixmap_data:
                return None
            return min(pixmap_data, key=lambda x: abs(x[0] - target_size))

        def create_menubutton(self, menu_structure, service_name: str):
            """
            Creates the main Gtk.MenuButton for the tray icon.
            """
            if service_name not in self.messages:
                self.logger.error(
                    f"Cannot create menubutton for {service_name}: No message data."
                )
                return None
            message_data = self.messages[service_name]
            icon_name = message_data["icon_name"]
            menubutton = self.gtk.MenuButton()
            self.add_cursor_effect(menubutton)
            if icon_pixmap_data := message_data.get("icon_pixmap"):
                if pixbuf := self.create_pixbuf_from_pixels(icon_pixmap_data):
                    menubutton.set_child(self.gtk.Image.new_from_pixbuf(pixbuf))
                else:
                    menubutton.set_icon_name(icon_name)
            else:
                menubutton.set_icon_name(icon_name)
            menubutton.add_css_class("tray-icon")
            if tooltip_variant := message_data.get("tooltip"):
                try:
                    icon_name, icon_data, title, text = tooltip_variant.value
                    if title and text:
                        menubutton.set_tooltip_text(f"{title}\n{text}")
                    elif title:
                        menubutton.set_tooltip_text(title)
                except Exception:
                    pass
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
            """
            Handles plugin stop logic.
            """
            self.logger.info("SystrayClientPlugin has stopped.")

        def on_reload(self):
            """
            Handles plugin reload logic.
            """
            self.logger.info("SystrayClientPlugin has been reloaded.")

        def on_cleanup(self):
            """
            Handles plugin cleanup logic.
            """
            self.logger.info("SystrayClientPlugin is cleaning up resources.")

    return SystrayClientPlugin
