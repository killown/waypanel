def get_plugin_metadata(panel):
    return {
        "id": "org.waypanel.plugin.monitor_devices",
        "name": "Hardware Monitor",
        "version": "4.7.1",
        "enabled": True,
        "container": "top-panel-center",
        "deps": ["css_generator"],
        "description": "GTK4 Hardware monitor with Mount/Eject controls.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    from gi.repository import Gtk, Gio, Adw
    import subprocess
    import os
    import sys

    # Import the watcher locally
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.append(plugin_dir)
    from _watch_devices import DeviceWatcher

    class USBMonitorPlugin(BasePlugin):
        def on_start(self):
            self.connected = {}
            self.watcher = None
            self.plugins["css_generator"].install_css("monitor-devices.css")

            # Register settings for Control Center
            self.get_plugin_setting_add_hint(
                "behavior/auto_open",
                False,
                "Automatically open file manager when a device is mounted",
            )

            # GTK4 MenuButton
            self.button = Gtk.MenuButton()
            self.button.set_icon_name("media-removable-symbolic")
            self.button.set_visible(False)
            self.button.add_css_class("usb-monitor-button")

            # GTK4 Popover
            self.popover = Gtk.Popover()
            self.popover.add_css_class("usb-monitor-popover")

            self.popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.popover_box.set_margin_start(12)
            self.popover_box.set_margin_end(12)
            self.popover_box.set_margin_top(12)
            self.popover_box.set_margin_bottom(12)
            self.popover_box.add_css_class("usb-monitor-container")

            self.popover.set_child(self.popover_box)
            self.button.set_popover(self.popover)
            self.main_widget = (self.button, "append")

        def on_enable(self):
            if not self.watcher:
                self.watcher = DeviceWatcher(self._handle_event)
                self.watcher.start()

        def _handle_event(
            self, action, did, name, vendor, is_joy, mount_path, dev_node
        ):
            if action == "add":
                if did not in self.connected:
                    self.connected[did] = {
                        "name": name,
                        "node": dev_node,
                        "path": mount_path,
                    }

                    if mount_path:
                        self.button.set_visible(True)
                        self._rebuild_ui()

                        if self.get_plugin_setting("behavior/auto_open"):
                            subprocess.Popen(["xdg-open", str(mount_path)])

                    self.notify_send(
                        title=f"{'Joypad' if is_joy else 'Storage'} Connected",
                        message=f"{name}\n{vendor}",
                        icon="joypad-symbolic"
                        if is_joy
                        else "media-removable-symbolic",
                    )

            elif action == "remove":
                if did in self.connected:
                    self.connected.pop(did, None)
                    if not any(v.get("path") for v in self.connected.values()):
                        self.button.set_visible(False)
                    self._rebuild_ui()

        def _rebuild_ui(self):
            child = self.popover_box.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.popover_box.remove(child)
                child = next_child

            for data in self.connected.values():
                if not data.get("path"):
                    continue

                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                row.add_css_class("usb-device-row")

                label = Gtk.Label(label=data["name"])
                label.add_css_class("heading")
                label.add_css_class("usb-device-label")
                row.append(label)

                btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                btn_box.add_css_class("usb-action-box")

                open_btn = Gtk.Button(label="Open")
                open_btn.add_css_class("suggested-action")
                open_btn.add_css_class("usb-open-button")
                open_btn.connect("clicked", lambda *_: self._open_device(data["path"]))

                eject_btn = Gtk.Button(label="Eject")
                eject_btn.add_css_class("destructive-action")
                eject_btn.add_css_class("usb-eject-button")
                eject_btn.connect(
                    "clicked", lambda *_: self._run_eject_sequence(data["node"])
                )

                btn_box.append(open_btn)
                btn_box.append(eject_btn)
                row.append(btn_box)
                self.popover_box.append(row)

        def _open_device(self, path):
            self.popover.popdown()
            subprocess.Popen(["xdg-open", str(path)])

        def _run_eject_sequence(self, node):
            self.popover.popdown()
            subprocess.run(["udisksctl", "unmount", "-b", str(node)])
            subprocess.run(["udisksctl", "power-off", "-b", str(node)])

        def on_disable(self):
            if self.watcher:
                self.watcher.stop()
                self.watcher = None
            self.button.set_visible(False)

    return USBMonitorPlugin
