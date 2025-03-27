import os
import random
from subprocess import Popen

import gi
import toml
from gi.repository import Adw, Gio, Gtk
from gi.repository import Gtk4LayerShell as LayerShell


class PopoverFolders(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_folders = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.home_folders = os.listdir(self.home)
        self.scripts = os.path.join(self.home, ".config/hypr/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.topbar_folders_config = os.path.join(
            self.config_path, "topbar-folders.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}

    def create_menu_popover_folders(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        self.menubutton_folders = Gtk.Button()
        self.menubutton_folders.connect("clicked", self.open_popover_folders)
        panel_config_path = os.path.join(self.config_path, "panel.toml")
        menu_icon = "folder"
        if os.path.exists(panel_config_path):
            with open(panel_config_path, "r") as f:
                panel_config = toml.load(f)
            menu_icon = panel_config.get("top", {}).get("folder_icon", "folder")
        self.menubutton_folders.set_icon_name(menu_icon)
        self.menubutton_folders.add_css_class("top_left_widgets")
        obj.top_panel_box_widgets_left.append(self.menubutton_folders)

    def create_popover_folders(self, *_):
        """
        Create and configure a popover for folders.
        """
        # Create a new popover menu
        self.popover_folders = Gtk.Popover.new()
        self.popover_folders.set_has_arrow(False)
        self.popover_folders.set_autohide(True)
        self.popover_folders.connect("closed", self.popover_is_closed)
        self.popover_folders.connect("notify::visible", self.popover_is_open)

        # Create an action to show the search bar
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.app.add_action(show_searchbar_action)

        # Set up scrolled window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(400)
        self.scrolled_window.set_min_content_height(600)

        # Set up main box
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

        # Create and configure search bar
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.props.hexpand = True
        self.searchbar.props.vexpand = True

        self.main_box.append(self.searchbar)

        # Create and configure listbox
        self.listbox = Gtk.ListBox.new()
        self.listbox.connect("row-selected", lambda widget, row: self.open_folder(row))
        self.searchbar.set_key_capture_widget(self.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)

        # Configure popover with main box
        self.popover_folders.set_child(self.main_box)

        # Load folders from file
        folders_path = os.path.join(self.config_path, "folders.toml")
        with open(folders_path, "r") as f:
            all_folders = toml.load(f)
        # Populate listbox with folders
        for folder in all_folders.items():
            name = folder[1]["name"]
            folders_path = folder[1]["path"]
            filemanager = folder[1]["filemanager"]
            icon = folder[1]["icon"]

            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = folders_path, filemanager

            # Configure bookmark icon

            # Add the bookmark to the listbox
            self.listbox.append(row_hbox)

            # Create label for the bookmark name
            line = Gtk.Label.new()
            line.add_css_class("label_from_folders")
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            # Create image for the bookmark icon
            image = Gtk.Image.new_from_icon_name(icon)
            image.add_css_class("icon_from_folders")
            image.set_icon_size(Gtk.IconSize.INHERIT)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)

            # Add label and image to the bookmark box
            row_hbox.append(image)
            row_hbox.append(line)

        for folder in self.home_folders:
            folders_path = os.path.join(self.home, folder)
            icon = "nautilus"

            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = folders_path, "nautilus"

            # Configure bookmark icon

            # Add the bookmark to the listbox
            self.listbox.append(row_hbox)

            # Create label for the bookmark name
            line = Gtk.Label.new()
            line.add_css_class("label_from_folders")
            line.set_label(folder)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            # Create image for the bookmark icon
            image = Gtk.Image.new_from_icon_name(icon)
            image.add_css_class("icon_from_folders")
            image.set_icon_size(Gtk.IconSize.LARGE)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)

            # Add label and image to the bookmark box
            row_hbox.append(image)
            row_hbox.append(line)

        # Configure listbox filter function
        self.listbox.set_filter_func(self.on_filter_invalidate)

        # Set the parent and display the popover
        self.popover_folders.set_parent(self.menubutton_folders)
        self.popover_folders.popup()

        return self.popover_folders

    def open_folder(self, x):
        folder, filemanager = x.get_child().MYTEXT
        path = os.path.join(self.home, folder)
        cmd = "{0} {1}".format(filemanager, path).split()
        Popen(cmd)
        self.popover_folders.popdown()

    def open_popover_folders(self, *_):
        if self.popover_folders and self.popover_folders.is_visible():
            self.popover_folders.popdown()
        if self.popover_folders and not self.popover_folders.is_visible():
            self.listbox.unselect_all()
            self.popover_folders.popup()
        if not self.popover_folders:
            self.popover_folders = self.create_popover_folders(self.app)

    def popover_is_open(self, *_):
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)

    def popover_is_closed(self, *_):
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
