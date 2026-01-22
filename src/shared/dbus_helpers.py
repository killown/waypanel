# ==== FILE: src/shared/dbus_helpers.py ====


class DbusHelpers:
    """
    Centralized D-Bus manager for Waypanel plugins.
    Handles MPRIS media controls, metadata extraction, and proxy caching.
    """

    def __init__(self, bus):
        self.bus = bus
        self._proxy_cache = {}

    async def get_interface(self, service: str, path: str, iface_name: str):
        """Retrieves or creates a cached proxy interface with auto-introspection."""
        cache_key = f"{service}{path}{iface_name}"
        if cache_key not in self._proxy_cache:
            introspection = await self.bus.introspect(service, path)
            proxy = self.bus.get_proxy_object(service, path, introspection)
            self._proxy_cache[cache_key] = proxy.get_interface(iface_name)
        return self._proxy_cache[cache_key]

    async def get_active_mpris_players(self):
        """Finds all active players using the DBus ListNames method."""
        from dbus_fast import Message

        reply = await self.bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="ListNames",
            )
        )
        return [n for n in reply.body[0] if n.startswith("org.mpris.MediaPlayer2")]

    async def get_media_metadata(self, player_name: str):
        """Extracts variants and playback status into a clean dictionary."""
        try:
            iface = await self.get_interface(
                player_name, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player"
            )

            raw_meta = await iface.get_metadata()
            status = await iface.get_playback_status()
            can_next = await iface.get_can_go_next()
            can_prev = await iface.get_can_go_previous()

            def v(key, default=None):
                return raw_meta[key].value if key in raw_meta else default

            return {
                "title": v("xesam:title", "Unknown"),
                "artist": v("xesam:artist", ["Unknown"])[0],
                "art_url": v("mpris:artUrl", ""),
                "status": status,
                "can_next": can_next,
                "can_prev": can_prev,
                "player": player_name,
            }
        except Exception:
            return None

    async def player_action(self, player_name: str, action: str):
        """Executes playback methods safely with capability checks."""
        from dbus_fast import DBusError

        try:
            iface = await self.get_interface(
                player_name, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player"
            )

            if action == "next":
                if await iface.get_can_go_next():
                    await iface.call_next()
            elif action == "previous":
                if await iface.get_can_go_previous():
                    await iface.call_previous()
            elif action == "play_pause":
                await iface.call_play_pause()

            return True
        except (DBusError, Exception):
            return False


# ==== END OF FILE: src/shared/dbus_helpers.py ====
