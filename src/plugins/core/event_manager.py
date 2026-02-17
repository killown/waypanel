def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.event_manager",
        "name": "Event Manager",
        "version": "2.0.0",
        "enabled": True,
        "description": (
            "Core background service acting as a central zero-latency event bus.",
            "Uses direct-execution routing to dispatch compositor events to subscribers with efficiency",
            ", ensuring absolute state consistency by bypassing main-loop batching.",
        ),
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    import collections
    import os

    class EventManagerPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

        def on_start(self):
            from src.ipc.client import WayfireClientIPC

            self._routers = {
                "view-": self.handle_view_event,
                "plugin-": self.handle_plugin_event,
                "output-": self.handle_output_event,
            }

            self.event_subscribers = collections.defaultdict(list)
            self.ipc_client = WayfireClientIPC(self.handle_event, self.obj)
            self.ipc_client.wayfire_events_setup(self.get_runtime_socket_path())

        def get_runtime_socket_path(self) -> str:
            return os.path.join(
                os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "waypanel.sock"
            )

        def handle_event(self, msg: dict) -> None:
            """Direct execution entry point from IPC thread."""
            etype = msg.get("event")
            if not etype:
                return

            # Subscribers must now handle their own thread safety if they touch GTK
            subs = self.event_subscribers.get(etype)
            if subs:
                for callback, _ in subs:
                    try:
                        callback(msg)
                    except Exception as e:
                        self.logger.error(f"Subscriber error: {e}")

            # Fast Routing via prefix matching
            prefix = etype[: etype.find("-") + 1]
            handler = self._routers.get(prefix)
            if handler:
                handler(msg)

        def handle_view_event(self, msg: dict) -> None:
            view, ev = msg.get("view"), msg.get("event")
            if not view or view.get("pid") == -1 or view.get("role") != "toplevel":
                return

            aid = view.get("app-id")
            if not aid or aid in (" ", "nil"):
                return

            if ev == "view-unmapped":
                self.on_view_destroyed(view)
            elif ev == "view-focused":
                self.on_view_focused(view)
            elif ev == "view-mapped":
                self.on_view_created(view)
            elif ev == "view-title-changed":
                self.on_title_changed(view)

        def handle_plugin_event(self, msg: dict) -> None:
            plugin, state = msg.get("plugin"), msg.get("state")
            if plugin == "expo":
                self.on_expo_activated() if state else self.on_expo_desactivated()
            elif plugin == "scale":
                self.on_scale_activated() if state else self.on_scale_desactivated()

        def handle_output_event(self, msg: dict) -> None:
            if msg.get("event") == "output-gain-focus":
                self.on_output_gain_focus()

        def subscribe_to_event(self, event_type, callback, plugin_name=None) -> None:
            self.event_subscribers[event_type].append((callback, plugin_name))

        def unsubscribe_from_event(self, event_type, callback) -> None:
            if event_type in self.event_subscribers:
                self.event_subscribers[event_type] = [
                    s for s in self.event_subscribers[event_type] if s[0] != callback
                ]

        def on_view_focused(self, v):
            self.logger.debug(f"Focus: {v.get('app-id')}")

        def on_view_created(self, v):
            self.logger.debug(f"Map: {v.get('app-id')}")

        def on_view_destroyed(self, v):
            self.logger.debug("Unmap")

        def on_title_changed(self, v):
            pass

        def on_expo_activated(self):
            pass

        def on_expo_desactivated(self):
            pass

        def on_scale_activated(self):
            pass

        def on_scale_desactivated(self):
            pass

        def on_output_gain_focus(self):
            pass

    return EventManagerPlugin
