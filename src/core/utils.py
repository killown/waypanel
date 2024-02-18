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
import wayfire


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
        # split the org.gnome dots from the list
        self.icon_names = [
            icon.split(".")[-1].lower() for icon in Gtk.IconTheme().get_icon_names()
        ]
        self.gio_icon_list = Gio.AppInfo.get_all()

        self.focused_view_id = None
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_path)
            os.makedirs(self.scripts)

    def run_app(self, cmd, wclass=None, initial_title=None, cmd_mode=True):
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

    def CreateWorkspacePanel(
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
        if "." in argument:
            argument = argument.split(".")[-1]

        # we split title and consider initial_title in certain cases
        # there is some titles that starts with "app: some title"
        # so if we simply title.split()[0] won't catch this case
        if ":" in argument:
            argument = argument.split(":")[0]

        if argument:
            # try to methods, with gtk and gio
            exist = None
            exist = [
                i.get_icon()
                for i in self.gio_icon_list
                if argument.lower() == i.get_startup_wm_class()
            ]

            if exist:
                # found icons, so extract from the list
                exist = exist[0].get_names()[0]
                return exist
            else:
                exist = [name for name in self.icon_names if argument.lower() in name]
                if exist:
                    exist = exist[0]
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
        # Map orientation to Gtk.Orientation
        if orientation == "h":
            orientation = Gtk.Orientation.HORIZONTAL
        elif orientation == "v":
            orientation = Gtk.Orientation.VERTICAL

        icon = self.get_icon(wmclass, initial_title, title)

        # Create a clickable image button and attach a gesture if callback is provided
        button = self.create_clicable_image(
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
        icon = self.icon_exist(wm_class)
        if icon == "":
            app_id = self.compositor().get_focused_view()["app-id"]
            icon = self.icon_exist(app_id)

        desk_local = self.search_local_desktop(initial_title)
        desk = self.search_desktop(wm_class)

        if "kitty" in wm_class.lower() and "kitty" not in title.lower():
            icon_exist = self.icon_exist(initial_title)
            if icon_exist:
                return icon_exist

        if desk_local and "-Default" in desk_local and icon == "":
            icon = desk_local.split(".desktop")[0]
            return icon
        if desk_local is None and icon == "":
            if desk:
                icon = desk.split(".desktop")[0]
                return icon
        if icon:
            return icon

        return ""

    def create_clicable_image(
        self, icon, Class_Style, wclass, title, initial_title, view_id
    ):
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class(Class_Style)
        image = None
        label = Gtk.Label.new()
        # zsh use titles instead of initial title
        use_this_title = initial_title
        if "kitty" in wclass.lower():
            use_this_title = title

        label.set_label(use_this_title)
        label.add_css_class("clicable_image_label")

        image = Gtk.Image.new_from_icon_name(icon)
        image.set_icon_size(Gtk.IconSize.LARGE)
        image.props.margin_end = 5
        image.set_halign(Gtk.Align.END)
        image.add_css_class("icon_from_clicable_image")

        box.append(image)
        box.append(label)
        # if you put the add_css_class above, wont work
        box.add_css_class("box_from_clicable_image")
        self.CreateGesture(box, 1, lambda *_: self.set_view_focus(view_id))
        return box

    def compositor(self):
        addr = os.getenv("WAYFIRE_SOCKET")
        return wayfire.WayfireSocket(addr)

    def set_view_focus(self, view_id):
        sock = self.compositor()
        sock.scale_leave()
        sock.set_focus(view_id)

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
        if use_function is False:
            self.CreateGesture(
                button, 1, lambda *_: self.run_app(cmd, wclass, initial_title)
            )
            self.CreateGesture(button, 3, lambda *_: self.dockbar_remove(icon_name))
        else:
            self.CreateGesture(button, 1, use_function)

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
