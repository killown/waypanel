import os
import sys
import json as js
import argparse
import shutil
from subprocess import call, check_output, run, Popen
import subprocess
import asyncio
import time
import dbus
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.extra.stipc import Stipc
from wayfire.extra.wpe import WPE

sock = WayfireSocket()
stipc = Stipc(sock)
utils = WayfireUtils(sock)
wpe = WPE(sock)


class Wayctl:
    def __init__(self):
        self.ws_utils = WayfireUtils(sock)
        self.parser = argparse.ArgumentParser(
            description="wayctl script utility for controlling parts of the wayfire compositor through the command line interface or a script."
        )
        self.parser.add_argument(
            "--dpms",
            nargs="*",
            help="Set DPMS (Display Power Management Signaling) state. Usage: --dpms on/off/toggle <monitor-name> (to turn DPMS on, off, or toggle its state for the specified monitor).",
        )
        self.parser.add_argument(
            "--screenshot",
            nargs="*",
            help="Capture screenshots with various options. Usage: --screenshot focused view (to capture a screenshot of the focused view), --screenshot slurp (to select a region to screenshot), --screenshot output all (to capture screenshots of all outputs).",
        )
        self.parser.add_argument(
            "--pastebin",
            action="store_true",
            help="Upload clipboard to 0x0.st and copy URL",
        )
        self.parser.add_argument(
            "--colorpicker",
            nargs="*",
            help="Color picker using slurp and grim",
        )
        self.parser.add_argument(
            "--move-view-to-empty-workspace",
            nargs="*",
            help="move the focused view to an empty workspace",
        )
        self.args = self.parser.parse_args()
        self.args = self.parser.parse_args()
        self.sock = sock

    def dpms_status(self):
        status = check_output(["wlopm"]).decode().strip().split("\n")
        dpms_status = {}
        for line in status:
            line = line.split()
            dpms_status[line[0]] = line[1]
        return dpms_status

    def dpms_manager(self, state, output_name=None):
        if state == "off" and output_name is None:
            outputs = [output["name"] for output in sock.list_outputs()]
            for output in outputs:
                call("wlopm --off {}".format(output).split())
        if state == "on" and output_name is None:
            outputs = [output["name"] for output in sock.list_outputs()]
            for output in outputs:
                call("wlopm --on {}".format(output).split())
        if state == "on":
            call("wlopm --on {}".format(output_name).split())
        if state == "off":
            call("wlopm --off {}".format(output_name).split())
        if state == "toggle":
            call("wlopm --toggle {}".format(output_name).split())

    def xdg_open(self, path):
        call("xdg-open {0}".format(path).split())

    def move_view_to_empty_workspace(self):
        try:
            active_workspace_views = utils.get_views_from_active_workspace()
            all_views = sock.list_views()
            toplevel_mapped_views = [
                view
                for view in all_views
                if view["id"] in active_workspace_views
                and view["role"] == "toplevel"
                and view["mapped"]
            ]
            if not toplevel_mapped_views:
                utils.go_next_workspace_with_views()
                return
            workspaces_without_views = utils.get_workspaces_without_views()
            if not workspaces_without_views:
                print("No empty workspace found.")
                return
            target_workspace = workspaces_without_views[0]
            focused_view = sock.get_focused_view()
            if not focused_view:
                print("No focused view found.")
                return
            focused_view_id = focused_view["id"]
            sock.set_workspace(
                target_workspace[0], target_workspace[1], focused_view_id
            )
            print(
                f"Moved view {focused_view_id} to workspace ({target_workspace[0]}, {target_workspace[1]})"
            )
        except Exception as e:
            print(f"Error moving view: {e}")

    def screenshot_all_outputs(self):
        bus = dbus.SessionBus()
        desktop = bus.get_object(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
        )
        desktop.Screenshot(
            "Screenshot",
            {"handle_token": "my_token"},
            dbus_interface="org.freedesktop.portal.Screenshot",
        )
        time.sleep(1)
        self.xdg_open("/tmp/out.png")

    def screenshot_focused_monitor(self):
        output = sock.get_focused_output()
        name = output["name"]
        output_file = "/tmp/output-{0}.png".format(name)
        call(["grim", "-o", name, output_file])
        self.xdg_open(output_file)

    def get_absolute_geometry(self):
        sock = WayfireSocket()

        view = sock.get_focused_view()
        output = sock.get_focused_output()

        if not view or not output:
            return None

        # Calculate absolute position
        abs_x = output["geometry"]["x"] + view["geometry"]["x"]
        abs_y = output["geometry"]["y"] + view["geometry"]["y"]
        width = view["geometry"]["width"]
        height = view["geometry"]["height"]

        return f"{abs_x},{abs_y} {width}x{height}"

    async def capture_view(self):
        region = self.get_absolute_geometry()
        if not region:
            return

        output_path = "/tmp/focused_view.png"

        # Using grim with the calculated global geometry
        try:
            subprocess.run(["grim", "-g", region, output_path], check=True)
        except FileNotFoundError:
            pass

    def screenshot(self, id, filename):
        self.screenshot_focused_output()

    def screenshot_view_focused(self):
        asyncio.run(self.capture_view())
        output_file = "/tmp/focused_view.png"
        self.xdg_open(output_file)

    def screenshot_focused_output(self):
        self.screenshot_focused_monitor()

    def run_slurp(self):
        return check_output(["slurp"]).decode().strip()

    def screenshot_slurp(self):
        slurp = self.run_slurp()
        focused = self.sock.get_focused_view()
        view_id = focused["id"]
        app_id = focused["app-id"]
        filename = f"/tmp/{app_id}-{view_id}.png"
        if os.path.exists(filename):
            os.remove(filename)
        cmd = ["grim", "-g", f"{slurp}", filename]
        call(cmd)
        Popen(["xdg-open", filename])

    def screenshot_slurp_focused_view(self):
        self.screenshot_view_focused()
        time.sleep(1)
        slurp = self.run_slurp()
        focused = self.sock.get_focused_view()
        view_id = focused["id"]
        app_id = focused["app-id"]
        filename = f"/tmp/{app_id}-{view_id}.png"
        if os.path.exists(filename):
            os.remove(filename)
        cmd = ["grim", "-g", f"{slurp}", filename]
        call(cmd)
        Popen(["xdg-open", filename])

    def pastebin_upload(self):
        """
        Uploads clipboard content to 0x0.st using system curl.

        WHY CURL IS USED INSTEAD OF PYTHON MODULES:
        Fingerprint Matching: 0x0.st (and similar services) aggressively block
           Python-requests/HTTPX User-Agents and TLS fingerprints with 403 Forbidden.
           Native curl provides the 'standard' handshake the server expects.
        """
        try:
            data = check_output(["wl-paste"], text=False)
            if not data:
                run(["notify-send", "0x0.st", "Clipboard is empty"])
                return

            result = run(
                ["curl", "-F", "file=@-", "https://0x0.st"],
                input=data,
                capture_output=True,
                text=False,
                check=True,
            )

            url_bytes = result.stdout.strip()

            if url_bytes.startswith(b"https://"):
                url = url_bytes.decode()
                run(["wl-copy"], input=url_bytes, check=True)
                run(
                    [
                        "notify-send",
                        "--action=open=Open Link",
                        "0x0.st",
                        f"URL Copied: {url}",
                    ]
                )

                if os.fork() == 0:
                    action = run(
                        [
                            "notify-send",
                            "--action=open=Open Link",
                            "0x0.st",
                            f"URL Copied: {url}",
                        ],
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    if action == "open":
                        run(["xdg-open", url])
                    sys.exit(0)
            else:
                run(
                    [
                        "notify-send",
                        "0x0.st Error",
                        f"Unexpected response: {url_bytes.decode()}",
                    ]
                )

        except Exception as e:
            run(["notify-send", "0x0.st Error", f"Upload failed: {str(e)}"])

    def color_picker(self):
        def get_color_at_position(x, y):
            command = ["grim", "-g", f"{int(x)},{int(y)} 1x1", "-t", "ppm", "-"]
            result = run(command, capture_output=True, check=True)
            ppm_data = result.stdout.split(b"\n", 3)[3]
            r, g, b = ppm_data[:3]
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            return hex_color

        try:
            cursor_x, cursor_y = sock.get_cursor_position()
            color = get_color_at_position(cursor_x, cursor_y)
            run(["wl-copy"], input=color.encode(), check=True)
        except Exception as e:
            print(f"Error in color picker: {e}", file=sys.stderr)

    def screenshot_view_id(self, view_id, filename):
        self.screenshot(view_id, filename)

    def create_directory(self, directory):
        if os.path.exists(directory):
            shutil.rmtree(directory)
        os.makedirs(directory)

    def screenshot_view_list(self):
        self.create_directory("/tmp/screenshots")
        for view in self.sock.list_views():
            view_id = view["id"]
            filename = str(view_id) + ".png"
            filename = os.path.join("/tmp/screenshots", filename)
            self.screenshot(view_id, filename)
        Popen("xdg-open /tmp/screenshots".split())

    def dpms(self):
        if "off_all" in self.args.dpms:
            self.dpms_manager("off")
        if "on_all" in self.args.dpms:
            self.dpms_manager("on")
        if "on" in self.args.dpms:
            monitor_name = self.args.dpms[-1].strip()
            self.dpms_manager("on", monitor_name)
        if "off" in self.args.dpms:
            if "timeout" in self.args.dpms:
                monitor_name = self.args.dpms[1].strip()
                timeout = int(self.args.dpms[3].strip())
                time.sleep(int(timeout))
                self.dpms_manager("off", monitor_name)
            else:
                self.dpms_manager("off")
        if "toggle" in self.args.dpms:
            monitor_name = self.args.dpms[-1].strip()
            focused_output = self.sock.get_focused_output()
            monitor_name = focused_output["name"]
            self.dpms_manager("toggle", monitor_name)

    def view_list(self):
        views = self.sock.list_views()
        focused_view = self.sock.get_focused_view()
        focused_view_id = focused_view["id"]
        has_title = None
        if "has_title" in self.args.view:
            has_title = self.args.view.split("has_title ")[-1].strip()
        for view in views:
            if view["id"] == focused_view_id:
                continue
            title = view["title"].lower()
            if has_title is not None:
                if has_title not in title:
                    continue
            print("[{0}: {1}]".format(view["app-id"], view["title"]))
            view = js.dumps(view)
            print(view)
            print("\n\n")


if __name__ == "__main__":
    wayctl = Wayctl()
    if wayctl.args.pastebin:
        wayctl.pastebin_upload()
    if wayctl.args.dpms is not None:
        wayctl.dpms()
    if wayctl.args.colorpicker is not None:
        wayctl.color_picker()
    if wayctl.args.move_view_to_empty_workspace is not None:
        wayctl.move_view_to_empty_workspace()
    if wayctl.args.screenshot is not None:
        if "focused" in wayctl.args.screenshot[0]:
            if "view" in wayctl.args.screenshot[1]:
                wayctl.screenshot_view_focused()
        if "slurp" in wayctl.args.screenshot[0]:
            if len(wayctl.args.screenshot) == 1:
                wayctl.screenshot_slurp()
            if "focused" in wayctl.args.screenshot[1]:
                if "view" in wayctl.args.screenshot[2]:
                    wayctl.screenshot_slurp_focused_view()
        if "focused" in wayctl.args.screenshot[0]:
            if "output" in wayctl.args.screenshot[1]:
                wayctl.screenshot_focused_output()
        if "output" in wayctl.args.screenshot[0]:
            if "all" in wayctl.args.screenshot[1]:
                wayctl.screenshot_all_outputs()
        if "view" in wayctl.args.screenshot[0]:
            if "all" in wayctl.args.screenshot[1]:
                wayctl.screenshot_view_list()
