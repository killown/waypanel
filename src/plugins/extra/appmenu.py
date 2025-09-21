import os
import random
from subprocess import Popen
from gi.repository import Gio, Gtk, Pango, Gdk
from gi.repository import Gtk4LayerShell as LayerShell
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
        self.menubutton_launcher = Gtk.Button()
        self.search_get_child = None
        # we need to store the images to avoid memory leak, no need to re-create them every new flowbox update
        self.icons = {}
        self.search_row = []
        self.recent_apps_file = os.path.expanduser("~/config/waypanel/.recent-apps")
        # The widget to be set in the panel and the action: append or set_content.
        # If you want to build a complete right panel (for example), create a plugin called right_panel.py,
        # use set_content to set the entire layout, then in other plugins call the instance
        # self.plugins["right_panel"]. You can then add more widgets through it.
        self.main_widget = (self.menubutton_launcher, "append")

    def create_menu_popover_launcher(self):
        """Create the menu button and connect its signal to open the popover launcher."""
        self.menubutton_launcher.connect("clicked", self.open_popover_launcher)
        self.menubutton_launcher.add_css_class("app-launcher-menu-button")

        icon_name = self.utils.set_widget_icon_name(
            "appmenu",
            ["archlinux-logo"],
        )
        self.menubutton_launcher.set_icon_name(icon_name)
        self.menubutton_launcher.add_css_class("app-launcher-menu-icon")
        self.utils.add_cursor_effect(self.menubutton_launcher)

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
        popover.add_css_class("app-launcher-popover")
        popover.set_has_arrow(True)
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
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,  # Horizontal, Vertical scroll policy
        )

        # Main box and search bar setup
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.main_box.add_css_class("app-launcher-main-box")
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.connect("activate", self.on_keypress)
        self.searchbar.connect("stop-search", self.on_searchbar_key_release)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.set_placeholder_text(
            "Search apps..."
        )  # Optional: Add placeholder text
        self.searchbar.add_css_class("app-launcher-searchbar")
        self.main_box.append(self.searchbar)

        # Flowbox setup
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)  # Align content to the top
        self.flowbox.set_halign(Gtk.Align.FILL)  # Fill the horizontal space
        self.flowbox.props.max_children_per_line = 30
        self.flowbox.set_max_children_per_line(5)  # Number of icons per row
        self.flowbox.set_homogeneous(False)  # Uniform size for all children
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.run_app_from_launcher)

        # Add CSS class for styling
        self.flowbox.add_css_class("app-launcher-flowbox")

        # Append the FlowBox to the main box via the scrolled window
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.flowbox)

        # Set the main box as the child of the popover
        self.popover_launcher.set_child(self.main_box)  # pyright: ignore

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
        self.scrolled_window.set_size_request(720, 570)
        self.scrolled_window.set_min_content_width(width)
        self.scrolled_window.set_min_content_height(500)
        if self.popover_launcher:
            self.popover_launcher.set_parent(self.menubutton_launcher)
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
        # Fetch all available applications and filter out docked apps
        all_apps = Gio.AppInfo.get_all()
        dockbar_toml = self.config["dockbar"]
        dockbar_desktop = {dockbar_toml[i]["desktop_file"] for i in dockbar_toml}
        all_apps = [app for app in all_apps if app.get_id() not in dockbar_desktop]

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

        # Use a fallback icon if the app does not have an icon
        if icon is None:
            icon = Gio.ThemedIcon.new_with_default_fallbacks(
                "application-x-executable-symbolic"
            )

        # Icon
        if name not in self.icons:
            # Create a vertical box to stack the icon and label
            vbox = Gtk.Box.new(
                Gtk.Orientation.VERTICAL, 5
            )  # Vertical layout with spacing
            vbox.set_halign(Gtk.Align.CENTER)  # Center align the widget horizontally
            vbox.set_valign(Gtk.Align.CENTER)  # Center align the widget vertically
            vbox.set_margin_top(1)  # Add margin at the top
            vbox.set_margin_bottom(1)  # Add margin at the bottom
            vbox.set_margin_start(1)  # Add margin on the left
            vbox.set_margin_end(1)  # Add margin on the right
            vbox.add_css_class("app-launcher-vbox")
            # Store metadata for later use
            vbox.MYTEXT = name, cmd, keywords  # pyright: ignore

            image = Gtk.Image.new_from_gicon(icon)
            image.set_halign(Gtk.Align.CENTER)  # Center align the icon
            image.add_css_class(
                "app-launcher-icon-from-popover"
            )  # Add CSS class for styling

            self.utils.add_cursor_effect(image)

            # Label
            label = Gtk.Label.new(name)
            label.set_max_width_chars(20)  # Limit the width of the label
            label.set_ellipsize(
                Pango.EllipsizeMode.END
            )  # Add ellipsis if text is too long
            label.set_halign(Gtk.Align.CENTER)  # Center align the label
            label.add_css_class(
                "app-launcher-label-from-popover"
            )  # Add CSS class for styling

            self.icons[name] = {"icon": image, "label": label, "vbox": vbox}

            # Add the icon and label to the vertical box
            vbox = self.icons[name]["vbox"]
            vbox.append(self.icons[name]["icon"])
            vbox.append(self.icons[name]["label"])

            # Add Gtk.GestureClick for right-click handling
            gesture = Gtk.GestureClick.new()
            gesture.set_button(Gdk.BUTTON_SECONDARY)
            gesture.connect("pressed", self.on_right_click_popover, vbox)
            vbox.add_controller(gesture)

            # Add the vertical box to the FlowBox
            self.flowbox.append(vbox)
            self.flowbox.add_css_class("app-launcher-flowbox")

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
        """Get the list of recent apps from the file."""
        if os.path.exists(self.recent_apps_file):
            with open(self.recent_apps_file, "r") as f:
                recent_apps = f.read().splitlines()
            return recent_apps
        else:
            return []

    def run_app_from_launcher(self, x, y):
        """Run the selected app from the launcher."""
        mytext = [i.get_child().MYTEXT for i in x.get_selected_children()][0]
        name, desktop, keywords = mytext
        desktop = desktop.split(".desktop")[0]
        cmd = "gtk-launch {}".format(desktop)

        # Add the app to the recent apps list
        self.add_recent_app(name)

        # Launch the app
        self.utils.run_cmd(cmd)
        if self.popover_launcher:
            self.popover_launcher.popdown()

        # Refresh the flowbox to reflect the updated recent apps list
        self.update_flowbox()

    def open_popover_launcher(self, *_):
        """Open or close the popover launcher safely without leaking memory."""
        if self.popover_launcher:
            if self.popover_launcher.is_visible():
                self.popover_launcher.popdown()
                self.popover_is_closed()
            else:
                # Popover exists but is hidden; refresh flowbox safely
                self.update_flowbox()
                self.flowbox.unselect_all()
                self.popover_launcher.popup()
                self.searchbar.set_text("")
                self.popover_is_open()
        else:
            # Create the popover safely
            self.popover_launcher = self.create_popover_launcher(self.obj)
            self.popover_launcher.popup()
            self.popover_is_open()

    def popover_is_open(self, *_):
        """Set the keyboard mode to ON_DEMAND when the popover is opened."""
        LayerShell.set_keyboard_mode(
            self.obj.top_panel, LayerShell.KeyboardMode.ON_DEMAND
        )
        # reset scrollbar position after launch an app
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
            return True  # Signal that we've handled the event
        return False

    def on_show_searchbar_action_actived(self, action, parameter):
        """Show the search bar when the show_searchbar action is activated."""
        self.searchbar.set_search_mode(  # pyright: ignore
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

    def search_entry_grab_focus(self):
        """Grab focus to the search entry."""
        self.searchentry.grab_focus()  # pyright: ignore

    def select_first_visible_child(self):
        """Select the first visible child in the flowbox."""

        def on_child(child):
            if child.is_visible():
                self.flowbox.select_child(child)
                return True  # Stop iteration after selecting the first visible child
            return False  # Continue iteration

        # Iterate over visible children and select the first one
        self.flowbox.selected_foreach(on_child)  # pyright: ignore
        return False  # Stops the GLib.idle_add loop

    def add_to_dockbar(self, button, name, desktop, popover):
        """
        Adds the selected app to the dockbar configuration in waypanel.toml.
        """
        desktop_file_name = desktop.split(".desktop")[0]

        new_entry = {
            "cmd": f"gtk-launch {desktop_file_name}.desktop",
            "icon": name,
            "wclass": desktop_file_name,
            "desktop_file": desktop,
            "name": name,
            "initial_title": name,
        }

        self.config["dockbar"][desktop_file_name] = new_entry
        self.save_config()

        if "dockbar" in self.obj.plugins:
            self.plugins["dockbar"].reload_plugin()

        # Close the popovers
        popover.popdown()
        if self.popover_launcher:
            self.popover_launcher.popdown()

        # Refresh the app launcher's flowbox to reflect the change
        self.update_flowbox()

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

        name, desktop, keywords = vbox.MYTEXT
        desktop_filename = desktop.split(".desktop")[0]

        open_button = Gtk.Button.new_with_label(f"Open {name}")
        open_button.connect(
            "clicked", self.run_app_from_menu, desktop_filename, popover
        )
        menu_box.append(open_button)

        add_button = Gtk.Button.new_with_label(f"Add to dockbar")
        add_button.connect("clicked", self.add_to_dockbar, name, desktop, popover)
        menu_box.append(add_button)

        popover.set_child(menu_box)
        popover.set_parent(vbox)
        popover.set_has_arrow(False)
        popover.popup()

        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def run_app_from_menu(self, button, desktop_file, popover):
        """
        Runs the app when the 'Open' button in the context menu is clicked.
        """
        cmd = "gtk-launch {}".format(desktop_file)
        self.utils.run_cmd(cmd)
        popover.popdown()
        if self.popover_launcher:
            self.popover_launcher.popdown()
        self.update_flowbox()

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        # run filter (run self.on_filter_invalidate look at self.listbox.set_filter_func(self.on_filter_invalidate) )
        self.flowbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        """Filter the flowbox rows based on the search entry."""
        text_to_search = self.searchbar.get_text().strip().lower()

        if not isinstance(row, str):
            # Get the metadata stored on the widget
            name, desktop, keywords = row.get_child().MYTEXT
            combined_text = f"{name} {desktop} {keywords}".lower()

            if text_to_search in combined_text:
                # Set the first match for on_keypress
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
