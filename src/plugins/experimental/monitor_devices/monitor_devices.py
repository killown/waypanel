def get_plugin_metadata(panel):
    return {
        "id": "org.waypanel.plugin.monitor_devices",
        "name": "USB Monitor",
        "version": "2.4.0",
        "enabled": True,
        "container": "background",
        "deps": [],
        "description": "Process-cycling hardware monitor with explicit termination.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    import subprocess
    import sys
    import os

    class USBMonitorPlugin(BasePlugin):
        def on_start(self):
            self.connected = {}
            self.monitor_active = False
            self.current_process = None

            # Resolve script path locally
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            self.script_path = os.path.join(plugin_dir, "_monitor_devices.py")

        def on_enable(self):
            self.monitor_active = True
            self.run_in_thread(self._cycle_manager)

        def _cycle_manager(self):
            """Restarts the script process every time it exits/terminates."""
            while self.monitor_active:
                try:
                    # Spawn the logic script
                    self.current_process = subprocess.Popen(
                        [sys.executable, self.script_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,  # Line buffered
                    )

                    # Read the one-line output (the script kills itself after printing)
                    output = self.current_process.stdout.readline()
                    if output:
                        self._handle_event_data(output.strip())

                    # Wait for the process to fully terminate before cycling
                    self.current_process.wait()
                    self.current_process = None

                except Exception as e:
                    self.logger.error(f"Monitor process cycle failure: {e}")
                    self.time.sleep(1)

        def _handle_event_data(self, data):
            try:
                action, did, name, vendor = data.split("|")

                if action == "add" and did not in self.connected:
                    self.connected[did] = name
                    self.notify_send(
                        title="Device Connected",
                        message=f"{name}\nVendor: {vendor}",
                        icon="drive-removable-media-usb-symbolic",
                    )
                elif action == "remove" and did in self.connected:
                    self.connected.pop(did)
                    self.notify_send(
                        title="Device Disconnected",
                        message=f"{name}",
                        icon="drive-removable-media-usb-symbolic",
                    )
            except ValueError:
                pass

        def on_disable(self):
            """LIFECYCLE: Explicitly kill the logic script on plugin disable."""
            self.monitor_active = False
            if self.current_process:
                self.current_process.kill()
                self.current_process.wait()
                self.current_process = None

    return USBMonitorPlugin
