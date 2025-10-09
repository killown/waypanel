def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.folders",
        "name": "Folders",
        "version": "1.0.0",
        "enabled": True,
        "index": 2,
        "container": "top-panel-box-widgets-left",
        "deps": [
            "top_panel",
        ],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class PopoverFolders(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.home = self.os.path.expanduser("~")
            self.home_folders = self.os.listdir(self.home)
            self.popover_folders = None

        def on_start(self):
            self.create_menu_popover_folders()
            self.main_widget = (self.menubutton_folders, "append")

        def create_menu_popover_folders(self):
            self.layer_shell.set_keyboard_mode(
                self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
            )
            self.menubutton_folders = self.gtk.Button()
            self.menubutton_folders.connect("clicked", self.open_popover_folders)
            icon_name = self.gtk_helper.set_widget_icon_name(
                "folders",
                ["folder"],
            )
            self.menubutton_folders.set_icon_name(icon_name)
            self.menubutton_folders.add_css_class("folders-menu-button")
            self.gtk_helper.add_cursor_effect(self.menubutton_folders)

        def create_popover_folders(self):
            """
            Create and configure a popover for folders by chaining helper methods.
            """
            self._setup_popover_base()
            main_box = self._setup_search_and_listbox()
            self.popover_folders.set_child(main_box)
            self._populate_folder_list()
            self.popover_folders.popup()
            return self.popover_folders

        def _setup_popover_base(self):
            """Creates and configures the main popover object and its GIO action."""
            self.popover_folders = self.create_popover(
                parent_widget=self.menubutton_folders,
                css_class="folders-popover",
                has_arrow=False,
                closed_handler=self.popover_is_closed,
                visible_handler=self.popover_is_open,
            )
            self.popover_folders.set_autohide(True)
            show_searchbar_action = self.gio.SimpleAction.new("show_searchbar")
            show_searchbar_action.connect(
                "activate", self.on_show_searchbar_action_actived
            )
            self.obj.add_action(show_searchbar_action)

        def _setup_search_and_listbox(self):
            """Sets up the scrolled window, main box, search entry, and listbox structure."""
            self.scrolled_window = self.gtk.ScrolledWindow()
            self.scrolled_window.set_min_content_width(400)
            self.scrolled_window.set_min_content_height(600)
            self.scrolled_window.add_css_class("folders-scrolled-window")
            self.main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
            self.main_box.add_css_class("folders-main-box")
            self.searchbar = self.gtk.SearchEntry.new()
            self.searchbar.grab_focus()
            self.searchbar.connect("search_changed", self.on_search_entry_changed)
            self.searchbar.set_focus_on_click(True)
            self.searchbar.props.hexpand = True
            self.searchbar.props.vexpand = True
            self.searchbar.add_css_class("folders-search-entry")
            self.main_box.append(self.searchbar)
            self.listbox = self.gtk.ListBox.new()
            self.listbox.connect(
                "row-selected", lambda widget, row: self.open_folder(row)
            )
            self.searchbar.set_key_capture_widget(self.obj.top_panel)
            self.listbox.props.hexpand = True
            self.listbox.props.vexpand = True
            self.listbox.set_selection_mode(self.gtk.SelectionMode.SINGLE)
            self.listbox.set_show_separators(True)
            self.listbox.add_css_class("folders-listbox")
            self.main_box.append(self.scrolled_window)
            self.scrolled_window.set_child(self.listbox)
            return self.main_box

        def _create_folder_row(
            self, name, folders_path, filemanager, icon, icon_size=None
        ):
            """Creates a single ListBox row (HBox) for a folder entry with an icon and label."""
            row_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
            row_hbox.add_css_class("folders-row-hbox")
            row_hbox.MYTEXT = folders_path, filemanager
            line = self.gtk.Label.new()
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(self.gtk.Align.START)
            line.add_css_class("folders-label-from-popover")
            image = self.gtk.Image.new_from_icon_name(icon)
            image.add_css_class("folders-icon-from-popover")
            if icon_size == self.gtk.IconSize.LARGE:
                image.set_icon_size(self.gtk.IconSize.LARGE)
            else:
                image.set_icon_size(self.gtk.IconSize.INHERIT)
            image.props.margin_end = 5
            image.set_halign(self.gtk.Align.END)
            row_hbox.append(image)
            row_hbox.append(line)
            self.gtk_helper.add_cursor_effect(line)
            self.create_row_right_click(row_hbox, folders_path)
            self.create_row_middle_click(row_hbox, folders_path)
            return row_hbox

        def _populate_folder_list(self):
            """
            Populates the listbox with configured folders and all directories from the home directory,
            with non-hidden folders listed before hidden folders, ensuring no duplicates.
            """
            all_folders = self.config_handler.config_data.get("folders")
            pinned_paths = set()
            if all_folders:
                for key, folder_data in all_folders.items():
                    name = folder_data["name"]
                    folders_path = folder_data["path"]
                    filemanager = folder_data["filemanager"]
                    icon = folder_data["icon"]
                    pinned_paths.add(folders_path)
                    row_hbox = self._create_folder_row(
                        name=name,
                        folders_path=folders_path,
                        filemanager=filemanager,
                        icon=icon,
                        icon_size=self.gtk.IconSize.INHERIT,
                    )
                    self.listbox.append(row_hbox)
            visible_dirs = []
            hidden_dirs = []
            for folder in self.home_folders:
                folders_path = self.os.path.join(self.home, folder)
                if folders_path in pinned_paths:
                    continue
                if not self.os.path.isdir(folders_path):
                    continue
                if folder.startswith("."):
                    hidden_dirs.append(folder)
                else:
                    visible_dirs.append(folder)
            visible_dirs.sort()
            hidden_dirs.sort()
            sorted_home_dirs = visible_dirs + hidden_dirs
            for folder in sorted_home_dirs:
                folders_path = self.os.path.join(self.home, folder)
                icon = "nautilus"
                filemanager = "nautilus"
                row_hbox = self._create_folder_row(
                    name=folder,
                    folders_path=folders_path,
                    filemanager=filemanager,
                    icon=icon,
                    icon_size=self.gtk.IconSize.LARGE,
                )
                self.listbox.append(row_hbox)
            self.listbox.set_filter_func(self.on_filter_invalidate)

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

        def _append_menu_button_to_box(self, box, label, callback):
            """Creates a button with a label and connects a clicked signal, then appends it to the provided box."""
            button = self.gtk.Button.new_with_label(label)
            button.connect("clicked", callback)
            button.add_css_class("folders-popover-menu-items")
            box.append(button)
            return button

        def create_right_click_menu(self, row_hbox, folder_path):
            popover = self.create_popover(
                parent_widget=row_hbox,
                css_class="folders-right-click-popover",
                has_arrow=False,
            )
            box = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL)
            listbox_row = row_hbox.get_parent()
            listbox_row.add_css_class("folders-lisbox-row")
            all_folders = self.get_plugin_setting() or {}
            is_pinned = any(
                data.get("path") == folder_path for data in all_folders.values()
            )
            if is_pinned:
                self._append_menu_button_to_box(
                    box=box,
                    label="Unpin folder",
                    callback=lambda _,
                    path=folder_path,
                    row=listbox_row: self.unpin_folder(path, row),
                )
            else:
                self._append_menu_button_to_box(
                    box=box,
                    label="Pin to the top",
                    callback=lambda _,
                    path=folder_path,
                    row=listbox_row: self.pin_to_top(path, row),
                )
            self._append_menu_button_to_box(
                box=box,
                label="Move to Trash",
                callback=lambda _,
                path=folder_path,
                row=listbox_row,
                popover=popover: self.move_to_trash(path, row, popover),
            )
            popover.set_child(box)
            popover.popup()

        def move_to_trash(self, folder_path, listbox_row, popover):
            popover.popdown()
            folder_name = self.os.path.basename(folder_path)
            cmd = f"gio trash '{folder_path}'"
            self.run_cmd(cmd)
            self.logger.info(f"Moved to trash: {folder_name} at {folder_path}")
            if listbox_row and isinstance(listbox_row, self.gtk.ListBoxRow):
                parent_listbox = listbox_row.get_parent()
                if parent_listbox:
                    parent_listbox.remove(listbox_row)
                    self.logger.info(f"Removed ListBoxRow for {folder_name}")

        def pin_to_top(self, folder_path, listbox_row):
            """
            Pins a folder by moving its entry to the top of the 'folders' section
            in the configuration data, and then moves the existing ListBoxRow
            to the top of the ListBox to reflect the change visually.
            """
            folder_name = self.os.path.basename(folder_path)
            if "folders" not in self.config_handler.config_data:
                self.config_handler.config_data["folders"] = {}
            all_folders = self.config_handler.config_data.get("folders")
            new_folder_entry = {
                "name": folder_name,
                "path": folder_path,
                "filemanager": "nautilus",
                "icon": "folder-symbolic",
            }
            keys_to_delete = [
                key
                for key, data in all_folders.items()
                if data.get("path") == folder_path
            ]
            for key in keys_to_delete:
                del all_folders[key]
            temp_dict = {folder_name: new_folder_entry}
            temp_dict.update(all_folders)
            self.config_handler.config_data["folders"] = temp_dict
            self.config_handler.save_config()
            parent_listbox = listbox_row.get_parent()
            if parent_listbox and parent_listbox == self.listbox:
                parent_listbox.remove(listbox_row)
                new_row_hbox = self._create_folder_row(
                    name=new_folder_entry["name"],
                    folders_path=new_folder_entry["path"],
                    filemanager=new_folder_entry["filemanager"],
                    icon=new_folder_entry["icon"],
                    icon_size=self.gtk.IconSize.INHERIT,
                )
                new_listbox_row = self.gtk.ListBoxRow()
                new_listbox_row.set_child(new_row_hbox)
                self.listbox.insert(new_listbox_row, 0)
                new_listbox_row.show()
                self.listbox.invalidate_filter()
            self.logger.info(f"'{folder_name}' is now at the top of the list.")

        def unpin_folder(self, folder_path, listbox_row):
            """
            Unpins a folder by removing its entry from the 'folders' section in the
            configuration data, removing its current ListBoxRow, and then re-inserting
            a new row into the correct alphabetical position in the unpinned section.
            This method is fully GTK4-compliant, using iteration over containers (ListBox, Box)
            instead of deprecated methods like get_children().
            """
            folder_name = self.os.path.basename(folder_path)
            all_folders = self.config_handler.config_data.get("folders") or {}
            if not all_folders:
                self.logger.warning(
                    f"Attempted to unpin {folder_name}, but 'folders' list is empty or missing in config."
                )
                return
            key_to_delete = None
            for key, data in all_folders.items():
                if data.get("path") == folder_path:
                    key_to_delete = key
                    break
            if key_to_delete:
                del all_folders[key_to_delete]
                self.config_handler.save_config()
                self.logger.info(
                    f"'{folder_name}' unpinned from config and removed from pinned list."
                )
            else:
                self.logger.warning(
                    f"Could not find {folder_name} in pinned list to unpin."
                )
                return
            parent_listbox = listbox_row.get_parent()
            if parent_listbox and parent_listbox == self.listbox:
                parent_listbox.remove(listbox_row)
                new_unpinned_hbox = self._create_folder_row(
                    name=folder_name,
                    folders_path=folder_path,
                    filemanager="nautilus",
                    icon="nautilus",
                    icon_size=self.gtk.IconSize.LARGE,
                )
                new_listbox_row = self.gtk.ListBoxRow()
                new_listbox_row.set_child(new_unpinned_hbox)
                children = list(self.listbox)
                insert_index = -1
                pinned_count = len(all_folders)
                for i in range(pinned_count, len(children)):
                    child_row = children[i]
                    row_hbox_child = child_row.get_child()
                    if row_hbox_child:
                        hbox_children = list(row_hbox_child)
                        if len(hbox_children) > 1:
                            row_label_widget = hbox_children[1]
                            row_name = row_label_widget.get_label()
                            if folder_name.lower() < row_name.lower():
                                insert_index = i
                                break
                if insert_index == -1:
                    insert_index = len(children)
                self.listbox.insert(new_listbox_row, insert_index)
                self.listbox.invalidate_filter()
            self.logger.info(
                f"'{folder_name}' is now unpinned and returned to the main list."
            )

        def create_row_middle_click(self, row_hbox, folder_path):
            create_gesture = self.plugins["gestures_setup"].create_gesture
            create_gesture(
                row_hbox,
                2,
                lambda _, folder_path=folder_path: self.open_baobab(folder_path),
            )

        def open_kitty(self, folder_path):
            cmd = "kitty --working-directory={0}".format(folder_path)
            self.run_cmd(cmd)

        def open_baobab(self, folder_path):
            cmd = "baobab {0}".format(folder_path)
            self.run_cmd(cmd)

        def open_folder(self, x):
            if not x:
                return
            path_tuple = x.get_child().MYTEXT
            if isinstance(path_tuple, tuple):
                path, filemanager = path_tuple
            else:
                path, filemanager = path_tuple.split()
            cmd = f"{filemanager} {path}"
            self.run_cmd(cmd)
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
            self.searchbar.set_search_mode(True)

        def search_entry_grab_focus(self):
            self.searchentry.grab_focus()
            self.logger.info(
                "search entry is focused: {}".format(self.searchentry.is_focus())
            )

        def on_search_entry_changed(self, searchentry):
            searchentry.grab_focus()
            self.listbox.invalidate_filter()

        def on_filter_invalidate(self, row):
            try:
                if not isinstance(row, self.gtk.ListBoxRow):
                    self.logger.error(
                        error=TypeError(
                            f"Invalid row type: {type(row).__name__}. Expected self.gtk.ListBoxRow."
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
                row_text_data = child.MYTEXT
                if isinstance(row_text_data, tuple):
                    row_text = row_text_data[0]
                else:
                    row_text = str(row_text_data)
                if not isinstance(row_text, str):
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
                self.logger.error(
                    f"Unexpected error occurred in on_filter_invalidate. {e}"
                )

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

    return PopoverFolders
