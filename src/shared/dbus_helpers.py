class DbusHelpers:
    """
    Centralized D-Bus manager for Waypanel plugins.
    Bypasses broken Chromium/Edge introspection by using static interface definitions.
    """

    # Static XML for MPRIS Player interface to bypass empty introspection bugs
    MPRIS_PLAYER_XML = """
    <node>
      <interface name="org.mpris.MediaPlayer2.Player">
        <method name="Next"/>
        <method name="Previous"/>
        <method name="PlayPause"/>
        <method name="Stop"/>
        <method name="Play"/>
        <method name="Pause"/>
        <property name="PlaybackStatus" type="s" access="read"/>
        <property name="Metadata" type="a{sv}" access="read"/>
        <property name="CanGoNext" type="b" access="read"/>
        <property name="CanGoPrevious" type="b" access="read"/>
        <property name="CanPlay" type="b" access="read"/>
        <property name="CanPause" type="b" access="read"/>
        <property name="CanControl" type="b" access="read"/>
      </interface>
    </node>
    """

    def __init__(self, bus):
        self.bus = bus
        self._proxy_cache = {}

    async def get_interface(self, service: str, path: str, iface_name: str):
        """Retrieves or creates a cached proxy interface with fallback logic."""
        cache_key = f"{service}{path}{iface_name}"
        if cache_key in self._proxy_cache:
            return self._proxy_cache[cache_key]

        try:
            # Try standard introspection
            introspection = await self.bus.introspect(service, path)

            # If introspection is hollow (Edge/Chromium bug), use Static Fallback
            if not introspection.interfaces or iface_name not in [
                i.name for i in introspection.interfaces
            ]:
                from dbus_fast.introspection import Node

                introspection = Node.parse(self.MPRIS_PLAYER_XML)

            proxy = self.bus.get_proxy_object(service, path, introspection)
            iface = proxy.get_interface(iface_name)

            self._proxy_cache[cache_key] = iface
            return iface
        except Exception:
            return None

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

            if not iface:
                return None

            # Get properties (dbus-fast will now use the static template to map these)
            raw_meta = await iface.get_metadata()
            status = await iface.get_playback_status()
            can_next = await iface.get_can_go_next()
            can_prev = await iface.get_can_go_previous()

            def v(key, default=None):
                if key in raw_meta:
                    val = raw_meta[key].value
                    if key == "xesam:artist" and isinstance(val, list):
                        return val[0] if val else "Unknown"
                    return val
                return default

            return {
                "title": v("xesam:title", "Unknown"),
                "artist": v("xesam:artist", "Unknown"),
                "art_url": v("mpris:artUrl", ""),
                "status": status,
                "can_next": can_next,
                "can_prev": can_prev,
                "player": player_name,
            }
        except Exception:
            # Clear stale instance cache on failure
            keys = [k for k in self._proxy_cache if k.startswith(player_name)]
            for k in keys:
                del self._proxy_cache[k]
            return None

    async def player_action(self, player_name: str, action: str):
        """Executes playback methods safely."""
        try:
            iface = await self.get_interface(
                player_name, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player"
            )
            if not iface:
                return False

            if action == "next":
                await iface.call_next()
            elif action == "previous":
                await iface.call_previous()
            elif action == "play_pause":
                await iface.call_play_pause()
            return True
        except Exception:
            return False
