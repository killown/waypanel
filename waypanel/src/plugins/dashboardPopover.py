import os
import gi
from gi.repository import Gio, Gtk, Adw
from gi.repository import Gtk4LayerShell as LayerShell
from ..core.utils import Utils
from subprocess import check_output
from gi.repository import Playerctl, GLib


class PopoverDashboard(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_dashboard = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()
        self.utils = Utils(application_id="com.github.utils")
        self.left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.right_label = Gtk.Label()
        # Connect the Playerctl manager signals
        self.manager = Playerctl.PlayerManager()
        self.manager.connect('name-appeared', self.on_name_appeared)
        self.manager.connect('player-vanished', self.on_player_vanished)
        self.button = None

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

    def get_folder_location(self, folder_name):
        """
        Get the location of a specified folder for the current user.

        :param folder_name: The name of the folder to locate.
                            Possible values: "DOCUMENTS", "DOWNLOAD", "MUSIC", "PICTURES", "VIDEOS", etc.
        :return: The path to the specified folder, or None if it cannot be determined or does not exist.
        """
        folder_location = (
            check_output("xdg-user-dir {0}".format(folder_name.upper()).split())
            .decode()
            .strip()
        )
        folder_location = Gio.File.new_for_path(folder_location)
        return folder_location.get_path()

    def create_menu_popover_dashboard(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        self.menubutton_dashboard = Gtk.Button()
        self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
        return self.menubutton_dashboard

    def create_popover_dashboard(self, *_):
        # FIXME: need to reset the calendar to the right month
        # if you change for another month, the popup and popdown wont reset

        # Create a popover
        self.popover_dashboard = Gtk.Popover.new()
        self.popover_dashboard.set_has_arrow(False)
        self.popover_dashboard.connect("closed", self.popover_is_closed)
        self.popover_dashboard.connect("notify::visible", self.popover_is_open)

        # Set width and height of the popover dashboard
        self.popover_dashboard.set_size_request(400, 200)

        # Create a grid to hold the elements
        grid = Gtk.Grid()
        grid.set_row_homogeneous(True)
        grid.set_column_homogeneous(True)

        # Add elements to the left box
        left_label = Gtk.Label(label="")
        self.left_box.append(left_label)

        # Add the left box to the grid
        #grid.attach(self.left_box, 0, 0, 1, 1)

        # Create a calendar for the right side
        self.calendar = Gtk.Calendar()

        # Add the calendar to the grid
        grid.attach(self.calendar, 1, 0, 1, 1)
        self.calendar.connect("day-selected", self.on_day_selected)

        # Create a box for the right side below the calendar
        self.right_label = Gtk.Label(label="")
        self.right_box.append(self.right_label)

        # Add the right box to the grid below the calendar
        # grid.attach_next_to(self.right_box, calendar, Gtk.PositionType.BOTTOM, 1, 1)

        # Set the grid as the child of the popover
        self.popover_dashboard.set_child(grid)

        # Set the parent widget of the popover and display it
        self.popover_dashboard.set_parent(self.menubutton_dashboard)
        self.popover_dashboard.popup()
        return self.popover_dashboard

    def on_day_selected(self, calendar):
        day = calendar.get_day()
        print(f"Day selected: {day}")

    def open_popover_dashboard(self, *_):
        if self.popover_dashboard and self.popover_dashboard.is_visible():
            self.popover_dashboard.popdown()
        if self.popover_dashboard and not self.popover_dashboard.is_visible():
            self.popover_dashboard.popup()
        if not self.popover_dashboard:
            self.popover_dashboard = self.create_popover_dashboard(self.app)

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return
 
    def on_play(self, player, status, manager):
        print('player is playing: {}'.format(player.props.player_name))


    def on_metadata(self, player, metadata, manager):
        keys = metadata.keys()
        if not metadata:
            return
        if  "mpris:artUrl" in keys:
            art_url = metadata["mpris:artUrl"] 
            #image = Gtk.Image.new_from_file(art_url)
            #button = Gtk.Button()
            #button.set_child(image)

        if 'xesam:artist' in keys and 'xesam:title' in keys:
            print('{} - {}'.format(metadata['xesam:artist'], metadata['xesam:title'] ))
            #self.button = Gtk.Button()
            #self.button.set_label(metadata['xesam:title'])
            #self.left_box.append(self.button)


    def init_player(self, name):
        # choose if you want to manage the player based on the name
            player = Playerctl.Player.new_from_name(name)
            player.connect('playback-status::playing', self.on_play, self.manager)
            player.connect('metadata', self.on_metadata, self.manager)
            self.manager.manage_player(player)


    def on_name_appeared(self, manager, name):
        self.init_player(name)


    def on_player_vanished(self, manager, player):
        if self.button:
            self.button.destroy()
        print('player has exited: {}'.format(player.props.player_name))
