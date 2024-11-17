import os
import random
import gi
from gi.repository import Gio, Gtk, Adw
from gi.repository import Gtk4LayerShell as LayerShell
from subprocess import Popen, check_output
import subprocess
from ..core.utils import Utils
import threading
from subprocess import check_output, PIPE


class MenuClipboard(Gtk.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_clipboard = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()
        self.utils = Utils(application_id="com.github.utils")
        self.find_text_using_button = {}
        self.row_content = None
        self.listbox = None
        self.clipboard_cmd = "cliphist"
        self.clipboard_cmd_exist = self.command_exists("cliphist")

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

    def clear_clipboard(self, text_list):
        # Clear the clipboard
        echo = Popen(("echo", text_list), stdout=subprocess.PIPE)
        echo.wait()
        Popen(("cliphist", "delete"), stdin=echo.stdout)

    def update_clipboard_list(self):
        # Clear the existing list
        self.listbox.remove_all()

        # Repopulate the list with updated clipboard history
        clipboard_history = "\n"
        if self.clipboard_cmd_exist:
            clipboard_history = ''
            try:
                clipboard_history = (
                check_output("cliphist list".split())
                .decode("latin-1")
                .encode("utf-8")
                .decode()
            )
            except Exception as e:
                print(e)

        clipboard_history = clipboard_history.split("\n")
        for i in clipboard_history:
            if not i:
                continue
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            image_button = Gtk.Button()
            image_button.set_icon_name("edit-paste")
            image_button.connect("clicked", self.cliphist_delete_selected)
            spacer = Gtk.Label(label="    ")
            row_hbox.append(image_button)
            row_hbox.append(spacer)
            row_hbox.MYTEXT = i
            self.listbox.append(row_hbox)
            line = Gtk.Label.new()
            line.set_markup('<span font="DejaVu Sans Mono">{}</span>'.format(i))
            #line.set_label(i)
            line.props.margin_end = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            row_hbox.append(line)
            self.find_text_using_button[image_button] = line

    def create_popover_menu_clipboard(self, obj, app, *_):
        self.top_panel = obj.top_panel
        LayerShell.set_keyboard_mode(self.top_panel, LayerShell.KeyboardMode.ON_DEMAND)
        self.app = app
        self.menubutton_clipboard = Gtk.Button.new()
        self.menubutton_clipboard.connect("clicked", self.open_popover_clipboard)
        self.menubutton_clipboard.set_icon_name("edit-paste")
        obj.top_panel_box_systray.append(self.menubutton_clipboard)

    def create_popover_clipboard(self, *_):
        # Create a popover
        self.popover_clipboard = Gtk.Popover.new()  # Create a new popover menu
        self.popover_clipboard.set_has_arrow(False)
        self.popover_clipboard.connect("closed", self.popover_is_closed)
        self.popover_clipboard.connect("notify::visible", self.popover_is_open)
        show_searchbar_action = Gio.SimpleAction.new("show_searchbar")
        show_searchbar_action.connect("activate", self.on_show_searchbar_action_actived)
        self.app.add_action(show_searchbar_action)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_min_content_width(600)
        self.scrolled_window.set_min_content_height(600)
        self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.searchbar = Gtk.SearchEntry.new()
        self.searchbar.grab_focus()
        self.searchbar.connect("search_changed", self.on_search_entry_changed)
        self.searchbar.set_focus_on_click(True)
        self.searchbar.props.hexpand = True
        self.searchbar.props.vexpand = True

        self.main_box.append(self.searchbar)
        self.button_clear = Gtk.Button()
        self.button_clear.add_css_class("clipboard_clear_button")
        if self.clipboard_cmd_exist:
            self.button_clear.set_label("Clear")
        else:
            self.button_clear.set_label(
                "Enable clipboard by installing {0} and autostart wl-paste --watch cliphist store".format(
                    self.clipboard_cmd.capitalize()
                )
            )
        self.button_clear.connect("clicked", self.clear_cliphist)
        self.button_clear.add_css_class("button_clear_from_clipboard")
        self.main_box.append(self.button_clear)
        self.listbox = Gtk.ListBox.new()
        self.listbox.connect(
            "row-selected", lambda widget, row: self.wl_copy_clipboard(row)
        )
        self.searchbar.set_key_capture_widget(self.top_panel)
        self.listbox.props.hexpand = True
        self.listbox.props.vexpand = True
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.main_box.append(self.scrolled_window)
        self.scrolled_window.set_child(self.listbox)
        self.popover_clipboard.set_child(self.main_box)
        clipboard_history = "\n"
        if self.clipboard_cmd_exist:
            clipboard_history = (
                check_output("cliphist list".split())
                .decode("latin-1")
                .encode("utf-8")
                .decode()
            )
        clipboard_history = clipboard_history.split("\n")
        for i in clipboard_history:
            if not self.clipboard_cmd_exist:
                continue
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            image_button = Gtk.Button()
            image_button.set_icon_name("edit-delete-remove")
            image_button.connect("clicked", lambda i: self.cliphist_delete_selected(i))
            spacer = Gtk.Label(label="    ")
            row_hbox.append(image_button)
            row_hbox.append(spacer)
            row_hbox.MYTEXT = i
            self.listbox.append(row_hbox)
            line = Gtk.Label.new()
            line.set_markup('<span font="DejaVu Sans Mono">{}</span>'.format(i))
            #line.set_label(i)
            line.props.margin_end = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)
            row_hbox.append(line)
            self.find_text_using_button[image_button] = line

        self.listbox.set_filter_func(self.on_filter_invalidate)
        # Create a menu button
        self.popover_clipboard.set_parent(self.menubutton_clipboard)
        self.popover_clipboard.popup()
        return self.popover_clipboard

    def wl_copy_clipboard(self, x, *_):
        selected_text = x.get_child().MYTEXT
        echo = Popen(("echo", selected_text), stdout=subprocess.PIPE)
        echo.wait()
        selected_text = check_output(("cliphist", "decode"), stdin=echo.stdout).decode()
        # not gonna use buggy pyperclip
        Popen(["wl-copy", selected_text])
        self.popover_clipboard.popdown()

    def clear_cliphist(self, *_):
        box = self.listbox
        counter = 0
        while True:
            b = box.get_row_at_index(counter)
            if not b:
                break
            text = b.get_child().MYTEXT
            counter += 1
            search = self.searchbar.get_text().strip()
            if search.lower() in text.lower() and isinstance(text, str):
                # huge lists will break the output
                try:
                    command_thread = threading.Thread(
                        target=self.clear_clipboard, args=(text,)
                    )
                    command_thread.start()
                except Exception as e:
                    print(e)

    def command_exists(self, command):
        try:
            subprocess.call([command])
            return True
        except Exception as e:
            print(e)
            return False

    def cliphist_delete_selected(self, button):
        button = [i for i in self.find_text_using_button if button == i]
        print(button)
        if button:
            button = button[0]
        else:
            print("clipboard del button not found")
            return
        label = self.find_text_using_button[button]
        text = label.get_text()
        label.set_label("")
        echo = Popen(("echo", text), stdout=subprocess.PIPE)
        echo.wait()
        Popen(("cliphist", "delete"), stdin=echo.stdout)
        self.update_clipboard_list()

    def run_app_from_launcher(self, x):
        selected_text, filename = x.get_child().MYTEXT
        cmd = "gtk-launch {}".format(filename)
        self.utils.run_app(cmd)
        self.popover_launcher.popdown()

    def open_popover_clipboard(self, *_):
        if self.popover_clipboard and self.popover_clipboard.is_visible():
            self.popover_clipboard.popdown()
        if self.popover_clipboard and not self.popover_clipboard.is_visible():
            print(self.clipboard_cmd_exist)
            self.update_clipboard_list()
            self.popover_clipboard.popup()
        if not self.popover_clipboard:
            self.popover_clipboard = self.create_popover_clipboard(self.app)

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
            row = row.get_child().MYTEXT
        row = row.lower().strip()
        if (
            text_to_search.lower() in row
        ):  # == row_hbox.MYTEXT (Gtk.ListBoxRow===>get_child()===>row_hbox.MYTEXT)
            return True  # if True Show row
        return False
