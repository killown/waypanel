import os
import random
from subprocess import Popen
from gi.repository import Adw, Gio, Gtk
from gi.repository import Gtk4LayerShell as LayerShell
from ...core.utils import Utils

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "left"
    order = 1
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        menu = AppLauncher(panel_instance)
        menu.create_menu_popover_launcher()
        return menu


class AppLauncher(Adw.Application):
    def __init__(self, panel_instance):
        self.popover_launcher = None
        self.obj = panel_instance
        self.widgets_dict = {}
        self.all_apps = None
        self.menubutton_launcher = Gtk.Button()
        self.top_panel = None
        self.search_get_child = None
        self.search_row = []
        self.recent_apps_file = os.path.expanduser("~/config/waypanel/.recent-apps")
        self.utils = Utils(application_id="com.github.utils")

    def append_widget(self):
        return self.menubutton_launcher

    def create_menu_popover_launcher(self):
        self.menubutton_launcher.connect("clicked", self.open_popover_launcher)
        self.menubutton_launcher.add_css_class("app-launcher-menu-button")
        menu_icon = self.utils.get_nearest_icon_name(
            self.obj.config.get("top", {}).get(
                "menu_icon", self.utils.get_nearest_icon_name("archlinux")
            )
        )
        self.menubutton_launcher.set_icon_name(menu_icon)

    def create_popover_launcher(self, *_):
        """Create and configure the popover launcher."""
        # Step 1: Create and configure the popover
        self.popover_launcher = self._create_and_configure_popover()

        # Step 2: Set up the scrolled window, search bar, and flowbox
        self._setup_scrolled_window_and_flowbox()

        # Step 3: Populate the flowbox with application buttons
        self._populate_flowbox_with_apps()

        # Step 4: Finalize the popover setup
        self._finalize_popover_setup()

        return self.popover_launcher

    def _create_and_configure_popover(self):
        """Create and configure the popover."""
        popover = Gtk.Popover()
        popover.set_has_arrow(False)
        popover.connect("closed", self.popover_is_closed)
        popover.connect("notify::visible", self.popover_is_open)

        # Add show_searchbar action
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)

        return popover

    def _setup_scrolled_window_and_flowbox(self):
        """Set up the scrolled window, search bar, and flowbox."""
        # Scrolled window setup
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )

        # Main box and search bar setup
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.connect("activate", self.on_keypress)
        self.searchbar.set_focus_on_click(True)

        self.main_box.append(self.searchbar)

        # Flowbox setup
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(1)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.run_app_from_launcher)

        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.flowbox)
        self.popover_launcher.set_child(self.main_box)

    def _populate_flowbox_with_apps(self):
        """Populate the flowbox with application buttons."""
        all_apps = Gio.AppInfo.get_all()
        random.shuffle(all_apps)
        dockbar_toml = self.obj.config["dockbar"]
        dockbar_desktop = [dockbar_toml[i]["desktop_file"] for i in dockbar_toml]
        self.all_apps = [i for i in all_apps if i.get_id() not in dockbar_desktop]

        # Recent apps handling
        recent_apps = self.get_recent_apps()
        for i in self.all_apps:
            name = i.get_name()
            if name not in recent_apps:
                continue
            self._add_app_to_flowbox(i, name, recent_apps)

        # Non-recent apps handling
        for i in self.all_apps:
            name = i.get_name()
            if name in recent_apps:
                continue
            self._add_app_to_flowbox(i, name, recent_apps)

        self.flowbox.set_filter_func(self.on_filter_invalidate)

    def _finalize_popover_setup(self):
        """Finalize the popover setup."""
        min_size, natural_size = self.flowbox.get_preferred_size()
        width = natural_size.width if natural_size else 0
        self.flowbox.add_css_class("app-launcher-flowbox")
        self.scrolled_window.set_min_content_width(width)
        self.scrolled_window.set_min_content_height(600)
        if self.popover_launcher:
            self.popover_launcher.set_parent(self.menubutton_launcher)
            self.popover_launcher.popup()
            self.popover_launcher.add_css_class("app-launcher-popover")

    def on_keypress(self, *_):
        cmd = "gtk-launch {}".format(self.search_get_child).split()
        Popen(cmd)
        if self.popover_launcher:
            self.popover_launcher.popdown()

    def update_flowbox(self):
        """
        Updates the flowbox by removing uninstalled apps, adding new apps,
        and prioritizing recently opened apps at the top.
        """
        # Fetch all available applications and filter out docked apps
        all_apps = Gio.AppInfo.get_all()
        dockbar_toml = self.obj.config["dockbar"]
        dockbar_desktop = {dockbar_toml[i]["desktop_file"] for i in dockbar_toml}
        all_apps = [app for app in all_apps if app.get_id() not in dockbar_desktop]

        # Clear the flowbox
        self.flowbox.remove_all()

        # Get the list of recent apps and reverse it
        recent_apps = self.get_recent_apps()
        recent_apps = list(
            reversed(recent_apps)
        )  # Reverse the list to display the most recent app first

        # Add recent apps to the flowbox first
        for app_name in recent_apps:
            app = next((a for a in all_apps if a.get_name() == app_name), None)
            if app:
                self._add_app_to_flowbox(app, app_name, recent=True)

        # Add non-recent apps to the flowbox
        for app in all_apps:
            app_name = app.get_name()
            if app_name not in recent_apps:
                self._add_app_to_flowbox(app, app_name, recent=False)

        # Update the list of all apps
        self.all_apps = all_apps

    def _add_app_to_flowbox(self, app, name, recent=False):
        """
        Adds an application to the flowbox.

        Args:
            app: The Gio.AppInfo object representing the app.
            name: The name of the app.
            recent: Whether the app is being added as a recent app.
        """
        keywords = " ".join(app.get_keywords())
        if not name:
            name = app.get_name()
        if name.count(" ") > 2:
            name = " ".join(name.split()[:3])

        icon = app.get_icon()
        cmd = app.get_id()
        if icon is None:
            return

        row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self.widgets_dict[app.get_id()] = row_hbox
        row_hbox.MYTEXT = name, cmd, keywords

        line = Gtk.Label.new()
        line.set_label(name)
        line.props.margin_start = 5
        line.props.hexpand = True
        line.set_halign(Gtk.Align.START)

        image = Gtk.Image.new_from_gicon(icon)
        image.props.margin_end = 5
        image.set_halign(Gtk.Align.END)

        row_hbox.append(image)
        row_hbox.append(line)
        self.flowbox.append(row_hbox)

        line.add_css_class("app-launcher-label-from-popover")
        image.add_css_class("app-launcher-icon-from-popover")

    def add_recent_app(self, app_name):
        """
        Add or update an app in the recent apps list.
        Ensures the app is moved to the end of the list if it already exists.
        """
        os.makedirs(os.path.dirname(self.recent_apps_file), exist_ok=True)

        # Read the existing list of recent apps
        if os.path.exists(self.recent_apps_file):
            with open(self.recent_apps_file, "r") as f:
                recent_apps = f.read().splitlines()
        else:
            recent_apps = []

        # Remove the app if it already exists in the list
        if app_name in recent_apps:
            recent_apps.remove(app_name)

        # Add the app to the end of the list
        recent_apps.append(app_name)

        # Truncate the list to the last 50 entries
        recent_apps = recent_apps[-50:]

        # Write the updated list back to the file
        with open(self.recent_apps_file, "w") as f:
            f.write("\n".join(recent_apps))
            f.flush()  # Ensure data is written to disk immediately

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

        # Add the app to the recent apps list
        self.add_recent_app(name)

        # Launch the app
        Popen(cmd)
        if self.popover_launcher:
            self.popover_launcher.popdown()

        # Refresh the flowbox to reflect the updated recent apps list
        self.update_flowbox()

    def open_popover_launcher(self, *_):
        if self.popover_launcher and self.popover_launcher.is_visible():
            self.popover_launcher.popdown()
            self.popover_is_closed()
        elif self.popover_launcher and not self.popover_launcher.is_visible():
            self.update_flowbox()  # Refresh the flowbox
            self.flowbox.unselect_all()
            self.popover_launcher.popup()
            self.searchbar.set_text("")
            self.popover_is_open()
        else:
            self.popover_launcher = self.create_popover_launcher(self.obj)

    def popover_is_open(self, *_):
        LayerShell.set_keyboard_mode(
            self.obj.top_panel, LayerShell.KeyboardMode.ON_DEMAND
        )
        # reset scrollbar position after launch an app
        vadjustment = self.scrolled_window.get_vadjustment()
        vadjustment.set_value(0)
        return

    def popover_is_closed(self, *_):
        LayerShell.set_keyboard_mode(self.obj.top_panel, LayerShell.KeyboardMode.NONE)
        self.obj.top_panel.grab_focus()
        toplevel = self.obj.top_panel.get_root()
        if isinstance(toplevel, Gtk.Window):
            toplevel.set_focus(None)
        if hasattr(self, "listbox"):
            self.flowbox.invalidate_filter()

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
