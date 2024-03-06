import os
import random
import gi
from gi.repository import Gio, Gtk, Adw
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen
from ..core.utils import Utils
import toml


class PopoverDashboard(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_dashboard = None
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
        self.topbar_dashboard_config = os.path.join(
            self.config_path, "topbar-launcher.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}

    def create_menu_popover_dashboard(self, obj, app, *_):
        self.top_panel = obj.top_panel
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        self.app = app
        self.menubutton_dashboard = Gtk.Button()
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        self.menubutton_dashboard.set_icon_name("start-here-archlinux")
        return self.menubutton_dashboard

    def create_popover_dashboard(self, *_):
        # Create a popover
        self.popover_dashboard = Gtk.Popover.new()

        # Set width and height of the popover dashboard
        self.popover_dashboard.set_size_request(
            600, 400
        )  # Set width to 600 and height to 400

        # Create a grid to hold the elements
        grid = Gtk.Grid()
        grid.set_row_homogeneous(True)
        grid.set_column_homogeneous(True)

        # Create a box for the left side
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Add elements to the left box
        left_label = Gtk.Label(label="")
        left_box.append(left_label)

        # Add the left box to the grid
        grid.attach(left_box, 0, 0, 1, 2)  # Set row span to 2 for twice the height

        # Create a calendar for the right side
        calendar = Gtk.Calendar()

        # Add the calendar to the grid
        grid.attach(calendar, 1, 0, 1, 1)

        # Create a box for the right side below the calendar
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Add elements to the right box
        right_label = Gtk.Label(label="")
        right_box.append(right_label)

        # Add the right box to the grid below the calendar
        grid.attach_next_to(right_box, calendar, Gtk.PositionType.BOTTOM, 1, 1)

        # Set the grid as the child of the popover
        self.popover_dashboard.set_child(grid)

        # Set the parent widget of the popover and display it
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()

        return self.popover_dashboard

    def run_app_from_dashboard(self, x):
        selected_text, filename = x.get_child().MYTEXT
        cmd = "gtk-launch {}".format(filename)
        self.utils.run_app(cmd)
        self.popover_dashboard.popdown()

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()

        self.create_popover_dashboard(self.app)

    def popover_is_closed(self, *_):
        return

    def popover_dashboard_is_closed(self, *_):
        return

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar
