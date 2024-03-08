import os
import random
import gi
from gi.repository import Gio, Gtk, Adw
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen
import toml
import wayfire


class PopoverBookmarks(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_bookmarks = None
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

    def create_menu_popover_bookmarks(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        self.menubutton_bookmarks = Gtk.Button()
        self.menubutton_bookmarks.connect("clicked", self.open_popover_bookmarks)
        self.menubutton_bookmarks.set_icon_name("firefox-developer-edition")
        self.menubutton_bookmarks.add_css_class("top_left_widgets")
        obj.top_panel_box_widgets_left.append(self.menubutton_bookmarks)

    def create_popover_bookmarks(self, *_):
        """
        Create and configure a popover for bookmarks.
        """
        # Create a new popover menu
        self.popover_bookmarks = Gtk.Popover.new()
        self.popover_bookmarks.set_autohide(True)

        # Create an action to show the search bar
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.app.add_action(show_searchbar_action)

        # Set up scrolled window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(200)
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
        self.listbox.connect(
            "row-selected", lambda widget, row: self.open_url_from_bookmarks(row)
        )
        self.searchbar.set_key_capture_widget(self.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)

        # Configure popover with main box
        self.popover_bookmarks.set_child(self.main_box)

        # Load bookmarks from file
        bookmarks_path = os.path.join(self.home, ".bookmarks")
        with open(bookmarks_path, "r") as f:
            all_bookmarks = toml.load(f)

        # Populate listbox with bookmarks
        for name, bookmark_data in all_bookmarks.items():
            url = bookmark_data.get("url", "")
            container = bookmark_data.get("container", "")

            # Create a box for each bookmark
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = url, container

            # Configure bookmark icon
            icon = url
            if "/" in icon:
                icon = [i for i in icon.split("/") if "." in i][0]
                icon = "{0}.png".format(icon)
                print(icon)
            else:
                icon = url + ".png"
            bookmark_image = os.path.join(self.config_path, "bookmarks/images/", icon)

            # Add the bookmark to the listbox
            self.listbox.append(row_hbox)

            # Create label for the bookmark name
            line = Gtk.Label.new()
            line.add_css_class("label_from_bookmarks")
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            # Create image for the bookmark icon
            image = Gtk.Image.new_from_file(bookmark_image)
            image.add_css_class("icon_from_popover_launcher")
            image.set_icon_size(Gtk.IconSize.LARGE)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)

            # Add label and image to the bookmark box
            row_hbox.append(image)
            row_hbox.append(line)

        # Configure listbox filter function
        self.listbox.set_filter_func(self.on_filter_invalidate)

        # Set the parent and display the popover
        self.popover_bookmarks.set_parent(self.menubutton_bookmarks)
        self.popover_bookmarks.popup()

        return self.popover_bookmarks

    def open_url_from_bookmarks(self, x):
        url, container = x.get_child().MYTEXT
        sock = self.compositor()
        all_windows = sock.list_views()
        view = [
            i["id"] for i in all_windows if "firefoxdeveloperedition" in i["app-id"]
        ]
        if view:
            sock.set_focus(view[0])
        cmd = [
            "firefox-developer-edition",
            "ext+container:name={0}&url={1}".format(container, url),
        ]
        Popen(cmd)
        self.popover_bookmarks.popdown()

    def open_popover_bookmarks(self, *_):
        if self.popover_bookmarks and self.popover_bookmarks.is_visible():
            self.popover_bookmarks.popdown()
        if self.popover_bookmarks and not self.popover_bookmarks.is_visible():
            self.popover_bookmarks.popup()
        if not self.popover_bookmarks:
            self.popover_bookmarks = self.create_popover_bookmarks(self.app)

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

    def compositor(self):
        addr = os.getenv("WAYFIRE_SOCKET")
        return wayfire.WayfireSocket(addr)
