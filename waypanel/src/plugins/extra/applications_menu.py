import os
import random
from subprocess import Popen

import toml
from gi.repository import Adw, Gio, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

from ...core.utils import Utils

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def position():
    position = "left"
    order = 1
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        menu = MenuLauncher(panel_instance)
        menu.create_menu_popover_launcher()
        return menu


class MenuLauncher(Adw.Application):
    def __init__(self, panel_instance):
        self.popover_launcher = None
        self.obj = panel_instance
        self.widgets_dict = {}
        self.all_apps = None
        self.menubutton_launcher = Gtk.Button()
        self.top_panel = None
        self.search_get_child = None
        self.search_row = []
        self._setup_config_paths()
        self.recent_apps_file = os.path.expanduser("~/config/waypanel/recent-apps.lst")
        self.utils = Utils(application_id="com.github.utils")

    def append_widget(self):
        return self.menubutton_launcher

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.scripts = os.path.join(self.home, ".config/hypr/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.waypanel_cfg = os.path.join(self.config_path, "waypanel.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}

    def create_menu_popover_launcher(self):
        self.menubutton_launcher.connect("clicked", self.open_popover_launcher)
        panel_config_path = os.path.join(self.config_path, "panel.toml")
        menu_icon = self.utils.get_nearest_icon_name("archlinux")
        if os.path.exists(panel_config_path):
            with open(panel_config_path, "r") as f:
                panel_config = toml.load(f)
            menu_icon = self.utils.get_nearest_icon_name(
                panel_config.get("top", {}).get(
                    "menu_icon", self.utils.get_nearest_icon_name("wayfire")
                )
            )

        self.menubutton_launcher.set_icon_name(menu_icon)
        self.menubutton_launcher.add_css_class("top_left_widgets")

    def create_popover_launcher(self, *_):
        # Create a popover
        self.popover_launcher = Gtk.Popover()
        self.popover_launcher.set_has_arrow(False)
        self.popover_launcher.connect("closed", self.popover_is_closed)
        self.popover_launcher.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)
        # Set up scrolled window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)

        # press enter
        self.searchbar.connect("activate", self.on_keypress)

        self.searchbar.set_focus_on_click(True)
        # self.searchbar.props.hexpand = False
        # self.searchbar.props.vexpand = True

        self.main_box.append(self.searchbar)
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(1)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.run_app_from_launcher)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.flowbox)
        self.popover_launcher.set_child(self.main_box)
        all_apps = Gio.AppInfo.get_all()
        random.shuffle(all_apps)
        with open(self.waypanel_cfg, "r") as f:
            dockbar_toml = toml.load(f)["dockbar"]

        dockbar_apps = [dockbar_toml[i] for i in dockbar_toml]
        dockbar_names = [dockbar_toml[i]["name"] for i in dockbar_toml]
        dockbar_desktop = [dockbar_toml[i]["desktop_file"] for i in dockbar_toml]
        self.all_apps = [i for i in all_apps if i.get_id() not in dockbar_desktop]

        # recent apps have a list of last apps started from the launcher
        recent_apps = self.get_recent_apps()
        for i in self.all_apps:
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
            self.widgets_dict[i.get_id()] = self.row_hbox
            self.row_hbox.MYTEXT = name, cmd, keywords
            line = Gtk.Label.new()
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            image = Gtk.Image.new_from_gicon(icon)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            self.row_hbox.append(image)
            self.row_hbox.append(line)
            self.flowbox.append(self.row_hbox)
            line.add_css_class("label_from_popover_launcher")
            image.add_css_class("icon_from_popover_launcher")

        for i in self.all_apps:
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
            self.widgets_dict[i.get_id()] = self.row_hbox
            self.row_hbox.MYTEXT = name, cmd, keywords
            line = Gtk.Label.new()
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            image = Gtk.Image.new_from_gicon(icon)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            self.row_hbox.append(image)
            self.row_hbox.append(line)
            self.flowbox.append(self.row_hbox)
            line.add_css_class("label_from_popover_launcher")
            image.add_css_class("icon_from_popover_launcher")

        self.flowbox.set_filter_func(self.on_filter_invalidate)
        # Connect signal for selecting a row
        width = self.flowbox.get_preferred_size().natural_size.width
        self.scrolled_window.set_min_content_width(width)
        self.scrolled_window.set_min_content_height(600)
        self.popover_launcher.set_parent(self.menubutton_launcher)
        self.popover_launcher.popup()
        self.flowbox.add_css_class("popover_launcher_flowbox")
        self.popover_launcher.add_css_class("transparent-popover-launcher")
        return self.popover_launcher

    # this is where pressing enter will take effect

    def on_keypress(self, *_):
        cmd = "gtk-launch {}".format(self.search_get_child).split()
        Popen(cmd)
        self.popover_launcher.popdown()

    def update_flowbox(self):
        all_apps = Gio.AppInfo.get_all()
        with open(self.waypanel_cfg, "r") as f:
            dockbar_toml = toml.load(f)["dockbar"]

        dockbar_desktop = [dockbar_toml[i]["desktop_file"] for i in dockbar_toml]
        all_apps = [i for i in all_apps if i.get_id() not in dockbar_desktop]

        # remove widgets from uninstalled apps
        app_ids = [i.get_id() for i in all_apps]
        should_continue = [
            i.get_id() for i in self.all_apps if i.get_id() not in app_ids
        ]

        # if all app_ids match in both all updated apps along with old self all apps
        if not should_continue:
            return

        for app in self.all_apps:
            id = app.get_id()
            if id not in app_ids:
                try:
                    self.flowbox.remove(self.widgets_dict[id])
                except KeyError:
                    pass

        # add new row if there is a new app installed
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
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            image = Gtk.Image.new_from_gicon(icon)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            self.row_hbox.append(image)
            self.row_hbox.append(line)
            self.flowbox.append(self.row_hbox)
            line.add_css_class("label_from_popover_launcher")
            image.add_css_class("icon_from_popover_launcher")

        for i in all_apps:
            if i in self.all_apps:
                continue
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
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            image = Gtk.Image.new_from_gicon(icon)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            self.row_hbox.append(image)
            self.row_hbox.append(line)
            self.flowbox.append(self.row_hbox)
            line.add_css_class("label_from_popover_launcher")
            image.add_css_class("icon_from_popover_launcher")

        self.all_apps = all_apps

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
            self.popover_is_closed()
        if self.popover_launcher and not self.popover_launcher.is_visible():
            self.update_flowbox()
            self.flowbox.unselect_all()
            self.popover_launcher.popup()
            self.searchbar.set_text("")
            self.popover_is_open()

        if not self.popover_launcher:
            self.popover_launcher = self.create_popover_launcher(self.obj)

    def popover_is_open(self, *_):
        LayerShell.set_keyboard_mode(
            self.obj.top_panel, LayerShell.KeyboardMode.ON_DEMAND
        )
        return

    def popover_is_closed(self, *_):
        LayerShell.set_keyboard_mode(self.obj.top_panel, LayerShell.KeyboardMode.NONE)
        # print(LayerShell.get_keyboard_mode(self.top_panel).value_name)

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()

    def select_first_visible_child(self):
        """Select the first visible child in the flowbox."""

        def on_child(child):
            if child.is_visible():
                self.flowbox.select_child(child)
                return True  # Stop iteration after selecting the first visible child
            return False  # Continue iteration

        # Iterate over visible children and select the first one
        self.flowbox.selected_foreach(on_child)
        return False  # Stops the GLib.idle_add loop

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        # run filter (run self.on_filter_invalidate look at self.listbox.set_filter_func(self.on_filter_invalidate) )
        self.flowbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        # get the Entry search
        text_to_search = self.searchbar.get_text().strip()
        if not isinstance(row, str):
            # the line searched for, it will return every line that matches the search
            row = row.get_child().MYTEXT
            # this is to store all rows that match the search and get the first one
            # then we can use on_keypress to start the app
            self.search_row.append(row[1])
            row = f"{row[0]} {row[1]} {row[2]}"

        r = row.lower().strip()
        # checking if the search is valid
        if text_to_search.lower() in r:
            # [-1] is the first item from the search, means first row searched
            # [1] is the desktop file, example.desktop
            self.search_get_child = self.search_row[-1]
            # clean up because we only need the list to get the first row
            self.search_row = []
            return True
        return False
