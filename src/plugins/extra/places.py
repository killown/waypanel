import os
from subprocess import Popen
from gi.repository import Gio, Gtk  # pyright: ignore
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True
DEPS = ["top_panel"]


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
        icon_name = self.gtk_helper.set_widget_icon_name(
            "places",
            ["folder"],
        )
        self.menubutton_folders.set_icon_name(icon_name)
        self.menubutton_folders.add_css_class("places-menu-button")
        self.gtk_helper.add_cursor_effect(self.menubutton_folders)

    def create_popover_folders(self):
        """
        Create and configure a popover for folders.
        """
        self.popover_folders = Gtk.Popover.new()
        self.popover_folders.set_has_arrow(False)
        self.popover_folders.set_autohide(True)
        self.popover_folders.connect("closed", self.popover_is_closed)
        self.popover_folders.connect("notify::visible", self.popover_is_open)
        self.popover_folders.add_css_class("places-popover")
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.obj.add_action(show_searchbar_action)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(400)
        self.scrolled_window.set_min_content_height(600)
        self.scrolled_window.add_css_class("places-scrolled-window")
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.main_box.add_css_class("places-main-box")
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.props.hexpand = True
        self.searchbar.props.vexpand = True
        self.searchbar.add_css_class("places-search-entry")
        self.main_box.append(self.searchbar)
        self.listbox = Gtk.ListBox.new()
        self.listbox.connect("row-selected", lambda widget, row: self.open_folder(row))
        self.searchbar.set_key_capture_widget(self.obj.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.listbox.add_css_class("places-listbox")
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)
        self.popover_folders.set_child(self.main_box)
        all_folders = self.config_handler.config_data.get("folders")
        if all_folders:
            for folder in all_folders.items():
                name = folder[1]["name"]
                folders_path = folder[1]["path"]
                filemanager = folder[1]["filemanager"]
                icon = folder[1]["icon"]
                row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
                row_hbox.add_css_class("places-row-hbox")
                row_hbox.MYTEXT = folders_path, filemanager  # pyright: ignore
                self.listbox.append(row_hbox)
                line = Gtk.Label.new()
                line.set_label(name)
                line.props.margin_start = 5
                line.props.hexpand = True
                line.set_halign(Gtk.Align.START)
                line.add_css_class("places-label-from-popover")
                image = Gtk.Image.new_from_icon_name(icon)
                image.set_icon_size(Gtk.IconSize.INHERIT)
                image.props.margin_end = 5
                image.set_halign(Gtk.Align.END)
                image.add_css_class("places-icon-from-popover")
                row_hbox.append(image)
                row_hbox.append(line)
                self.create_row_right_click(row_hbox, folders_path)
                self.create_row_middle_click(row_hbox, folders_path)
                self.gtk_helper.add_cursor_effect(line)
        for folder in self.home_folders:
            folders_path = os.path.join(self.home, folder)
            icon = "nautilus"
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.add_css_class("places-row-hbox")
            row_hbox.MYTEXT = folders_path, "nautilus"  # pyright: ignore
            self.listbox.append(row_hbox)
            line = Gtk.Label.new()
            line.add_css_class("places-label-from-popover")
            line.set_label(folder)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            image = Gtk.Image.new_from_icon_name(icon)
            image.add_css_class("places-icon-from-popover")
            image.set_icon_size(Gtk.IconSize.LARGE)
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)
            row_hbox.append(image)
            row_hbox.append(line)
            self.create_row_right_click(row_hbox, folders_path)
            self.create_row_middle_click(row_hbox, folders_path)
            self.gtk_helper.add_cursor_effect(line)
        self.listbox.set_filter_func(self.on_filter_invalidate)
        self.popover_folders.set_parent(self.menubutton_folders)
        self.popover_folders.popup()
        return self.popover_folders

    def create_row_right_click(self, row_hbox, folder_path):
        create_gesture = self.plugins["gestures_setup"].create_gesture
        create_gesture(
            row_hbox,
            3,
            lambda _,
            row_hbox=row_hbox,
            folder_path=folder_path: self.create_right_click_menu(
                row_hbox, folder_path
            ),
        )

    def create_right_click_menu(self, row_hbox, folder_path):
        popover = Gtk.Popover()
        popover.set_parent(row_hbox)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        button = Gtk.Button.new_with_label("Pin to the top")
        button.connect("clicked", lambda _, path=folder_path: self.pin_to_top(path))
        box.append(button)
        popover.set_child(box)
        popover.popup()

    def pin_to_top(self, folder_path):
        folder_name = os.path.basename(folder_path)
        if "folders" not in self.config_handler.config_data:
            self.config_handler.config_data["folders"] = {}
        all_folders = self.config_handler.config_data.get("folders")
        for key, value in all_folders.items():  # pyright: ignore
            if value.get("path") == folder_path:
                self.logger.info(f"{folder_path} is already pinned.")
                return
        new_folder_entry = {
            "name": folder_name,
            "path": folder_path,
            "filemanager": "nautilus",
            "icon": "folder-symbolic",
        }
        self.config_handler.config_data["folders"][folder_name] = new_folder_entry
        self.config_handler.save_config()
        self.config_handler.reload_config()
        self.logger.info(f"Pinned folder: {folder_name} to config.toml")

    def create_row_middle_click(self, row_hbox, folder_path):
        create_gesture = self.plugins["gestures_setup"].create_gesture
        create_gesture(
            row_hbox,
            2,
            lambda _, folder_path=folder_path: self.open_baobab(folder_path),
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
        self.searchbar.set_search_mode(True)  # pyright: ignore

    def search_entry_grab_focus(self):
        self.searchentry.grab_focus()  # pyright: ignore
        self.logger.info(
            "search entry is focused: {}".format(self.searchentry.is_focus())  # pyright: ignore
        )

    def on_search_entry_changed(self, searchentry):
        searchentry.grab_focus()
        self.listbox.invalidate_filter()

    def on_filter_invalidate(self, row):
        try:
            if not isinstance(row, Gtk.ListBoxRow):
                self.logger.error(
                    error=TypeError(
                        f"Invalid row type: {type(row).__name__}. Expected Gtk.ListBoxRow."
                    ),
                    message="Invalid row type encountered in on_filter_invalidate.",
                    level="warning",
                )
                return False
            child = row.get_child()
            if not child or not hasattr(child, "MYTEXT"):
                self.logger.error(
                    message="Row child is missing the required 'MYTEXT' attribute.",
                )
                return False
            row_text = child.MYTEXT  # pyright: ignore
            if not isinstance(row_text, str):
                if isinstance(row_text, tuple):
                    row_text = " ".join(str(item) for item in row_text)
                    child.MYTEXT = row_text  # pyright: ignore
                else:
                    self.logger.error(
                        error=TypeError(
                            f"Invalid row text type: {type(row_text).__name__}. Expected str."
                        ),
                        message=f"Invalid row text encountered: {row_text}.",
                        level="warning",
                    )
                    return False
            text_to_search = self.searchbar.get_text().strip().lower()
            return text_to_search in row_text.lower()
        except Exception as e:
            self.logger.error(f"Unexpected error occurred in on_filter_invalidate. {e}")

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
