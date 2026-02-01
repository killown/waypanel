import os
import sys
import json as js
from configparser import ConfigParser
import argparse
import shutil
from subprocess import call, check_output, run, Popen
import subprocess
import asyncio
import time
import dbus
import configparser
from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils
from wayfire.extra.stipc import Stipc
from wayfire.extra.wpe import WPE

sock = WayfireSocket()
stipc = Stipc(sock)
utils = WayfireUtils(sock)
wpe = WPE(sock)


class ViewDropDown:
    def __init__(self, term, width, height) -> None:
        pass
        self.TERMINAL_CMD = term
        self.TERMINAL_WIDTH = width
        self.TERMINAL_HEIGHT = height
        self.VIEW_STICKY = True
        self.VIEW_ALWAYS_ON_TOP = True
        addr = os.getenv("WAYFIRE_SOCKET")
        self.sock = WayfireSocket(addr)


class Wayctl:
    def __init__(self):
        self.ws_utils = WayfireUtils(sock)
        self.parser = argparse.ArgumentParser(
            description="wayctl script utility for controlling parts of the wayfire compositor through the command line interface or a script."
        )
        self.parser.add_argument(
            "--move_cursor",
            nargs="*",
            help="move mouse cursor position with <x-coordinate> <y-coordinate>",
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
            "--colorpicker",
            nargs="*",
            help="Color picker using slurp and grim",
        )
        self.parser.add_argument(
            "--plugin",
            nargs="*",
            help="manage plugins with -> enable, disable, restart, status",
        )
        self.parser.add_argument(
            "--drop",
            nargs="*",
            help="start a view in guake mode",
        )
        self.parser.add_argument(
            "--move-view-to-empty-workspace",
            nargs="*",
            help="move the focused view to an empty workspace",
        )
        self.args = self.parser.parse_args()
        self.args = self.parser.parse_args()
        self.sock = sock

    def get_wayfire_ini_path(self):
        wayfire_ini_path = os.getenv("WAYFIRE_CONFIG_FILE")
        if wayfire_ini_path:
            return wayfire_ini_path
        else:
            print("Error: WAYFIRE_CONFIG_FILE environment variable is not set.")
            return None

    def is_plugin_enabled(self, plugin):
        wayfire_ini_path = self.get_wayfire_ini_path()
        if not wayfire_ini_path:
            return
        config = ConfigParser()
        config.read(wayfire_ini_path)
        if "core" not in config:
            raise KeyError("Section 'core' not found in wayfire.ini")
        plugins = config.get("core", "plugins", fallback="").split()
        plugins = [p.strip() for p in plugins]
        if plugin in plugins:
            print("{0} is enabled".format(plugin))
        else:
            print("{0} is disabled".format(plugin))

    def activate_plugin(self, plugin_name):
        wayfire_ini_path = self.get_wayfire_ini_path()
        if not wayfire_ini_path:
            return
        config = ConfigParser()
        config.read(wayfire_ini_path)
        if "core" not in config:
            config["core"] = {}
        plugins = config["core"].get("plugins", "").split()
        if plugin_name in plugins:
            print(f"Plugin '{plugin_name}' is already enabled in wayfire.ini.")
            return
        plugins.append(plugin_name)
        config["core"]["plugins"] = " ".join(plugins)
        with open(wayfire_ini_path, "w") as configfile:
            config.write(configfile)
        print(f"Plugin '{plugin_name}' enabled successfully in wayfire.ini.")

    def disactivate_plugin(self, plugin_name):
        wayfire_ini_path = self.get_wayfire_ini_path()
        if not wayfire_ini_path:
            return
        config = ConfigParser()
        config.read(wayfire_ini_path)
        if "core" not in config:
            print("Error: 'core' section not found in wayfire.ini.")
            return
        plugins = config["core"].get("plugins", "").split()
        if plugin_name not in plugins:
            print(f"Plugin '{plugin_name}' is not enabled in wayfire.ini.")
            return
        plugins.remove(plugin_name)
        config["core"]["plugins"] = " ".join(plugins)
        with open(wayfire_ini_path, "w") as configfile:
            config.write(configfile)
        print(f"Plugin '{plugin_name}' disabled successfully in wayfire.ini.")

    def plugin_list(self):
        official_url = "https://github.com/WayfireWM/wayfire/tree/master/metadata"
        extra_url = (
            "https://github.com/WayfireWM/wayfire-plugins-extra/tree/master/metadata"
        )
        official_response = requests.get(official_url)
        extra_response = requests.get(extra_url)
        if official_response.status_code != 200 or extra_response.status_code != 200:
            print("Failed to fetch content from one or both repositories.")
            return {}
        official_html_content = official_response.text
        extra_html_content = extra_response.text
        official_start_index = official_html_content.find(
            '<script type="application/json" data-target="react-app.embeddedData">'
        )
        extra_start_index = extra_html_content.find(
            '<script type="application/json" data-target="react-app.embeddedData">'
        )
        official_end_index = official_html_content.find(
            "</script>", official_start_index
        )
        extra_end_index = extra_html_content.find("</script>", extra_start_index)
        official_json_data = official_html_content[
            official_start_index
            + len(
                '<script type="application/json" data-target="react-app.embeddedData">'
            ) : official_end_index
        ]
        extra_json_data = extra_html_content[
            extra_start_index
            + len(
                '<script type="application/json" data-target="react-app.embeddedData">'
            ) : extra_end_index
        ]
        official_data = js.loads(official_json_data)
        extra_data = js.loads(extra_json_data)
        official_plugin_names = [
            item["name"][:-4]
            for item in official_data["payload"]["tree"]["items"]
            if item["contentType"] == "file" and item["name"].endswith(".xml")
        ]
        extra_plugin_names = [
            item["name"][:-4]
            for item in extra_data["payload"]["tree"]["items"]
            if item["contentType"] == "file" and item["name"].endswith(".xml")
        ]
        return {
            "official-plugins": official_plugin_names,
            "extra-plugins": extra_plugin_names,
        }

    def list_enabled_plugins(self):
        wayfire_ini_path = self.get_wayfire_ini_path()
        if not wayfire_ini_path:
            return []
        config = ConfigParser()
        config.read(wayfire_ini_path)
        if "core" not in config:
            print("Error: 'core' section not found in wayfire.ini.")
            return []
        plugins = config["core"].get("plugins", "").split()
        return plugins

    def reload_plugins(self):
        filename = self.get_wayfire_ini_path()
        if not filename:
            return
        config = configparser.ConfigParser()
        config.read(filename)
        config["core"]["plugins"] = "# " + config["core"]["plugins"]
        with open(filename, "w") as configfile:
            config.write(configfile)
        config["core"]["plugins"] = (
            config["core"]["plugins"][2:]
            if config["core"]["plugins"].startswith("# ")
            else config["core"]["plugins"]
        )
        with open(filename, "w") as configfile:
            config.write(configfile)

    def reload_plugin(self, plugin_name):
        self.disable_plugin(plugin_name)

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

    def generate_screenshot_info(self, view_id, filename):
        font_size = 22
        font_filepath = "SourceCodePro-ExtraLight.otf"
        color = (80, 80, 80)
        view = self.sock.get_view(view_id)
        text = f"ID: {view['id']}, PID: {view['pid']}, Title: {view['title']}"
        font = ImageFont.truetype(font_filepath, size=font_size)
        mask_image = font.getmask(text, "L")
        size = mask_image.size[0] + 20, mask_image.size[1] + 20
        img = Image.new("RGBA", size)
        img.im.paste(color, (20, 20) + size, mask_image)
        img.save(filename)

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

    def list_plugins(self):
        plugins = self.plugin_list()
        for plugin in plugins:
            print(plugin)
            print(plugins[plugin])
            print("\n")
        print("Enabled Plugins ")
        print(self.list_enabled_plugins())

    def _reload_plugin(self, plugin_name):
        self.reload_plugin(plugin_name)

    def enable_plugin(self, plugin_name):
        self.enable_plugin(plugin_name)

    def disable_plugin(self, plugin_name):
        self.disable_plugin(plugin_name)


if __name__ == "__main__":
    wayctl = Wayctl()
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
    if wayctl.args.plugin is not None:
        if "reload" in wayctl.args.plugin:
            if wayctl.args.plugin[1] != "all":
                wayctl._reload_plugin(wayctl.args.plugin[1])
        if "enable" in wayctl.args.plugin:
            wayctl.activate_plugin(wayctl.args.plugin[1])
        if "disable" in wayctl.args.plugin:
            wayctl.disactivate_plugin(wayctl.args.plugin[1])
        if "list" in wayctl.args.plugin:
            wayctl.list_plugins()
        if "status" in wayctl.args.plugin:
            plugin = wayctl.args.plugin[1]
            wayctl.is_plugin_enabled(plugin)
