import os
from subprocess import Popen

import gi
from gi.repository import Gio, Gtk

from src.plugins.core._base import BasePlugin


# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


# set the plugin location, order, position
def get_plugin_placement(panel_instance):
    position = "top-panel-box-widgets-left"
    order = 3
    return position, order


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        places = PopoverFolders(panel_instance)
        places.create_menu_popover_folders()
        places.set_main_widget()
        return places


class PopoverFolders(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.home = os.path.expanduser("~")
        self.home_folders = os.listdir(self.home)
        self.popover_folders = None

    def set_main_widget(self):
        self.main_widget = (self.menubutton_folders, "append")

    def create_menu_popover_folders(self):
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
        )
        self.menubutton_folders = Gtk.Button()
        self.menubutton_folders.connect("clicked", self.open_popover_folders)
        icon_name = self.utils.set_widget_icon_name(
            "places",
            ["folder"],
        )
        self.menubutton_folders.set_icon_name(icon_name)
        self.menubutton_folders.add_css_class("places-menu-button")
        self.utils.add_cursor_effect(self.menubutton_folders)

    def create_popover_folders(self):
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
        self.obj.add_action(show_searchbar_action)

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
        self.searchbar.set_key_capture_widget(self.obj.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)

        # Configure popover with main box
        self.popover_folders.set_child(self.main_box)

        all_folders = self.config["folders"]
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
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            # Create image for the bookmark icon
            image = Gtk.Image.new_from_icon_name(icon)
            image.set_icon_size(Gtk.IconSize.INHERIT)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)

            # Add label and image to the bookmark box
            row_hbox.append(image)
            row_hbox.append(line)
            line.add_css_class("places-label-from-popover")
            image.add_css_class("places-icon-from-popover")
            self.create_row_right_click(row_hbox, folders_path)
            self.create_row_middle_click(row_hbox, folders_path)
            self.utils.add_cursor_effect(line)

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
            line.add_css_class("places-label-from-popover")
            line.set_label(folder)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            # Create image for the bookmark icon
            image = Gtk.Image.new_from_icon_name(icon)
            image.add_css_class("places-icon-from-popover")
            image.set_icon_size(Gtk.IconSize.LARGE)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)

            # Add label and image to the bookmark box
            row_hbox.append(image)
            row_hbox.append(line)
            self.create_row_right_click(row_hbox, folders_path)
            self.create_row_middle_click(row_hbox, folders_path)

            self.utils.add_cursor_effect(line)

        # Configure listbox filter function
        self.listbox.set_filter_func(self.on_filter_invalidate)

        # Set the parent and display the popover
        self.popover_folders.set_parent(self.menubutton_folders)
        self.popover_folders.popup()

        return self.popover_folders

    def create_row_right_click(self, row_hbox, folder_path):
        create_gesture = self.plugins["gestures_setup"].create_gesture
        create_gesture(
            row_hbox,
            3,
            lambda _, folder_path=folder_path: self.open_baobab(folder_path),
        )

    def create_row_middle_click(self, row_hbox, folder_path):
        create_gesture = self.plugins["gestures_setup"].create_gesture
        create_gesture(
            row_hbox,
            2,
            lambda _, folder_path=folder_path: self.open_kitty(folder_path),
        )

    def open_kitty(self, folder_path):
        cmd = "kitty --working-directory={0}".format(folder_path).split()
        Popen(cmd)

    def open_baobab(self, folder_path):
        cmd = "baobab {0}".format(folder_path).split()
        Popen(cmd)

    def open_folder(self, x):
        if not x:
            return
        folder, filemanager = x.get_child().MYTEXT.split()
        path = os.path.join(self.home, folder)
        cmd = "{0} {1}".format(filemanager, path).split()
        Popen(cmd)
        if self.popover_folders:
            self.popover_folders.popdown()

    def open_popover_folders(self, *_):
        if self.popover_folders and self.popover_folders.is_visible():
            self.popover_folders.popdown()
        if self.popover_folders and not self.popover_folders.is_visible():
            self.listbox.unselect_all()
            self.popover_folders.popup()
        if not self.popover_folders:
            self.popover_folders = self.create_popover_folders()

    def popover_is_open(self, *_):
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
        )

    def popover_is_closed(self, *_):
        self.layer_shell.set_keyboard_mode(
            self.obj.top_panel, self.layer_shell.KeyboardMode.NONE
        )

    def on_show_searchbar_action_actived(self, action, parameter):
        self.searchbar.set_search_mode(
            True
        )  # Ctrl+F To Active show_searchbar and show searchbar

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()
        self.logger.info(
            "search entry is focused: {}".format(self.searchentry.is_focus())
        )

    def on_search_entry_changed(self, searchentry):
        """The filter_func will be called for each row after the call,
        and it will continue to be called each time a row changes (via [method`Gtk`.ListBoxRow.changed])
        or when [method`Gtk`.ListBox.invalidate_filter] is called."""
        searchentry.grab_focus()
        # run filter (run self.on_filter_invalidate look at self.listbox.set_filter_func(self.on_filter_invalidate) )
        self.listbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        """
        Filter function for the Gtk.ListBox.
        Args:
            row (Gtk.ListBoxRow): The row to validate.
        Returns:
            bool: True if the row matches the search criteria, False otherwise.
        """
        try:
            # Ensure the input is a Gtk.ListBoxRow
            if not isinstance(row, Gtk.ListBoxRow):
                self.log_error(
                    error=TypeError(
                        f"Invalid row type: {type(row).__name__}. Expected Gtk.ListBoxRow."
                    ),
                    message="Invalid row type encountered in on_filter_invalidate.",
                    level="warning",
                )
                return False

            # Get the child widget of the row
            child = row.get_child()
            if not child or not hasattr(child, "MYTEXT"):
                self.log_error(
                    error=ValueError("Row child does not have 'MYTEXT' attribute."),
                    message="Row child is missing the required 'MYTEXT' attribute.",
                    level="warning",
                )
                return False

            # Extract the text from the child widget
            row_text = child.MYTEXT

            # Ensure MYTEXT is a string
            if not isinstance(row_text, str):
                # If MYTEXT is a tuple, convert it to a string
                if isinstance(row_text, tuple):
                    row_text = " ".join(str(item) for item in row_text)
                    child.MYTEXT = row_text  # Update MYTEXT to avoid future issues
                else:
                    self.log_error(
                        error=TypeError(
                            f"Invalid row text type: {type(row_text).__name__}. Expected str."
                        ),
                        message=f"Invalid row text encountered: {row_text}.",
                        level="warning",
                    )
                    return False

            # Perform case-insensitive search
            text_to_search = self.searchbar.get_text().strip().lower()
            return text_to_search in row_text.lower()

        except Exception as e:
            self.log_error(
                message="Unexpected error occurred in on_filter_invalidate.",
            )
            return False

    def about(self):
        """Provides a user interface for managing and controlling system audio devices and volume settings."""
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin creates a popover-based user interface for managing audio devices.
        It listens for system events to dynamically update its state and UI.

        Its core logic is centered on **state synchronization, event-driven updates, and dynamic UI manipulation**:

        1.  **Event Subscription**: It subscribes to a system-wide event channel to receive
            notifications about changes in audio output devices and volume levels. This allows
            the plugin to react in real time to external changes.
        2.  **State Management**: It maintains an internal state that reflects the current
            audio configuration, including the active output device, volume level, and mute status.
            This state is kept synchronized with the system via event notifications.
        3.  **Dynamic UI**: The plugin dynamically generates and updates UI elements within
            a popover, such as a volume slider and a list of available audio devices. The UI is
            rebuilt or modified in real time to match the changes in the system's audio state.
        4.  **User Interaction**: It provides interactive elements that allow the user to
            change the volume, mute/unmute audio, and switch between different audio output devices.
            These user actions trigger updates to both the UI and the underlying system state.
        """
        return self.code_explanation.__doc__
