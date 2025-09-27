import os
import random
import sqlite3
import time
from subprocess import Popen
from gi.repository import Gio, Gtk, Pango, Gdk  # pyright: ignore
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    position = "top-panel-box-widgets-left"
    order = 1
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        menu = AppLauncher(panel_instance)
        menu.create_menu_popover_launcher()
        return menu


class AppLauncher(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_launcher = None
        self.widgets_dict = {}
        self.all_apps = None
        self.appmenu = Gtk.Button()
        self.search_get_child = None
        self.icons = {}
        self.search_row = []
        self.db_path = self.path_handler.get_data_path("waypanel", "recent_apps.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._create_recent_apps_table()
        self.main_widget = (self.appmenu, "append")

    def _create_recent_apps_table(self):
        """Creates the SQLite table for recent apps if it doesn't exist."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_apps (
                app_name TEXT PRIMARY KEY,
                last_opened_at REAL
            )
        """)
        self.conn.commit()

    def close(self):
        """Closes the database connection."""
        self.conn.close()

    def create_menu_popover_launcher(self):
        """Create the menu button and connect its signal to open the popover launcher."""
        self.appmenu.connect("clicked", self.open_popover_launcher)
        self.appmenu.add_css_class("app-launcher-menu-button")
        icon_name = self.gtk_helper.set_widget_icon_name(
            "appmenu",
            ["archlinux-logo"],
        )
        self.appmenu.set_icon_name(icon_name)
        self.appmenu.add_css_class("app-launcher-menu-icon")
        self.gtk_helper.add_cursor_effect(self.appmenu)

    def create_popover_launcher(self, *_):
        """Create and configure the popover launcher."""
        self.popover_launcher = self._create_and_configure_popover()
        self._setup_scrolled_window_and_flowbox()
        self._populate_flowbox_with_apps()
        self._finalize_popover_setup()
        return self.popover_launcher

    def _create_and_configure_popover(self):
        """Create and configure the popover."""
        popover = Gtk.Popover()
        popover.add_css_class("app-launcher-popover")
        popover.set_has_arrow(True)
        popover.connect("closed", self.popover_is_closed)
        popover.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)
        return popover

    def _setup_scrolled_window_and_flowbox(self):
        """Set up the scrolled window, search bar, and flowbox."""
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.main_box.add_css_class("app-launcher-main-box")
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.connect("activate", self.on_keypress)
        self.searchbar.connect("stop-search", self.on_searchbar_key_release)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.set_placeholder_text("Search apps...")
        self.searchbar.add_css_class("app-launcher-searchbar")
        self.main_box.append(self.searchbar)
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_halign(Gtk.Align.FILL)
        self.flowbox.props.max_children_per_line = 30
        self.flowbox.set_max_children_per_line(5)
        self.flowbox.set_homogeneous(False)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.run_app_from_launcher)
        self.flowbox.add_css_class("app-launcher-flowbox")
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.flowbox)
        self.popover_launcher.set_child(self.main_box)  # pyright: ignore

    def _populate_flowbox_with_apps(self):
        """Populate the flowbox with application buttons."""
        all_apps = Gio.AppInfo.get_all()
        random.shuffle(all_apps)
        self.all_apps = [i for i in all_apps if i.get_id()]
        recent_apps = self.get_recent_apps()
        for i in self.all_apps:
            name = i.get_name()
            if name not in recent_apps:
                continue
            self._add_app_to_flowbox(i, name, recent_apps)  # pyright: ignore
        for i in self.all_apps:
            name = i.get_name()
            if name in recent_apps:
                continue
            self._add_app_to_flowbox(i, name, recent_apps)  # pyright: ignore
        self.flowbox.set_filter_func(self.on_filter_invalidate)

    def _finalize_popover_setup(self):
        """Finalize the popover setup."""
        min_size, natural_size = self.flowbox.get_preferred_size()
        width = natural_size.width if natural_size else 0
        self.flowbox.add_css_class("app-launcher-flowbox")
        self.scrolled_window.set_size_request(720, 570)
        self.scrolled_window.set_min_content_width(width)
        self.scrolled_window.set_min_content_height(500)
        if self.popover_launcher:
            self.popover_launcher.set_parent(self.appmenu)
            self.popover_launcher.popup()
            self.popover_launcher.add_css_class("app-launcher-popover")

    def on_keypress(self, *_):
        """Open the app selected from the search bar."""
        cmd = "gtk-launch {}".format(self.search_get_child).split()
        Popen(cmd)
        if self.popover_launcher:
            self.popover_launcher.popdown()

    def update_flowbox(self):
        """
        Updates the flowbox by removing uninstalled apps, adding new apps,
        and prioritizing recently opened apps at the top.
        """
        while child := self.flowbox.get_child_at_index(0):
            self.flowbox.remove(child)
        self.icons.clear()
        all_apps = Gio.AppInfo.get_all()
        recent_apps = self.get_recent_apps()
        for app_name in recent_apps:
            app = next((a for a in all_apps if a.get_name() == app_name), None)
            if app:
                self._add_app_to_flowbox(app, app_name)
        for app in all_apps:
            app_name = app.get_name()
            if app_name not in recent_apps:
                self._add_app_to_flowbox(app, app_name)

    def _add_app_to_flowbox(self, app, name, recent=False):
        """
        Adds an application to the flowbox.
        Args:
            app: The Gio.AppInfo object representing the app.
            name: The name of the app.
            recent: Whether the app is being added as a recent app.
        """
        if hasattr(app, "get_keywords"):
            keywords = " ".join(app.get_keywords())
        else:
            keywords = ""
        if not name:
            name = app.get_name()
        if name.count(" ") > 2:
            name = " ".join(name.split()[:3])
        icon = app.get_icon()
        cmd = app.get_id()
        if icon is None:
            icon = Gio.ThemedIcon.new_with_default_fallbacks(
                "application-x-executable-symbolic"
            )
        if name not in self.icons:
            vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            vbox.set_halign(Gtk.Align.CENTER)
            vbox.set_valign(Gtk.Align.CENTER)
            vbox.set_margin_top(1)
            vbox.set_margin_bottom(1)
            vbox.set_margin_start(1)
            vbox.set_margin_end(1)
            vbox.add_css_class("app-launcher-vbox")
            vbox.MYTEXT = name, cmd, keywords  # pyright: ignore
            image = Gtk.Image.new_from_gicon(icon)
            image.set_halign(Gtk.Align.CENTER)
            image.add_css_class("app-launcher-icon-from-popover")
            self.gtk_helper.add_cursor_effect(image)
            label = Gtk.Label.new(name)
            label.set_max_width_chars(20)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_halign(Gtk.Align.CENTER)
            label.add_css_class("app-launcher-label-from-popover")
            self.icons[name] = {"icon": image, "label": label, "vbox": vbox}
            vbox = self.icons[name]["vbox"]
            vbox.append(self.icons[name]["icon"])
            vbox.append(self.icons[name]["label"])
            gesture = Gtk.GestureClick.new()
            gesture.set_button(Gdk.BUTTON_SECONDARY)
            gesture.connect("pressed", self.on_right_click_popover, vbox)
            vbox.add_controller(gesture)
            self.flowbox.append(vbox)
            self.flowbox.add_css_class("app-launcher-flowbox")

    def add_recent_app(self, app_name):
        """
        Add or update an app in the recent apps table.
        Ensures the app is moved to the end of the list if it already exists.
        """
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO recent_apps (app_name, last_opened_at)
            VALUES (?, ?)
        """,
            (app_name, time.time()),
        )
        self.conn.commit()
        self.cursor.execute("SELECT COUNT(*) FROM recent_apps")
        count = self.cursor.fetchone()[0]
        if count > 50:
            self.cursor.execute(
                """
                DELETE FROM recent_apps
                WHERE app_name IN (
                    SELECT app_name FROM recent_apps ORDER BY last_opened_at ASC LIMIT ?
                )
            """,
                (count - 50,),
            )
            self.conn.commit()

    def get_recent_apps(self):
        """Get the list of recent apps from the SQLite database."""
        self.cursor.execute(
            "SELECT app_name FROM recent_apps ORDER BY last_opened_at DESC LIMIT 50"
        )
        recent_apps = [row[0] for row in self.cursor.fetchall()]
        return recent_apps

    def run_app_from_launcher(self, x, y):
        """Run the selected app from the launcher."""
        mytext = [i.get_child().MYTEXT for i in x.get_selected_children()][0]
        name, desktop, keywords = mytext
        desktop = desktop.split(".desktop")[0]
        cmd = "gtk-launch {}".format(desktop)
        self.add_recent_app(name)
        self.cmd.run(cmd)
        if self.popover_launcher:
            self.popover_launcher.popdown()
        self.update_flowbox()

    def open_popover_launcher(self, *_):
        """Open or close the popover launcher safely without leaking memory."""
        if self.popover_launcher:
            if self.popover_launcher.is_visible():
                self.popover_launcher.popdown()
                self.popover_is_closed()
            else:
                self.update_flowbox()
                self.flowbox.unselect_all()
                self.popover_launcher.popup()
                self.searchbar.set_text("")
                self.popover_is_open()
        else:
            self.popover_launcher = self.create_popover_launcher(self.obj)
            self.popover_launcher.popup()
            self.popover_is_open()

    def popover_is_open(self, *_):
        """Set the keyboard mode to ON_DEMAND when the popover is opened."""
        LayerShell.set_keyboard_mode(
            self.obj.top_panel, LayerShell.KeyboardMode.ON_DEMAND
        )
        vadjustment = self.scrolled_window.get_vadjustment()
        vadjustment.set_value(0)
        return

    def popover_is_closed(self, *_):
        """Set the keyboard mode to NONE when the popover is closed."""
        LayerShell.set_keyboard_mode(self.obj.top_panel, LayerShell.KeyboardMode.NONE)
        self.obj.top_panel.grab_focus()
        toplevel = self.obj.top_panel.get_root()
        if isinstance(toplevel, Gtk.Window):
            toplevel.set_focus(None)
        if hasattr(self, "listbox"):
            self.flowbox.invalidate_filter()

    def on_searchbar_key_release(self, widget, event):
        """
        Handle key release events on the search bar.
        """
        keyval = event.keyval
        if keyval == Gdk.KEY_Escape:
            if self.popover_launcher:
                self.popover_launcher.popdown()
            return True
        return False

    def on_show_searchbar_action_actived(self, action, parameter):
        """Show the search bar when the show_searchbar action is activated."""
        self.searchbar.set_search_mode(  # pyright: ignore
            True
        )

    def search_entry_grab_focus(self):
        """Grab focus to the search entry."""
        self.searchentry.grab_focus()  # pyright: ignore

    def select_first_visible_child(self):
        """Select the first visible child in the flowbox."""

        def on_child(child):
            if child.is_visible():
                self.flowbox.select_child(child)
                return True
            return False

        self.flowbox.selected_foreach(on_child)  # pyright: ignore
        return False

    def add_to_dockbar(self, button, name, desktop_file, popover):
        """
        Adds the selected app to the dockbar configuration in waypanel.toml.
        """
        wclass = os.path.splitext(desktop_file)[0]
        new_entry = {
            "cmd": f"gtk-launch {desktop_file}",
            "icon": wclass,
            "wclass": wclass,
            "desktop_file": desktop_file,
            "name": name,
            "initial_title": name,
        }
        dockbar_config = self.config_handler.config_data.get("dockbar", {})
        app_config = dockbar_config.get("app", {})
        app_config[name] = new_entry
        dockbar_config["app"] = app_config
        self.config_handler.config_data["dockbar"] = dockbar_config
        self.config_handler.save_config()
        self.config_handler.reload_config()
        popover.popdown()
        if self.popover_launcher:
            self.popover_launcher.popdown()
        self.update_flowbox()

    def open_desktop_file(self, button, desktop_file, popover):
        """
        Finds and opens the application's .desktop file. Tries a list of
        fallback editors if xdg-open fails.
        """
        common_locations = [
            "/usr/share/applications/",
            os.path.expanduser("~/.local/share/applications/"),
        ]
        file_path = None
        for location in common_locations:
            path_to_check = os.path.join(location, desktop_file)
            if os.path.exists(path_to_check):
                file_path = path_to_check
                break
        if file_path:
            gui_editors = [
                "gedit",
                "code",
                "atom",
                "subl",
            ]
            terminal_editors = ["nvim", "nano"]
            terminal_emulators = ["kitty", "alacritty", "gnome-terminal"]
            for editor in gui_editors:
                try:
                    cmd = editor + " " + file_path
                    self.cmd.run(cmd)
                    popover.popdown()
                    if self.popover_launcher:
                        self.popover_launcher.popdown()
                    return
                except Exception as e:
                    self.logger.error(f"Appmenu: No text editor found: {e}")
                    continue
            for term in terminal_emulators:
                for editor in terminal_editors:
                    try:
                        cmd = [term, "-e", editor, file_path]
                        Popen(cmd)
                        popover.popdown()
                        if self.popover_launcher:
                            self.popover_launcher.popdown()
                        return
                    except FileNotFoundError:
                        continue
            self.logger.error(
                "Error: Could not find an editor to open the .desktop file."
            )

    def on_right_click_popover(self, gesture, n_press, x, y, vbox):
        """
        Handle right-click event to show a popover menu.
        """
        popover = Gtk.Popover()
        popover.add_css_class("app-launcher-context-menu")
        menu_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        menu_box.set_margin_start(10)
        menu_box.set_margin_end(10)
        menu_box.set_margin_top(10)
        menu_box.set_margin_bottom(10)
        name, desktop_file, keywords = vbox.MYTEXT
        is_in_dockbar = desktop_file in self.config_handler.config_data.get(
            "dockbar", {}
        )
        open_button = Gtk.Button.new_with_label(f"Open {name}")
        open_button.connect("clicked", self.run_app_from_menu, desktop_file, popover)
        menu_box.append(open_button)
        open_desktop_button = Gtk.Button.new_with_label("Open .desktop File")
        open_desktop_button.connect(
            "clicked", self.open_desktop_file, desktop_file, popover
        )
        menu_box.append(open_desktop_button)
        search_button = Gtk.Button.new_with_label("Search in GNOME Software")
        search_button.connect("clicked", self.search_in_gnome_software, name, popover)
        menu_box.append(search_button)
        if is_in_dockbar:
            remove_button = Gtk.Button.new_with_label("Remove from dockbar")
            remove_button.connect(
                "clicked", self.remove_from_dockbar, desktop_file, popover
            )
            menu_box.append(remove_button)
        else:
            add_button = Gtk.Button.new_with_label("Add to dockbar")
            add_button.connect(
                "clicked", self.add_to_dockbar, name, desktop_file, popover
            )
            menu_box.append(add_button)
        popover.set_child(menu_box)
        popover.set_parent(vbox)
        popover.set_has_arrow(False)
        popover.popup()
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def remove_from_dockbar(self, button, desktop_file, popover):
        """
        Removes the selected app from the dockbar configuration.
        """
        if desktop_file in self.config_handler.config_data.get("dockbar", {}):
            del self.config_handler.config_data["dockbar"][desktop_file]
            self.config_handler.save_config()
        popover.popdown()
        if self.popover_launcher:
            self.popover_launcher.popdown()
        self.update_flowbox()

    def search_in_gnome_software(self, button, name, popover):
        """
        Runs gnome-software with the search parameter for the selected application.
        """
        cmd = ["gnome-software", f"--search={name}"]
        try:
            Popen(cmd)
        except FileNotFoundError:
            self.logger.error("Error: gnome-software command not found.")
        finally:
            popover.popdown()
            if self.popover_launcher:
                self.popover_launcher.popdown()

    def run_app_from_menu(self, button, desktop_file, popover):
        """
        Runs the app when the 'Open' button in the context menu is clicked.
        """
        cmd = "gtk-launch {}".format(desktop_file)
        self.cmd.run(cmd)
        popover.popdown()
        if self.popover_launcher:
            self.popover_launcher.popdown()
        self.update_flowbox()

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        self.flowbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        """Filter the flowbox rows based on the search entry."""
        text_to_search = self.searchbar.get_text().strip().lower()
        if not isinstance(row, str):
            name, desktop, keywords = row.get_child().MYTEXT
            combined_text = f"{name} {desktop} {keywords}".lower()
            if text_to_search in combined_text:
                self.search_get_child = desktop
                return True
            else:
                return False
        else:
            return text_to_search in row.lower().strip()

    def about(self):
        """A dynamic application launcher with a search bar and a grid view of installed and recently used applications."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin creates a full-featured application launcher integrated into the panel.
        It provides a visual, searchable interface for launching applications directly.
        Its core logic is centered on **dynamic UI generation, state management, and interaction**:
        1.  **Application Discovery**: It retrieves all installed applications using
            `Gio.AppInfo.get_all()` and filters out any apps that are already
            in the dockbar, preventing redundancy.
        2.  **Recent Apps Persistence**: A key feature is its ability to track
            recently launched applications by reading from and writing to a
            hidden file (`~/.config/waypanel/.recent-apps`). This allows the
            launcher to prioritize frequently used apps, improving user experience.
        3.  **Dynamic Filtering**: It uses a `Gtk.SearchEntry` connected to a
            `Gtk.FlowBox` to provide a fast, real-time search experience. The
            `invalidate_filter` method efficiently hides/shows applications
            that match the search query.
        4.  **Popover and UI**: The launcher is displayed in a `Gtk.Popover` that
            is attached to a main button. The applications themselves are
            displayed in a grid-like layout using `Gtk.FlowBox`, which dynamically
            arranges widgets (icons and labels) based on available space.
        5.  **System Integration**: It interacts with the `Gtk4LayerShell` to
            manage keyboard focus, ensuring the search bar is active when the
            launcher is open and relinquishes focus when it's closed.
        """
        return self.code_explanation.__doc__
