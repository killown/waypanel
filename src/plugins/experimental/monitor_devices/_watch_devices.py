import pyudev
import subprocess
import time
from pyudev.glib import MonitorObserver


class DeviceWatcher:
    """Persistent udev monitor for Joysticks and Auto-mounting USB drives."""

    def __init__(self, callback):
        self.callback = callback
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.observer = MonitorObserver(self.monitor)
        self.observer.connect("device-event", self._on_event)

    def start(self):
        self.monitor.start()

    def stop(self):
        self.monitor.stop()

    def _find_mountpoint(self, devnode):
        try:
            with open("/proc/self/mounts") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == devnode:
                        return parts[1]
        except Exception:
            pass
        return None

    def _on_event(self, observer, device):
        action = device.action
        is_joy = device.properties.get("ID_INPUT_JOYSTICK") == "1"
        is_block = device.get("SUBSYSTEM") == "block"
        is_partition = device.get("DEVTYPE") == "partition"

        if not (is_joy or (is_block and is_partition)):
            return

        did = device.properties.get("ID_SERIAL") or device.sys_path
        raw_name = (
            device.get("ID_FS_LABEL") or device.get("ID_MODEL") or "Unknown Device"
        )
        name = " ".join(raw_name.replace("-", " ").replace("_", " ").split())

        if name.upper().startswith(("EFI", "VTOY")):
            return

        mount_path = None
        dev_node = device.get("DEVNAME")

        if action == "add" and is_block:
            subprocess.run(
                ["udisksctl", "mount", "-b", dev_node],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(10):
                mount_path = self._find_mountpoint(dev_node)
                if mount_path:
                    break
                time.sleep(0.5)

        vendor = device.get("ID_VENDOR", "Unknown").replace("-", " ").replace("_", " ")
        self.callback(action, did, name, vendor, is_joy, mount_path, dev_node)
