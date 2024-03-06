import os
import random
import gi
from gi.repository import Gio, Gtk, Adw, GLib
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen


class PopoverWallpaper(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_wallpaper = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()

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

    def create_menu_popover_wallpaper(self, obj, app, *_):
        self.top_panel = obj.top_panel
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        self.menubutton_wallpaper = Gtk.Button()
        self.menubutton_wallpaper.connect("clicked", self.open_popover_wallpaper)
        self.menubutton_wallpaper.set_icon_name("livewallpaper")
        obj.top_panel_box_widgets_left.append(self.menubutton_wallpaper)
        self.menubutton_wallpaper.add_css_class("top_left_widgets")
        self.app = app

    def create_popover_wallpaper(self, *_):
        # Create a popover
        self.popover_wallpaper = Gtk.Popover.new()
        self.popover_wallpaper.set_autohide(True)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        self.add_action(show_searchbar_action)
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
            "row-selected", lambda widget, row: self.open_wallpaper(row)
        )
        self.searchbar.set_key_capture_widget(self.top_panel)
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)
        self.popover_wallpaper.set_child(self.main_box)
        wallpapers_path = GLib.get_user_special_dir(
            GLib.UserDirectory.DIRECTORY_PICTURES
        )
        wallpapers_path = os.path.join(wallpapers_path, "Wallpapers")

        if not os.path.exists(wallpapers_path):
            os.mkdir(wallpapers_path)
        wallpaper_files = os.listdir(wallpapers_path)
        random.shuffle(wallpaper_files)
        wallpaper_files = wallpaper_files[:8]
        for wallpaper in wallpaper_files:
            wallpaper_path = os.path.join(wallpapers_path, wallpaper)
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = wallpaper_path
            image = Gtk.Image.new_from_file(wallpaper_path)
            row_hbox.append(image)
            row_hbox.add_css_class("wallpaper")
            self.listbox.append(row_hbox)
        self.listbox.set_filter_func(self.on_filter_invalidate)
        self.popover_wallpaper.set_parent(self.menubutton_wallpaper)
        self.popover_wallpaper.popup()
        return self.popover_wallpaper

    def open_wallpaper(self, x):
        import shutil

        img = x.get_child().MYTEXT
        cmd = "swww img {0}".format(img).split()
        Popen(cmd)
        default_wallpaper_path = os.path.join(self.home, ".config/hypr/fav.jpg")
        shutil.copyfile(img, default_wallpaper_path)
        self.popover_wallpaper.popdown()

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

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

    def open_popover_wallpaper(self, *_):
        if self.popover_wallpaper and self.popover_wallpaper.is_visible():
            self.popover_wallpaper.popdown()

        self.create_popover_wallpaper(self.app)
