import os
import random
import gi
from gi.repository import Gio, Gtk, Adw, Gdk
import cairo
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen
from ..core.utils import Utils
import toml


class MenuLauncher(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_launcher = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()
        self.recent_apps_file = os.path.expanduser("~/config/waypanel/recent-apps.lst")
        self.utils = Utils(application_id="com.github.utils")

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.scripts = os.path.join(self.home, ".config/hypr/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.topbar_launcher_config = os.path.join(
            self.config_path, "topbar-launcher.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}

    def create_menu_popover_launcher(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        self.menubutton_launcher = Gtk.Button()
        self.menubutton_launcher.connect("clicked", self.open_popover_launcher)
        self.menubutton_launcher.set_icon_name("start-here-archlinux")
        self.menubutton_launcher.add_css_class("top_left_widgets")
        obj.top_panel_box_widgets_left.append(self.menubutton_launcher)

    def create_popover_launcher(self, *_):
        # Create a popover
        self.popover_launcher = Gtk.Popover()
        self.popover_launcher.set_has_arrow(False)
        self.popover_launcher.add_css_class("transparent-popover-launcher")
        self.popover_launcher.connect("closed", self.popover_is_closed)
        self.popover_launcher.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.app.add_action(show_searchbar_action)
        # Set up scrolled window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        # self.searchbar.props.hexpand = False
        # self.searchbar.props.vexpand = True

        self.main_box.append(self.searchbar)
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(4)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.run_app_from_launcher)
        self.flowbox.add_css_class("popover_launcher_flowbox")
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.flowbox)
        self.popover_launcher.set_child(self.main_box)
        all_apps = Gio.AppInfo.get_all()
        random.shuffle(all_apps)
        with open(self.dockbar_config, "r") as f:
            dockbar_toml = toml.load(f)

        dockbar_apps = [dockbar_toml[i] for i in dockbar_toml]
        dockbar_names = [dockbar_toml[i]["name"] for i in dockbar_toml]
        dockbar_desktop = [dockbar_toml[i]["desktop_file"] for i in dockbar_toml]
        all_apps = [i for i in all_apps if i.get_id() not in dockbar_desktop]

        # recent apps have a list of last apps started from the launcher
        recent_apps = self.get_recent_apps()
        for i in all_apps:
            name = i.get_name()
            if name not in recent_apps:
                continue
            keywords = " ".join(i.get_keywords())
            if not name:
                name = i.get_name()

            if name.count(" ") > 2:
                name = " ".join(name.split()[:3])
            icon = i.get_icon()
            cmd = i.get_id()
            if icon is None:
                continue
            self.row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            self.row_hbox.MYTEXT = name, cmd, keywords
            line = Gtk.Label.new()
            line.add_css_class("label_from_popover_launcher")
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            image = Gtk.Image.new_from_gicon(icon)
            image.add_css_class("icon_from_popover_launcher")
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            self.row_hbox.append(image)
            self.row_hbox.append(line)
            self.flowbox.append(self.row_hbox)

        for i in all_apps:
            name = i.get_name()
            if name in recent_apps:
                continue
            keywords = " ".join(i.get_keywords())

            if name.count(" ") > 2:
                name = " ".join(name.split()[:3])
            icon = i.get_icon()
            cmd = i.get_id()
            if icon is None:
                continue
            self.row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            self.row_hbox.MYTEXT = name, cmd, keywords
            line = Gtk.Label.new()
            line.add_css_class("label_from_popover_launcher")
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            image = Gtk.Image.new_from_gicon(icon)
            image.add_css_class("icon_from_popover_launcher")
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            self.row_hbox.append(image)
            self.row_hbox.append(line)
            self.flowbox.append(self.row_hbox)
        self.flowbox.set_filter_func(self.on_filter_invalidate)
        # Connect signal for selecting a row
        width = self.flowbox.get_preferred_size().natural_size.width
        self.scrolled_window.set_min_content_width(width * 4)
        self.scrolled_window.set_min_content_height(600)
        self.popover_launcher.set_parent(self.menubutton_launcher)
        self.popover_launcher.popup()
        return self.popover_launcher

    def add_recent_app(self, app_name):
        os.makedirs(os.path.dirname(self.recent_apps_file), exist_ok=True)

        if os.path.exists(self.recent_apps_file):
            recent_apps = self.get_recent_apps()
        else:
            recent_apps = []

        if app_name not in recent_apps:
            recent_apps.append(app_name)
            recent_apps = recent_apps[-40:]

            with open(self.recent_apps_file, "w") as f:
                f.write("\n".join(recent_apps))

    def get_recent_apps(self):
        if os.path.exists(self.recent_apps_file):
            with open(self.recent_apps_file, "r") as f:
                recent_apps = f.read().splitlines()
            return recent_apps
        else:
            return []

    def run_app_from_launcher(self, x, y):
        mytext = [i.get_child().MYTEXT for i in x.get_selected_children()][0]
        name, desktop, keywords = mytext
        cmd = "gtk-launch {}".format(desktop).split()
        self.add_recent_app(name)
        Popen(cmd)
        self.popover_launcher.popdown()

    def open_popover_launcher(self, *_):
        if self.popover_launcher and self.popover_launcher.is_visible():
            self.popover_launcher.popdown()
        if self.popover_launcher and not self.popover_launcher.is_visible():
            self.popover_launcher.popup()
        if not self.popover_launcher:
            self.popover_launcher = self.create_popover_launcher(self.app)

    def popover_is_open(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        return

    def popover_is_closed(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.NONE)
        # print(LayerShell.get_keyboard_mode(self.top_panel).value_name)

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()
        print("search entry is focused: {}".format(self.searchentry.is_focus()))

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        # run filter (run self.on_filter_invalidate look at self.listbox.set_filter_func(self.on_filter_invalidate) )
        self.flowbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        text_to_search = self.searchbar.get_text().strip()
        if not isinstance(row, str):
            row = row.get_child().MYTEXT
            # using get_name + get_keywords from Gio.AppInfo.get_all()
            row = "{0} {1} {2}".format(row[0], row[1], row[2])

        row = row.lower().strip()
        if text_to_search.lower() in row:
            return True
        return False
