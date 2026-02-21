def get_plugin_metadata(panel):
    id = "org.waypanel.xwayland_satellite"
    container = "background"

    return {
        "id": id,
        "name": "XWayland Satellite",
        "version": "1.0.0",
        "enabled": True,
        "container": container,
        "deps": [],
        "description": "Kills default Xwayland and manages xwayland-satellite on :1",
    }


def get_plugin_class():
    import os
    import psutil
    from src.plugins.core._base import BasePlugin

    class XWaylandSatellitePlugin(BasePlugin):
        """
        Plugin to manage xwayland-satellite for Wayfire environments.

        Setup Process:
            1. Wayfire MUST be launched with 'WLR_XWAYLAND=/dev/null' in the environment
               (via a wrapper script or .desktop file) to prevent the internal
               Xwayland from starting.

            2. To allow shells to detect the satellite, add these conditional exports:

               For Fish (~/.config/fish/config.fish):
               if pgrep -f xwayland-satellite > /dev/null
                   set -gx DISPLAY :1
               end

               For POSIX (~/.profile or ~/.bashrc):
               if pgrep -f xwayland-satellite > /dev/null 2>&1; then
                   export DISPLAY=:1
               fi

        Constraints:
            - Plugin stays idle if WLR_XWAYLAND is not /dev/null.
            - Uses `psutil` to prevent duplicate satellite instances.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.proc = None

        def on_enable(self):
            """LIFECYCLE: Entry point for logic."""
            if os.environ.get("WLR_XWAYLAND") != "/dev/null":
                self.logger.info("WLR_XWAYLAND is not /dev/null. Plugin idle.")
                return

            # Purge existing Xwayland instances (org.freedesktop.Xwayland)
            self._kill_internal_xwayland()

            if self._check_existing():
                self.logger.info("xwayland-satellite already running.")
                return

            # Use panel helper to schedule
            self.run_in_async_task(self._run_satellite())

        def _kill_internal_xwayland(self):
            """Kills processes matching the app-id org.freedesktop.Xwayland."""
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = " ".join(proc.info["cmdline"] or [])
                    if (
                        "Xwayland" in proc.info["name"]
                        or "org.freedesktop.Xwayland" in cmdline
                    ):
                        self.logger.info(
                            f"Killing internal Xwayland (PID: {proc.info['pid']})"
                        )
                        proc.kill()  # Hard kill to ensure socket release
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        def _check_existing(self) -> bool:
            """Check for xwayland-satellite using psutil."""
            for proc in psutil.process_iter(["name", "cmdline"]):
                try:
                    if "xwayland-satellite" in (proc.info["name"] or ""):
                        return True
                    cmdline = proc.info["cmdline"] or []
                    if any("xwayland-satellite" in arg for arg in cmdline):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False

        async def _run_satellite(self):
            """Starts xwayland-satellite and ensures DISPLAY=:1 is set."""
            wayland_display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
            xdg_runtime = (
                os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
            )
            socket_path = os.path.join(xdg_runtime, wayland_display)

            for _ in range(50):
                if os.path.exists(socket_path):
                    break
                await self.asyncio.sleep(0.1)

            os.environ["DISPLAY"] = ":1"

            try:
                self.logger.info("Starting xwayland-satellite on :1")
                self.proc = await self.asyncio.create_subprocess_exec(
                    "xwayland-satellite",
                    ":1",
                    stdout=self.asyncio.subprocess.DEVNULL,
                    stderr=self.asyncio.subprocess.DEVNULL,
                )
                await self.proc.wait()
            except Exception as e:
                self.logger.error(f"Satellite execution failed: {e}")

        def on_disable(self):
            """LIFECYCLE: Cleanup."""
            if self.proc:
                try:
                    self.proc.terminate()
                except (ProcessLookupError, AttributeError):
                    pass
                self.logger.info("xwayland-satellite process terminated.")

    return XWaylandSatellitePlugin
