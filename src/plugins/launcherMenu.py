import os
import random
import gi
from gi.repository import Gio, Gtk, Adw
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
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        self.app = app
        self.menubutton_launcher = Gtk.Button()
        self.menubutton_launcher.connect("clicked", self.open_popover_launcher)
        self.menubutton_launcher.set_icon_name("start-here-archlinux")
        self.menubutton_launcher.add_css_class("top_left_widgets")
        obj.top_panel_box_widgets_left.append(self.menubutton_launcher)

    def create_popover_launcher(self, *_):
        # Create a popover
        self.popover_launcher = Gtk.Popover.new()  # Create a new popover menu
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.app.add_action(show_searchbar_action)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(400)
        self.scrolled_window.set_min_content_height(600)
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.props.hexpand = True
        self.searchbar.props.vexpand = True

        self.main_box.append(self.searchbar)
        self.listbox = Gtk.ListBox.new()
        self.listbox.connect(
            "row-selected", lambda widget, row: self.run_app_from_launcher((row))
        )
        self.searchbar.set_key_capture_widget(self.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)
        self.popover_launcher.set_child(self.main_box)
        all_apps = Gio.AppInfo.get_all()
        # randomize apps displayed every .popup()
        random.shuffle(all_apps)
        with open(self.dockbar_config, "r") as f:
            dockbar_toml = toml.load(f)

        dockbar_apps = [dockbar_toml[i] for i in dockbar_toml]
        dockbar_names = [dockbar_toml[i]["name"] for i in dockbar_toml]
        all_apps = [i for i in all_apps if i.get_display_name not in dockbar_names]
        # #TODO: create a function to not repeate this loop
        for n, i in enumerate(dockbar_apps):
            name = dockbar_names[n]
            filename = i["desktop_file"].strip()
            print(filename)
            icon = i["icon"]
            if icon is None:
                continue
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = name, filename  # to filter later
            self.listbox.append(row_hbox)
            line = Gtk.Label.new()
            line.add_css_class("label_from_popover_launcher")
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            image = Gtk.Image.new_from_icon_name(icon)
            image.add_css_class("icon_from_popover_launcher")
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            row_hbox.append(image)
            row_hbox.append(line)

        for i in all_apps:
            name = i.get_display_name()
            filename = i.get_id()
            icon = i.get_icon()
            if icon is None:
                continue
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = name, filename  # to filter later
            self.listbox.append(row_hbox)
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
            row_hbox.append(image)
            row_hbox.append(line)
        self.listbox.set_filter_func(self.on_filter_invalidate)
        # Create a menu button
        self.popover_launcher.set_parent(self.menubutton_launcher)
        self.popover_launcher.popup()
        return self.popover_launcher

    def run_app_from_launcher(self, x):
        selected_text, filename = x.get_child().MYTEXT
        cmd = "gtk-launch {}".format(filename)
        self.utils.run_app(cmd)
        self.popover_launcher.popdown()

    def open_popover_launcher(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)

        if self.popover_launcher and self.popover_launcher.is_visible():
            self.popover_launcher.popdown()

        self.create_popover_launcher(self.app)

    def open_popover_clipboard(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)

        if self.popover_clipboard and self.popover_clipboard.is_visible():
            self.popover_clipboard.popdown()

        self.create_popover_clipboard(self.app)

    def popover_is_closed(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.NONE)

    def popover_launcher_is_closed(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.NONE)

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
        self.listbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        text_to_search = (
            self.searchbar.get_text().strip()
        )  # get text from searchentry and remove space from start and end
        if not isinstance(row, str):
            row = row.get_child().MYTEXT[0]
        row = row.lower().strip()
        if (
            text_to_search.lower() in row
        ):  # == row_hbox.MYTEXT (Gtk.ListBoxRow===>get_child()===>row_hbox.MYTEXT)
            return True  # if True Show row
        return False
