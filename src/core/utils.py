import os
import toml
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk
from gi.repository import Gtk
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen
import math
import pulsectl
import psutil
import waypy


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
        self.icon_theme_list = Gtk.IconTheme().get_icon_names()
        self.icon_names = [
            i.get_id().split(".")[0].lower() for i in Gio.AppInfo.get_all()
        ]
        self.focused_view_id = None
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_path)
            os.makedirs(self.scripts)

    def run_app(self, cmd, wclass=None, initial_title=None, cmd_mode=True):
        if isinstance(cmd, type(self.set_view_focus)):
            self.set_view_focus(self.active_view_id)
            return True

        if "kitty --hold" in cmd and cmd_mode:
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

    def CreateFromAppList(
        self, config, orientation, class_style, callback=None, use_label=False
    ):
        # Map orientation to Gtk.Orientation
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        if orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        # Create a Gtk.Box with specified spacing and orientation
        box = Gtk.Box(spacing=10, orientation=orientation)
        box.add_css_class("box_from_dockbar")  # Add a CSS class to the box for styling

        # Load configuration from a file using the toml library
        with open(config, "r") as f:
            config = toml.load(f)

            # Iterate through each application in the configuration
            for app in config:
                wclass = None
                initial_title = None

                try:
                    # Try to get the 'wclass' field from the configuration, if present
                    wclass = config[app]["wclass"]
                except KeyError:
                    pass

                # Create a button using the CreateButton method
                button = self.CreateButton(
                    config[app]["icon"],
                    config[app]["cmd"],
                    class_style,
                    wclass,
                    initial_title,
                    use_label,
                )

                # If a callback is provided, create a gesture for the button
                if callback is not None:
                    self.CreateGesture(button, 3, callback)

                # Append the button to the Gtk.Box
                box.append(button)

        # Return the created Gtk.Box
        return box

    def search_local_desktop(self, initial_title):
        for deskfile in os.listdir(self.webapps_applications):
            if (
                deskfile.startswith("chrome")
                or deskfile.startswith("msedge")
                or deskfile.startswith("FFPWA-")
            ):
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

    def wayfire_info(self, method):
        addr = os.getenv("WAYFIRE_SOCKET")
        sock = ws.WayfireSocket(addr)
        query = ws.get_msg_template(method)
        return sock.send_json(query)

    def focused_window_info(self):
        return self.wayfire_info("window-rules/get-focused-view")["info"]

    def list_views(self):
        return self.wayfire_info("window-rules/list-views")

    def update_icon(self, wm_class, initial_title, title):
        # Set window icon based on icon_exist
        if " " in initial_title:
            initial_title = initial_title.replace(" ", "")
        icon_exist = self.icon_exist(wm_class)
        if wm_class in icon_exist:
            return wm_class
        if wm_class not in icon_exist:
            # If no icon for wm_class, check if there's an icon for the initial_title
            icon_exist = self.icon_exist(initial_title)
            if initial_title in icon_exist:
                return initial_title
        # If still no icon, search for desktop files based on wmclass and initial_title
        desk = self.search_desktop(wm_class)
        desk_local = self.search_local_desktop(initial_title)
        if wm_class not in icon_exist and initial_title not in icon_exist:
            if desk_local and "-Default" in desk_local:
                icon = desk_local.split(".desktop")[0]
                return icon
            if desk_local is None:
                if desk:
                    icon = desk.split(".desktop")[0]
                    return icon
        return None

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
        if argument is not None:
            exist = [name for name in self.icon_names if argument.lower() in name]
            return exist

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
        if ".desktop" in wmclass:
            wmclass = wmclass.split(".desktop")[0]
            if "org." in wmclass:
                wmclass = wmclass.split("org.")[-1]

        # Map orientation to Gtk.Orientation
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        # Check if a window with the given address is already open

        icon = self.update_icon(wmclass, initial_title, title)

        # Special case for "zsh" initial_title
        if initial_title == "zsh":
            label = title.split(" ")[0]
        if initial_title == "fish":
            label = title.split(" ")[0]
            icon_exist = [i for i in self.icon_theme_list if label in i]
            try:
                icon = icon_exist[-1]
            except IndexError:
                pass

        # button title will appear captalized
        initial_title = " ".join(i.capitalize() for i in initial_title.split())

        # Load panel config and check if there is a custom icon set
        with open(self.topbar_config, "r") as f:
            config = toml.load(f)
        try:
            # Try to get icon information from the configuration file
            icon = config["change_icon_title"][wmclass]
        except KeyError:
            pass

        # Load dockbar configuration and set the icon from default if exist
        with open(self.dockbar_config, "r") as f:
            config = toml.load(f)
        try:
            # Try to get icon information from the configuration file
            icon = config[wmclass.lower()]["icon"]
        except KeyError:
            pass

        # Set additional label-based icons for specific initial_titles (zsh, fish)
        label = title.split(" ")[0] if initial_title in ["zsh", "fish"] else None

        if label:
            icon_exist = self.icon_exist(label)
            if icon_exist:
                self.window_title.set_icon_name(icon_exist[0])
                self.tbclass.set_icon_name(label)

        # Create a clickable image button and attach a gesture if callback is provided
        button = self.create_clicable_image(
            icon, class_style, wmclass, title, initial_title, view_id
        )
        # if callback is not None:
        #    self.CreateGesture(button, 3, callback)

        return button

    def search_str_inside_file(self, file_path, word):
        with open(file_path, "r") as file:
            content = file.read()
            if word.lower() in content.lower():
                return True
            else:
                return False

    def create_clicable_image(
        self, icon, Class_Style, wclass, title, initial_title, pid=None
    ):
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class(Class_Style)
        image = None
        if icon is None:
            icon = ""
        # panel.toml has filters for missing icons
        try:
            icon = self.panel_cfg["change_icon_title"][icon]
        except Exception as e:
            print(e)
        if isinstance(icon, str):
            image = Gtk.Image.new_from_icon_name(icon)
        else:
            image = Gtk.Image.new_from_gicon(icon)
        image.add_css_class("icon_from_popover_launcher")
        image.set_icon_size(Gtk.IconSize.LARGE)
        image.props.margin_end = 5
        image.set_halign(Gtk.Align.END)
        label = Gtk.Label.new()
        # zsh use titles instead of initial title
        use_this_title = initial_title
        if "zsh" == initial_title.lower():
            use_this_title = title
        if "fish" == initial_title.lower():
            use_this_title = title

        desktop_local_file = self.search_local_desktop(initial_title)
        if desktop_local_file:
            icon = desktop_local_file.split(".desktop")[0]

        label.set_label(use_this_title)
        label.add_css_class("clicable_image_label")
        box.append(image)
        box.append(label)
        box.add_css_class("box_from_clicable_image")
        self.CreateGesture(box, 1, lambda *_: self.set_view_focus(pid))
        return box

    def compositor(self):
        addr = os.getenv("WAYFIRE_SOCKET")
        return waypy.WayfireSocket(addr)

    def set_view_focus(self, pid):
        sock = self.compositor()
        sock.set_focus(pid)
        # sock.scale_toggle()

    def CreateButton(
        self, icon_name, cmd, Class_Style, wclass, initial_title=None, use_label=False
    ):
        box = Gtk.Box(spacing=6)
        box.add_css_class(Class_Style)
        button = Adw.ButtonContent()
        if use_label:
            button.set_label(icon_name)
        else:
            button.add_css_class("hvr-grow")
            button.set_icon_name(icon_name)

        button.add_css_class("{}-buttons".format(Class_Style))
        if cmd == "NULL":
            button.set_sensitive(False)
            return button
        self.CreateGesture(
            button, 1, lambda *_: self.run_app(cmd, wclass, initial_title)
        )
        self.CreateGesture(button, 3, lambda *_: self.dockbar_remove(icon_name))
        return button

    def load_topbar_config(self):
        with open(self.topbar_config, "r") as f:
            return toml.load(f)

    def CreateGesture(self, widget, mouse_button, callback):
        gesture = Gtk.GestureClick.new()
        gesture.connect("released", callback)
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)

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
        tbtn_title_b.add_css_class(class_style)
        return tbtn_title_b
