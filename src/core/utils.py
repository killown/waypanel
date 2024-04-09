import os
import math
import gi
from src.core.background import *
import numpy as np
from time import sleep

gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk4LayerShell as LayerShell
from gi.repository import Gtk, Adw, Gio, GObject
from subprocess import Popen
from wayfire.ipc import sock
import wayfire.ipc as wayfire
import toml

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gtk4LayerShell", "1.0")


class Utils(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.home = os.path.expanduser("~")
        self.webapps_applications = os.path.join(self.home, ".local/share/applications")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.psutil_store = {}
        self.panel_cfg = self.load_topbar_config()
        self.icon_names = [icon for icon in Gtk.IconTheme().get_icon_names()]
        self.gio_icon_list = Gio.AppInfo.get_all()
        self.gestures = {}

        self.focused_view_id = None
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_path)

        self.is_scale_active = {}
        self.start_thread_compositor()

    def run_app(self, cmd, wclass=None, initial_title=None, cmd_mode=True):
        if "kitty" in cmd and cmd_mode:
            try:
                Popen(cmd.split(), start_new_session=True)
            except Exception as e:
                print(e)
            return
        if ";" in cmd:
            for c in cmd.split(";"):
                try:
                    Popen(c.split(), start_new_session=True)
                except Exception as e:
                    print(e)
        else:
            try:
                Popen(cmd.split(), start_new_session=True)
            except Exception as e:
                print(e)

    def widget_exists(self, widget):
        return widget is not None and isinstance(widget, Gtk.Widget)

    def CreateWorkspacePanel(
        self, config, orientation, class_style, callback=None, use_label=False
    ):
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        if orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        box = Gtk.Box(spacing=10, orientation=orientation)
        box.add_css_class("box_from_dockbar")

        with open(config, "r") as f:
            config_data = toml.load(f)

            for app in config_data:
                wclass = None
                initial_title = None

                try:
                    wclass = config_data[app]["wclass"]
                except KeyError:
                    pass

                button = self.CreateButton(
                    config_data[app]["icon"],
                    config_data[app]["cmd"],
                    class_style,
                    wclass,
                    initial_title,
                    use_label,
                )

                if callback is not None:
                    self.create_gesture(button, 3, callback)

                box.append(button)

        return box

    def CreateFromAppList(
        self, config, orientation, class_style, callback=None, use_label=False
    ):
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        if orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        box = Gtk.Box(spacing=10, orientation=orientation)
        box.add_css_class("box_from_dockbar")

        with open(config, "r") as f:
            config_data = toml.load(f)

            for app in config_data:
                wclass = None
                initial_title = None

                try:
                    wclass = config_data[app]["wclass"]
                except KeyError:
                    pass

                button = self.CreateButton(
                    config_data[app]["icon"],
                    config_data[app]["cmd"],
                    class_style,
                    wclass,
                    initial_title,
                    use_label,
                )

                if callback is not None:
                    self.create_gesture(button, 3, callback)

                box.append(button)

        return box

    def on_compositor_finished(self):
        try:
            self.watch_task.finish()
        except Exception as err:
            print(err)

    def start_thread_compositor(self):
        self.watch_task = Background(self.watch_events, self.on_compositor_finished)
        self.watch_task.start()

    def compositor_window_changed(self):
        pass

    def watch_events(self):
        sock = self.compositor()
        sock.watch()
        while True:
            try:
                msg = sock.read_message()
                if "event" in msg:
                    if msg["event"] == "plugin-activation-state-changed":
                        if msg["state"] is True:
                            if msg["plugin"] == "scale":
                                self.is_scale_active[msg["output"]] = True
                        if msg["state"] is False:
                            if msg["plugin"] == "scale":
                                self.is_scale_active[msg["output"]] = False
            except Exception as e:
                print(e)

    def search_local_desktop(self, initial_title):
        for deskfile in os.listdir(self.webapps_applications):
            if deskfile.startswith(("chrome", "msedge", "FFPWA-")):
                pass
            else:
                continue
            webapp_path = os.path.join(self.webapps_applications, deskfile)
            desktop_file_found = self.search_str_inside_file(
                webapp_path, initial_title.lower()
            )
            if desktop_file_found:
                return deskfile
        return None

    def extract_icon_info(self, application_name):
        icon_name = None

        # Paths to search for desktop files
        search_paths = [
            "/usr/share/applications/",
            os.path.expanduser("~/.local/share/applications/"),
        ]

        # Loop through each search path
        for search_path in search_paths:
            # Check if the search path exists
            if os.path.exists(search_path):
                # Loop through each file in the directory
                for file_name in os.listdir(search_path):
                    if file_name.endswith(".desktop"):
                        file_path = os.path.join(search_path, file_name)
                        with open(file_path, "r") as desktop_file:
                            found_name = False
                            for line in desktop_file:
                                if line.startswith("Name="):
                                    if line.strip().split("=")[1] == application_name:
                                        found_name = True
                                elif found_name and line.startswith("Icon="):
                                    icon_name = line.strip().split("=")[1]
                                    return icon_name

        return icon_name

    def search_desktop(self, wm_class):
        all_apps = Gio.AppInfo.get_all()
        desktop_files = [
            i.get_id().lower() for i in all_apps if wm_class in i.get_id().lower()
        ]
        if desktop_files:
            return desktop_files[0]
        else:
            return None

    def icon_exist(self, argument):
        argument = argument.lower()

        if argument:
            exist = [
                i.get_icon()
                for i in self.gio_icon_list
                if argument in i.get_id().lower()
            ]
            if exist:
                if hasattr(exist[0], "get_names"):
                    return exist[0].get_names()[0]
                if hasattr(exist[0], "get_icon"):
                    return exist[0].get_icon()
                if hasattr(exist[0], "get_name"):
                    return exist[0].get_name()
                if hasattr(exist[0], "get_id"):
                    return self.extract_icon_info(exist[0].get_id())
                else:
                    # If not, assume it's a string
                    return exist[0]
            else:
                exist = [name for name in self.icon_names if argument.lower() in name]
                if exist:
                    exist = exist[0].lower()
                    return exist
        return ""

    def create_taskbar_launcher(
        self,
        wmclass,
        title,
        initial_title,
        orientation,
        class_style,
        view_id,
        callback=None,
    ):
        title = self.filter_utf8_for_gtk(title)
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        icon = self.get_icon(wmclass, initial_title, title)

        button = self.create_clickable_image(
            icon, class_style, wmclass, title, initial_title, view_id
        )
        return button

    def search_str_inside_file(self, file_path, word):
        with open(file_path, "r") as file:
            content = file.read()
            if word.lower() in content.lower():
                return True
            else:
                return False

    def get_icon(self, wm_class, initial_title, title):
        title = self.filter_utf8_for_gtk(title)
        if "kitty" in wm_class and "kitty" not in title.lower():
            title_icon = self.icon_exist(initial_title)
            if title_icon:
                return title_icon

        web_apps = {"microsoft-edge", "chromium"}
        if any(app in wm_class for app in web_apps):
            desk_local = self.search_local_desktop(initial_title)

            if desk_local and "-Default" in desk_local:
                return desk_local.split(".desktop")[0]

        found_icon = self.icon_exist(wm_class)
        if found_icon:
            return found_icon

        app_id = sock.get_focused_view_app_id()
        found_icon = self.icon_exist(app_id)
        if found_icon:
            return found_icon

        return ""

    # FIXME: panel will crash if started app has some random errors in output
    # that means, the panels bellow will be always on top and no clickable anymore
    # example of apps with errors, nautilus, element, chromium etc.
    def create_clickable_image(
        self, icon_name, class_style, wclass, title, initial_title, view_id
    ):

        # this is creating empty box in case you can't find any app-id
        if wclass == "nil":
            return Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=6)

        # no pid no new taskbar button, that will crash the panel
        self.compositor()
        pid = sock.get_view_pid(view_id)
        if pid == -1:
            return

        title = self.filter_utf8_for_gtk(title)
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class(class_style)

        use_this_title = title[:40]

        label = Gtk.Label.new(use_this_title)
        label.add_css_class("label_from_clickable_image")

        print(icon_name)
        if isinstance(icon_name, Gio.FileIcon):
            # If icon_name is a FileIcon object, directly use it
            image = Gtk.Image.new_from_gicon(icon_name)
        else:
            # Otherwise, treat icon_name as a string representing the icon name
            image = Gtk.Image.new_from_icon_name(icon_name)

        image.props.margin_end = 5
        image.set_halign(Gtk.Align.END)
        image.add_css_class("icon_from_clickable_image")

        box.append(image)
        box.append(label)
        box.add_css_class("box_from_clickable_image")

        self.create_gesture(box, 1, lambda *_: self.set_view_focus(view_id))
        self.create_gesture(box, 3, lambda *_: self.close_view(view_id))

        return box

    def compositor(self):
        addr = os.getenv("WAYFIRE_SOCKET")
        return wayfire.WayfireSocket(addr)

    def close_view(self, view_id):
        sock.close_view(view_id)

    def view_focus_indicator_effect(self, view_id):
        sock = self.compositor()
        precision = 1
        values = np.arange(0.1, 1, 0.1)
        float_sequence = [round(value, precision) for value in values]
        original_alpha = sock.get_view_alpha(view_id)["alpha"]
        for f in float_sequence:
            try:
                sock.set_view_alpha(view_id, f)
                sleep(0.04)
            except Exception as e:
                print(e)
        sock.set_view_alpha(view_id, original_alpha)

    def set_view_focus(self, view_id):
        try:
            view = sock.get_view(view_id)
            if view is None:
                return

            print(view)
            # why foucs an app with no app-id
            if view["app-id"] == "nil":
                return

            view_id = view["id"]
            output_id = view["output-id"]

            if output_id in self.is_scale_active:
                # there is an issue depending on the scale animation duration
                # the panel will freeze while the layzer shell will keep on top of the views because it enter in a infinite recursion
                # the conflict happens with go_workspace_set_focus while the animation of scale is still happening
                # another issue with scale is, if you enable close on new views option it will close faster than you set layer on bottom
                # thus will produce the same kind of issue
                if self.is_scale_active[output_id] is True:
                    sock.scale_toggle()
                    # FIXME: better get animation speed from the conf so define a proper sleep
                    sleep(0.2)
                    sock.go_workspace_set_focus(view_id)
                    sock.move_cursor_middle(view_id)
                else:
                    sock.go_workspace_set_focus(view_id)
                    sock.move_cursor_middle(view_id)
            else:
                sock.go_workspace_set_focus(view_id)
                sock.move_cursor_middle(view_id)
                self.view_focus_indicator_effect(view_id)

        except Exception as e:
            print(e)
            return True

    def filter_utf8_for_gtk(self, byte_string, encoding="utf-8"):
        if isinstance(byte_string, str):
            return byte_string  # For Python 3, assume the string is already decoded
        try:
            decoded_text = byte_string.decode(encoding)
        except AttributeError:
            decoded_text = byte_string.decode(encoding, errors="ignore")
        return decoded_text

    def CreateButton(
        self,
        icon_name,
        cmd,
        Class_Style,
        wclass,
        initial_title=None,
        use_label=False,
        use_function=False,
    ):
        box = Gtk.Box(spacing=2)
        box.add_css_class(Class_Style)
        button = Adw.ButtonContent()
        if use_label:
            button.set_label(icon_name)
        else:
            button.add_css_class("hvr-grow")
            button.set_icon_name(icon_name)

        button.add_css_class("{}-button".format(Class_Style))
        if cmd == "NULL":
            button.set_sensitive(False)
            return button
        if use_function is False:
            self.create_gesture(button, 1, lambda *_: sock.run(cmd))
            self.create_gesture(button, 3, lambda *_: self.dockbar_remove(icon_name))
        else:
            self.create_gesture(button, 1, use_function)

        return button

    def load_topbar_config(self):
        with open(self.topbar_config, "r") as f:
            return toml.load(f)

    def create_gesture(self, widget, mouse_button, callback, arg=None):
        gesture = Gtk.GestureClick.new()
        if arg is None:
            gesture.connect("released", callback)
        else:
            gesture.connect("released", lambda gesture, arg=arg: callback(arg))
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        self.gestures[widget] = gesture
        return widget

    def remove_gesture(self, widget):
        if widget in self.gestures:
            gesture = self.gestures[widget]
            widget.remove_controller(gesture)
            del self.gestures[widget]

    def convert_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return "%s %s" % (s, size_name[i])

    def btn_background(self, class_style, icon_name):
        tbtn_title_b = Adw.ButtonContent()
        tbtn_title_b.set_icon_name(icon_name)
        return tbtn_title_b
