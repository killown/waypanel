import os
import toml
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GObject
from gi.repository import Gtk

gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen
import math
import pulsectl
import psutil
from wayfire import sock
import wayfire
from time import sleep


class InvalidGioTaskError(Exception):
    pass


class AlreadyRunningError(Exception):
    pass


class BackgroundUtils(GObject.Object):
    __gtype_name__ = "BackgroundUtils"

    def __init__(self, function, finish_callback, **kwargs):
        super().__init__(**kwargs)

        self.function = function
        self.finish_callback = finish_callback
        self._current = None

    def start(self):
        if self._current:
            AlreadyRunningError("Task is already running")

        finish_callback = lambda self, task, nothing: self.finish_callback()

        task = Gio.Task.new(self, None, finish_callback, None)
        task.run_in_thread(self._thread_cb)

        self._current = task

    @staticmethod
    def _thread_cb(task, self, task_data, cancellable):
        try:
            retval = self.function()
            task.return_value(retval)
        except Exception as e:
            task.return_value(e)

    def finish(self):
        task = self._current
        self._current = None

        if not Gio.Task.is_valid(task, self):
            raise InvalidGioTaskError()

        value = task.propagate_value().value

        if isinstance(value, Exception):
            raise value

        return value


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
        self.icon_names = [icon for icon in Gtk.IconTheme().get_icon_names()]
        self.gio_icon_list = Gio.AppInfo.get_all()

        self.focused_view_id = None
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_path)
            os.makedirs(self.scripts)

        self.is_scale_active = {}
        self.start_thread_compositor()

    def run_app(self, cmd, wclass=None, initial_title=None, cmd_mode=True):
        if "alacritty" in cmd and cmd_mode:
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
                    self.create_gesture(button, 3, callback)

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
                    self.create_gesture(button, 3, callback)

                # Append the button to the Gtk.Box
                box.append(button)

        # Return the created Gtk.Box
        return box

    def on_compositor_finished(self):
        # non working code
        try:
            self.taskbarwatch_task.finish()
        except Exception as err:
            print(err)

    def start_thread_compositor(self):
        self.watch_task = BackgroundUtils(
            self.watch_events, lambda: self.on_compositor_finished
        )
        self.watch_task.start()

    def compositor_window_changed(self):
        # if no windows, window_created signal will conflict with window_changed
        # the issue will be no new button will be appended to the taskbar
        # necessary to check if the window list is empity
        # if not len(self.hyprinstance.get_windows()) == 0:
        # self.update_active_window_shell()
        print()

    def watch_events(self):
        sock = self.compositor()
        sock.watch()
        while True:
            try:
                msg = sock.read_message()
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
        if argument:
            # try to methods, with gtk and gio
            exist = None
            exist = [
                i.get_icon()
                for i in self.gio_icon_list
                if argument == i.get_startup_wm_class()
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
        found_icon = self.icon_exist(wm_class)
        if found_icon:
            return found_icon

        app_id = sock.get_focused_view().get("app-id", "")
        found_icon = self.icon_exist(app_id)
        if found_icon:
            return found_icon

        web_apps = {"microsoft-edge", "chromium"}
        if any(app in wm_class for app in web_apps):
            desk_local = self.search_local_desktop(initial_title)
            desk = self.search_desktop(wm_class)

            if desk_local and "-Default" in desk_local:
                return desk_local.split(".desktop")[0]
            elif desk:
                return desk.split(".desktop")[0]

        if "alacritty" in wm_class and "alacritty" not in title.lower():
            title_icon = self.icon_exist(initial_title)
            if title_icon:
                return title_icon

        return ""

    def create_clickable_image(
        self, icon_name, class_style, wclass, title, initial_title, view_id
    ):
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class(class_style)

        use_this_title = title[:40]  # Limit to 40 characters

        if "alacritty" not in wclass.lower():
            self.gio_icon_list = Gio.AppInfo.get_all()
            exist = (
                i.get_display_name()
                for i in self.gio_icon_list
                if wclass == i.get_startup_wm_class()
            )
            use_this_title = next(iter(exist), use_this_title)

        label = Gtk.Label.new(use_this_title)
        label.add_css_class("label_from_clickable_image")

        image = Gtk.Image.new_from_icon_name(icon_name)
        image.set_icon_size(Gtk.IconSize.LARGE)
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

    def set_view_focus(self, view_id):
        list_views = sock.list_views()
        matching_views = [view for view in list_views if view_id == view["id"]]

        if not matching_views:
            return None

        view_id = matching_views[0]["id"]
        output_id = matching_views[0]["output-id"]
        focused_output_views = sock.focused_output_views()
        is_view_from_focused_output = None
        if focused_output_views:
            is_view_from_focused_output = any(
                view for view in focused_output_views if view_id == view["id"]
            )

        if output_id in self.is_scale_active:
            if self.is_scale_active[output_id] is True:
                sock.scale_toggle()
                sock.set_focus(view_id)
            else:
                sock.set_focus(view_id)

        alpha = sock.get_view_alpha(view_id)["alpha"]
        config_path = os.path.join(self.home, ".config/waypanel/")
        shader = os.path.join(config_path, "shaders/view-effect.shader")
        revert_effect = os.path.join(config_path, "shaders/revert.shader")

        if os.path.exists(shader) and not is_view_from_focused_output:
            sock.set_view_shader(view_id, shader)
            sleep(0.2)
            sock.set_view_shader(view_id, revert_effect)
        elif not is_view_from_focused_output:
            sock.set_view_alpha(view_id, alpha / 2)
            sleep(0.2)
            sock.set_view_alpha(view_id, alpha)

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
            self.create_gesture(
                button, 1, lambda *_: self.run_app(cmd, wclass, initial_title)
            )
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
            gesture.connect("released", lambda arg: callback(arg))
        gesture.set_button(mouse_button)
        widget.add_controller(gesture)
        return widget

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
