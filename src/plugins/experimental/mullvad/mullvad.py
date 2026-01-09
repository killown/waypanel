def get_plugin_metadata(_):
    about = (
        "This plugin provides a graphical user interface for managing the",
        "Mullvad VPN client directly from the Wayfire panel.",
    )
    return {
        "id": "org.waypanel.plugin.mullvad",
        "name": "Mullvad VPN",
        "version": "1.9.0",
        "enabled": True,
        "index": 8,
        "container": "top-panel-systray",
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    import random
    import aiohttp
    from collections import defaultdict
    from src.plugins.core._base import BasePlugin

    class MullvadPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.mullvad_version = None
            self.city_code = self.get_plugin_setting_add_hint(
                ["city_code"], "sao", "Default city code for relay selection."
            )
            self.menubutton_mullvad = self.gtk.MenuButton()
            self.status_container = None
            self.account_container = None
            self.location_list_container = None
            self.toggle_button = None
            self.search_entry = None
            self.relays_cache = {}
            self.is_connected = False
            self.main_widget = (self.menubutton_mullvad, "append")

        def on_start(self):
            self.run_in_async_task(self._async_init_setup())

        async def _async_init_setup(self):
            self.mullvad_version = await self.asyncio.to_thread(self._get_version)
            self.icon_name = "mullvad-vpn"

            self.menubutton_mullvad.set_icon_name(self.icon_name)
            self.menubutton_mullvad.add_css_class("top_right_widgets")
            self.gtk_helper.add_cursor_effect(self.menubutton_mullvad)

            popover_content = self._create_popover_ui()
            self.popover_mullvad = self.gtk.Popover()
            self.popover_mullvad.set_child(popover_content)
            self.menubutton_mullvad.set_popover(self.popover_mullvad)

            self.popover_mullvad.connect(
                "map", lambda _: self.run_in_async_task(self.refresh_all())
            )

            if self.os.path.exists("/usr/bin/mullvad"):
                self.glib.timeout_add(10000, self._trigger_status_update)

        def _create_popover_ui(self):
            main_vbox = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=0
            )
            main_vbox.set_size_request(350, 350)

            stack = self.gtk.Stack()
            stack.set_transition_type(self.gtk.StackTransitionType.SLIDE_LEFT_RIGHT)

            switcher = self.gtk.StackSwitcher()
            switcher.set_stack(stack)
            switcher.set_halign(self.gtk.Align.CENTER)
            switcher.set_margin_top(12)
            switcher.set_margin_bottom(12)

            main_vbox.append(switcher)
            main_vbox.append(self.gtk.Separator())
            main_vbox.append(stack)

            # --- TAB 1: STATUS & ACCOUNT ---
            status_page = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=10
            )
            status_page.set_margin_start(16)
            status_page.set_margin_end(16)
            status_page.set_margin_top(16)
            status_page.set_margin_bottom(16)

            self.status_container = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=6
            )
            status_page.append(self.status_container)

            status_page.append(self.gtk.Separator())

            # Account Info Section with Privacy Reveal
            self.account_container = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=4
            )
            status_page.append(self.account_container)

            status_page.append(self.gtk.Separator())

            self.toggle_button = self.create_async_button(
                label="Checking...", callback=self._handle_toggle, css_class=""
            )
            status_page.append(self.toggle_button)

            for label, callback in [
                ("Reconnect", self.reconnect_vpn),
                (f"Random {self.city_code.upper()} Relay", self.set_relay_city),
                ("Random Global Relay", self.set_relay_global),
            ]:
                status_page.append(
                    self.create_async_button(
                        label=label, callback=callback, css_class=""
                    )
                )

            stack.add_titled(status_page, "status", "Status")

            # --- TAB 2: LOCATIONS ---
            loc_page = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=0
            )
            self.search_entry = self.gtk.SearchEntry()
            self.search_entry.set_margin_start(12)
            self.search_entry.set_margin_end(12)
            self.search_entry.set_margin_top(12)
            self.search_entry.set_margin_bottom(12)
            self.search_entry.connect("search-changed", self._on_search_changed)
            loc_page.append(self.search_entry)

            scroll = self.gtk.ScrolledWindow()
            scroll.set_vexpand(True)
            self.location_list_container = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=2
            )
            self.location_list_container.set_margin_start(12)
            self.location_list_container.set_margin_end(12)
            scroll.set_child(self.location_list_container)
            loc_page.append(scroll)
            stack.add_titled(loc_page, "locations", "Locations")

            return main_vbox

        async def refresh_all(self):
            """Refreshes status, resets account to hidden, and fetches relays."""
            await self.update_vpn_status()
            await self.fetch_relays()

            def _reset_account_ui():
                while child := self.account_container.get_first_child():
                    self.account_container.remove(child)

                reveal_btn = self.gtk.Button(label="Click to reveal account details")
                reveal_btn.add_css_class("suggested-action")
                reveal_btn.connect(
                    "clicked",
                    lambda _: self.run_in_async_task(self.lazy_load_account()),
                )
                self.account_container.append(reveal_btn)

            self.schedule_in_gtk_thread(_reset_account_ui)

        async def lazy_load_account(self):
            """Fetch and show Mullvad account details only on request."""
            try:
                proc = await self.asyncio.create_subprocess_exec(
                    "mullvad",
                    "account",
                    "get",
                    stdout=self.asyncio.subprocess.PIPE,
                    stderr=self.asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await proc.communicate()
                raw = stdout.decode().strip()
                details = {
                    l.split(":")[0].strip(): l.split(":")[1].strip()
                    for l in raw.split("\n")
                    if ":" in l
                }

                def _ui_update():
                    while child := self.account_container.get_first_child():
                        self.account_container.remove(child)

                    for k, v in details.items():
                        lbl = self.gtk.Label()
                        lbl.set_markup(
                            f"<span size='small' weight='bold' alpha='60%'>{k}:</span> <span size='small'>{v}</span>"
                        )
                        lbl.set_halign(self.gtk.Align.START)
                        lbl.set_selectable(True)
                        self.account_container.append(lbl)

                self.schedule_in_gtk_thread(_ui_update)
            except Exception as e:
                self.logger.error(f"Account fetch error: {e}")

        async def fetch_relays(self):
            url = "https://api.mullvad.net/www/relays/all/"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        relays = await resp.json()
                self.relays_cache = defaultdict(list)
                for r in relays:
                    if r.get("active"):
                        self.relays_cache[r.get("country_name", "Unknown")].append(r)
                self._render_relay_list()
            except Exception as e:
                self.logger.error(f"Relay fetch error: {e}")

        def _on_search_changed(self, entry):
            self._render_relay_list(entry.get_text().lower())

        def _render_relay_list(self, filter_text=""):
            def _ui_update():
                while child := self.location_list_container.get_first_child():
                    self.location_list_container.remove(child)

                for country in sorted(self.relays_cache.keys()):
                    relays = self.relays_cache[country]
                    filtered = [
                        r
                        for r in relays
                        if filter_text in country.lower()
                        or filter_text in r.get("city_name", "").lower()
                    ]
                    if not filtered:
                        continue

                    expander = self.gtk.Expander(label=country)
                    expander.set_expanded(bool(filter_text))
                    inner_vbox = self.gtk.Box(
                        orientation=self.gtk.Orientation.VERTICAL, spacing=4
                    )
                    inner_vbox.set_margin_start(16)

                    for r in sorted(filtered, key=lambda x: x.get("city_name")):
                        host = r["hostname"]
                        city = r.get("city_name", "Unknown")
                        btn = self.create_async_button(
                            label=f"{city} ({host})",
                            callback=lambda h=host: self._set_specific_relay(h),
                            css_class="",
                        )
                        btn.set_halign(self.gtk.Align.START)
                        inner_vbox.append(btn)

                    expander.set_child(inner_vbox)
                    self.location_list_container.append(expander)

            self.schedule_in_gtk_thread(_ui_update)

        async def _set_specific_relay(self, hostname):
            await self.asyncio.create_subprocess_exec(
                "mullvad", "relay", "set", "location", hostname
            )
            await self.asyncio.create_subprocess_exec("mullvad", "connect")
            self.notifier.notify_send(
                "Mullvad VPN", f"Connecting to {hostname}...", self.icon_name
            )
            self.glib.timeout_add(1200, self._trigger_status_update)

        async def update_vpn_status(self):
            try:
                proc = await self.asyncio.create_subprocess_exec(
                    "mullvad", "status", stdout=self.asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                raw = stdout.decode().strip()
                self.is_connected = "Connected" in raw
                lines = raw.split("\n")
                details = {
                    l.split(":")[0].strip(): l.split(":")[1].strip()
                    for l in lines[1:]
                    if ":" in l
                }

                def _ui_update():
                    while child := self.status_container.get_first_child():
                        self.status_container.remove(child)
                    color = "#2ecc71" if self.is_connected else "#e74c3c"
                    header = self.gtk.Label()
                    header.set_markup(
                        f"<span size='large' weight='bold' foreground='{color}'>{lines[0]}</span>"
                    )
                    header.set_halign(self.gtk.Align.START)
                    self.status_container.append(header)
                    for k, v in details.items():
                        lbl = self.gtk.Label()
                        lbl.set_markup(
                            f"<span weight='bold' alpha='70%'>{k}:</span> {v}"
                        )
                        lbl.set_halign(self.gtk.Align.START)
                        self.status_container.append(lbl)
                    self.toggle_button.set_label(
                        "Disconnect" if self.is_connected else "Connect"
                    )
                    self.menubutton_mullvad.set_icon_name(
                        self.icon_name if self.is_connected else "stock_disconnect"
                    )

                self.schedule_in_gtk_thread(_ui_update)
            except Exception as e:
                self.logger.error(f"Status error: {e}")

        def _trigger_status_update(self):
            self.run_in_async_task(self.update_vpn_status())
            return True

        async def _handle_toggle(self):
            cmd = "disconnect" if self.is_connected else "connect"
            await self.asyncio.create_subprocess_exec("mullvad", cmd)
            self.glib.timeout_add(800, self._trigger_status_update)

        async def reconnect_vpn(self):
            await self.asyncio.create_subprocess_exec("mullvad", "disconnect")
            await self.asyncio.create_subprocess_exec("mullvad", "connect")
            self.glib.timeout_add(800, self._trigger_status_update)

        async def set_relay_city(self):
            await self._set_relay(self.city_code)

        async def set_relay_global(self):
            await self._set_relay()

        async def _set_relay(self, city=None):
            url = "https://api.mullvad.net/www/relays/wireguard/"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    relays = await resp.json()
            targets = (
                [r for r in relays if r.get("city_code") == city] if city else relays
            )
            if targets:
                await self._set_specific_relay(random.choice(targets)["hostname"])

        def _get_version(self):
            try:
                return (
                    self.os.popen("mullvad --version")
                    .read()
                    .strip()
                    .replace("mullvad ", "")
                )
            except:
                return "Unknown"

    return MullvadPlugin
