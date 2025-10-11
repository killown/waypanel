def get_plugin_metadata(_):
    about = """
            Provides a user interface for quickly finding and opening
            files from a configured directory, using an extension-based editor mapping.
            """
    return {
        "id": "org.waypanel.plugin.open_with_editor",
        "name": "Open with editor",
        "version": "1.0.0",
        "enabled": True,
        "index": 3,
        "container": "top-panel-box-widgets-left",
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    import fnmatch

    class OpenWithEditor(BasePlugin):
        """
        A plugin to quickly search and open files from a configured directory,
        using a specified editor based on file extension.
        Left-click, middle-click, and right-click can open the file with
        the first, second, or third configured editor, respectively.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            raw_config_maps = self.get_plugin_setting()
            if not raw_config_maps:
                raw_config_maps = self.get_plugin_setting(
                    ["directories", "nvim"], "~/.config/nvim"
                )
            else:
                raw_config_maps = self.get_plugin_setting("directories")
            self.config_maps = {}
            for dir_name, dir_path in raw_config_maps.items():
                self.config_maps[dir_name] = self.os.path.expanduser(dir_path)
            self.active_dir_name = next(iter(self.config_maps))
            self.config_dir = self.config_maps[self.active_dir_name]
            self.listbox_widgets = {}
            self.searchbar_widgets = {}
            self.cached_files = {}
            self.active_listbox = None
            self.active_searchbar = None
            self.editor_extensions = self.get_plugin_setting(["extensions"])
            if not self.editor_extensions:
                self.editor_extensions = {
                    "json": ["code", "nvim"],
                    "toml": ["code", "nvim"],
                    "yml": ["code", "nvim"],
                    "yaml": ["code", "nvim"],
                    "conf": ["code", "gedit"],
                    "ini": ["code", "gedit"],
                    "cfg": ["code", "gedit"],
                    "xml": ["code", "nvim"],
                    "txt": ["gedit", "code"],
                    "log": ["gedit", "nvim"],
                    "md": ["code", "gedit"],
                    "css": ["code", "nvim"],
                    "scss": ["code", "nvim"],
                    "html": ["code", "nvim"],
                    "js": ["code", "nvim"],
                    "ts": ["code", "nvim"],
                    "py": ["nvim", "code"],
                    "lua": ["nvim", "code"],
                    "sh": ["nvim", "code"],
                    "go": ["nvim", "code"],
                    "rs": ["nvim", "code"],
                    "rb": ["nvim", "code"],
                    "php": ["nvim", "code"],
                    "java": ["nvim", "code"],
                    "c": ["nvim", "code"],
                    "cpp": ["nvim", "code"],
                    "h": ["nvim", "code"],
                }
                self.logger.info(
                    "Using default recommended editor mappings as none were configured by the user."
                )
            self.default_editors = ["nvim", "code", "gedit", "subl", "vscode", "nano"]
            self.extension_to_icon = {
                "py": "text-x-python-symbolic",
                "js": "text-x-javascript-symbolic",
                "ts": "text-x-typescript-symbolic",
                "html": "text-html-symbolic",
                "css": "text-css-symbolic",
                "scss": "text-css-symbolic",
                "json": "text-json-symbolic",
                "xml": "text-xml-symbolic",
                "sh": "application-x-shellscript-symbolic",
                "lua": "text-x-lua-symbolic",
                "java": "text-x-java-symbolic",
                "c": "text-x-csrc-symbolic",
                "cpp": "text-x-c++src-symbolic",
                "h": "text-x-chdr-symbolic",
                "go": "text-x-go-symbolic",
                "rs": "text-x-rust-symbolic",
                "rb": "text-x-ruby-symbolic",
                "php": "text-x-php-symbolic",
                "yml": "text-x-yaml-symbolic",
                "yaml": "text-x-yaml-symbolic",
                "toml": "application-toml",
                "md": "text-markdown-symbolic",
                "lock": "text-x-generic-symbolic",
                "conf": "text-x-generic-symbolic",
                "ini": "text-x-generic-symbolic",
                "cfg": "text-x-generic-symbolic",
                "git": "folder-git-symbolic",
                "txt": "text-x-generic-symbolic",
                "pdf": "application-pdf-symbolic",
                "log": "text-x-generic-symbolic",
                "csv": "text-csv-symbolic",
                "data": "application-x-generic-symbolic",
            }
            self.popover_openwitheditor = None
            self.terminal_emulators = [
                "kitty",
                "alacritty",
                "gnome-terminal",
                "terminator",
                "tilix",
                "xterm",
                "urxvt",
                "wezterm",
                "lxterminal",
                "xfce4-terminal",
                "st",
                "rxvt",
            ]

        def on_start(self):
            self.create_menu_popover_openwitheditor()
            self.set_main_widget()

        def set_main_widget(self):
            self.main_widget = (self.menubutton_openwitheditor, "append")

        def create_menu_popover_openwitheditor(self):
            self.layer_shell.set_keyboard_mode(
                self.obj.top_panel, self.layer_shell.KeyboardMode.ON_DEMAND
            )
            self.menubutton_openwitheditor = self.gtk.Button()
            self.menubutton_openwitheditor.connect(
                "clicked", self.open_popover_openwitheditor
            )
            icon_name = self.gtk_helper.set_widget_icon_name(
                "code-exploration",
                ["code", "com.visualstudio.code.oss"],
            )
            self.menubutton_openwitheditor.set_icon_name(icon_name)
            self.menubutton_openwitheditor.add_css_class("openwitheditor-menu-button")
            self.gtk_helper.add_cursor_effect(self.menubutton_openwitheditor)

        def create_popover_openwitheditor(self):
            """
            Create and configure a popover for files, now with tabs.
            """
            self._setup_popover_base()
            main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
            main_box.add_css_class("openwitheditor-main-box")
            self.switcher, self.stack = self._setup_tabbed_ui()  # pyright: ignore
            main_box.append(self.switcher)
            main_box.append(self.stack)
            self.popover_openwitheditor.set_child(main_box)  # pyright: ignore
            self.active_listbox = self.listbox_widgets[self.active_dir_name]
            self.active_searchbar = self.searchbar_widgets[self.active_dir_name]
            self._populate_listbox(
                self.active_listbox, self.config_dir, self.active_searchbar
            )
            self.active_searchbar.grab_focus()
            self.popover_openwitheditor.popup()  # pyright: ignore
            return self.popover_openwitheditor

        def on_listbox_row_activated(self, listbox, row):
            """
            Handler for the 'row-activated' signal (Enter key press or double-click).
            Opens the selected file using the default (index 0) editor.
            """
            row_hbox = row.get_child()
            if row_hbox and hasattr(row_hbox, "MYTEXT"):
                file_path = row_hbox.MYTEXT
                self.open_file_in_editor(file_path=file_path, editor_index=0)
            else:
                self.logger.warning("Activated row does not contain a valid file path.")

        def _setup_tabbed_ui(self):
            """
            Creates the Gtk.StackSwitcher and Gtk.Stack for the tabbed interface.
            """
            self.stack = self.gtk.Stack.new()
            self.stack.props.hexpand = True
            self.stack.props.vexpand = True
            self.stack.set_transition_type(
                self.gtk.StackTransitionType.SLIDE_LEFT_RIGHT
            )
            self.stack.add_css_class("openwitheditor-stack")
            self.switcher = self.gtk.StackSwitcher.new()
            self.switcher.set_stack(self.stack)
            self.switcher.add_css_class("openwitheditor-stack-switcher")
            for dir_name, dir_path in self.config_maps.items():
                page_box, searchbar, listbox = self._create_tab_page(dir_name)
                self.stack.add_titled(page_box, dir_name, dir_name)
                self.listbox_widgets[dir_name] = listbox
                self.searchbar_widgets[dir_name] = searchbar
            self.stack.connect("notify::visible-child", self.on_tab_switched)
            return self.switcher, self.stack

        def _create_tab_page(self, dir_name):
            """Creates the Gtk.Box content for a single tab (searchbar + listbox)."""
            page_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
            page_box.add_css_class("openwitheditor-page-box")
            page_box.props.hexpand = True
            page_box.props.vexpand = True
            searchbar = self.gtk.SearchEntry.new()
            searchbar.connect("search_changed", self.on_search_entry_changed)
            searchbar.set_focus_on_click(True)
            searchbar.grab_focus()
            searchbar.props.hexpand = True
            searchbar.props.vexpand = False
            searchbar.add_css_class("openwitheditor-search-entry")
            page_box.append(searchbar)
            listbox = self.gtk.ListBox.new()
            listbox.connect("row-activated", self.on_listbox_row_activated)
            listbox.set_can_focus(True)
            listbox.set_focusable(True)
            listbox.props.hexpand = True
            listbox.props.vexpand = True
            listbox.set_selection_mode(self.gtk.SelectionMode.SINGLE)
            listbox.set_show_separators(True)
            listbox.add_css_class("openwitheditor-listbox")
            self.scrolled_window = self.gtk.ScrolledWindow()
            self.scrolled_window.set_min_content_width(800)
            self.scrolled_window.set_min_content_height(600)
            self.scrolled_window.add_css_class("openwitheditor-scrolled-window")
            self.scrolled_window.set_child(listbox)
            page_box.append(self.scrolled_window)
            return page_box, searchbar, listbox

        def on_tab_switched(self, stack, pspec):
            """Handler for when a tab is switched in the Gtk.Stack (for lazy loading)."""
            new_dir_name = stack.get_visible_child_name()
            self.active_dir_name = new_dir_name
            self.config_dir = self.config_maps[new_dir_name]
            self.active_listbox = self.listbox_widgets[new_dir_name]
            self.active_searchbar = self.searchbar_widgets[new_dir_name]
            if self.active_listbox.get_row_at_index(0) is None:
                self._populate_listbox(
                    self.active_listbox, self.config_dir, self.active_searchbar
                )
            self.active_searchbar.grab_focus()

        def _setup_popover_base(self):
            """Creates and configures the main popover object and its GIO action."""
            self.popover_openwitheditor = self.create_popover(
                parent_widget=self.menubutton_openwitheditor,
                css_class="openwitheditor-popover",
                has_arrow=False,
                closed_handler=self.popover_is_closed,
                visible_handler=self.popover_is_open,
            )
            self.popover_openwitheditor.set_autohide(True)
            show_searchbar_action = self.gio.SimpleAction.new("show_searchbar")
            show_searchbar_action.connect(
                "activate", self.on_show_searchbar_action_actived
            )
            self.obj.add_action(show_searchbar_action)

        def _load_gitignore_patterns(self, directory):
            """Loads .gitignore patterns from the specified directory."""
            gitignore_path = self.os.path.join(directory, ".gitignore")
            patterns = []
            if self.os.path.exists(gitignore_path):
                try:
                    with open(gitignore_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                patterns.append(line)
                except Exception as e:
                    self.logger.warning(
                        f"Error reading .gitignore at {gitignore_path}: {e}"
                    )
            return patterns

        def _is_ignored(self, relative_path, ignore_patterns):
            """Checks if a relative path matches any of the .gitignore patterns."""
            for pattern in ignore_patterns:
                if fnmatch.fnmatch(relative_path, pattern):
                    return True
                if fnmatch.fnmatch(self.os.path.basename(relative_path), pattern):
                    return True
                if pattern.endswith("/") and fnmatch.fnmatch(
                    relative_path + "/", pattern
                ):
                    return True
            return False

        def _get_files_from_dir(self, directory):
            """
            Recursively get all non-hidden files from the specified directory,
            respecting .gitignore rules. Uses caching.
            """
            if directory in self.cached_files:
                return self.cached_files[directory]
            files = []
            if not self.os.path.isdir(directory):
                self.logger.warning(
                    f"Directory path does not exist or is not a directory: {directory}"
                )
                return files
            ignore_patterns = self._load_gitignore_patterns(directory)
            for root, dirnames, filenames in self.os.walk(directory):
                relative_root = self.os.path.relpath(root, directory)
                if relative_root == ".":
                    relative_root = ""
                dirnames_to_keep = []
                for dname in dirnames:
                    relative_dir_path = self.os.path.join(relative_root, dname)
                    if dname.startswith("."):
                        continue
                    if self._is_ignored(relative_dir_path, ignore_patterns):
                        continue
                    dirnames_to_keep.append(dname)
                dirnames[:] = dirnames_to_keep
                for filename in filenames:
                    if filename.startswith("."):
                        continue
                    full_file_path = self.os.path.join(root, filename)
                    relative_file_path = self.os.path.join(relative_root, filename)
                    if self._is_ignored(relative_file_path, ignore_patterns):
                        continue
                    files.append(full_file_path)
            self.cached_files[directory] = files
            return files

        def _get_file_icon_name(self, file_path):
            """Determines the appropriate icon name for a file path, checking for existence."""
            filename = self.os.path.basename(file_path)
            if "." not in filename or filename.startswith("."):
                if filename.startswith("."):
                    extension = filename[1:]
                else:
                    extension = filename
            else:
                extension = file_path.split(".")[-1].lower()
            icon_name = self.extension_to_icon.get(extension)
            if icon_name:
                return icon_name
            if self.os.path.isdir(file_path):
                return "folder-symbolic"
            elif not extension:
                return "text-x-generic-symbolic"
            else:
                return f"text-x-{extension}-symbolic"

        def _handle_file_click(self, gesture, n_press, x, y, row_hbox):
            """
            Handles mouse clicks on a file row and launches the file with the
            editor corresponding to the mouse button (Left=1, Middle=2, Right=3).
            """
            if n_press != 1:
                return
            button = gesture.get_current_button()
            editor_index = button - 1
            file_path = row_hbox.MYTEXT
            self.open_file_in_editor(file_path=file_path, editor_index=editor_index)
            gesture.set_state(self.gtk.EventSequenceState.STOPPED)  # pyright: ignore

        def _create_file_row(self, full_file_path, root_dir):
            """
            Creates a single ListBox row child (HBox) for a file entry.
            Args:
                full_file_path (str): The absolute path to the file.
                root_dir (str): The root directory used for relative path calculation.
            """
            icon_name = self._get_file_icon_name(full_file_path)
            display_path = self.os.path.relpath(full_file_path, root_dir)
            row_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
            row_hbox.add_css_class("openwitheditor-row-hbox")
            row_hbox.MYTEXT = full_file_path  # pyright: ignore
            row_hbox.set_tooltip_text(full_file_path)
            line = self.gtk.Label.new()
            line.set_label(display_path)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(self.gtk.Align.START)
            line.add_css_class("openwitheditor-label-from-popover")
            image = self.gtk.Image.new_from_icon_name(icon_name)
            image.add_css_class("openwitheditor-icon-from-popover")
            image.set_icon_size(self.gtk.IconSize.INHERIT)
            image.props.margin_end = 5
            image.set_halign(self.gtk.Align.END)
            row_hbox.append(image)
            row_hbox.append(line)
            self.gtk_helper.add_cursor_effect(line)
            return row_hbox

        def _populate_listbox(self, listbox, directory_path, searchbar):
            """
            Populates the given listbox with files from the specified directory path.
            """
            row = listbox.get_row_at_index(0)
            while row is not None:
                listbox.remove(row)
                row = listbox.get_row_at_index(0)
            files_to_list = self._get_files_from_dir(directory_path)
            if not files_to_list and not self.os.path.isdir(directory_path):
                row_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
                label = self.gtk.Label.new(
                    f"Error: Directory not found or unreadable: {directory_path}"
                )
                row_hbox.append(label)
                listbox.append(row_hbox)
                listbox.set_filter_func(lambda r: False)
                return
            elif not files_to_list:
                row_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
                label = self.gtk.Label.new(
                    f"No files found in {directory_path} (or all ignored)."
                )
                row_hbox.append(label)
                listbox.append(row_hbox)
                listbox.set_filter_func(lambda r: False)
                return
            for file_path in files_to_list:
                row_hbox = self._create_file_row(
                    full_file_path=file_path, root_dir=directory_path
                )
                click_gesture = self.gtk.GestureClick.new()
                click_gesture.set_button(0)
                click_gesture.connect(
                    "pressed",
                    lambda gesture,
                    n_press,
                    x,
                    y,
                    box=row_hbox: self._handle_file_click(gesture, n_press, x, y, box),
                )
                row_hbox.add_controller(click_gesture)
                listbox.append(row_hbox)
            listbox.set_filter_func(lambda row: self._filter_logic(row, searchbar))

        def open_file_in_editor(self, file_path, editor_index=0):
            """
            Opens the specified file using the editor at the given index (0=Left, 1=Middle, 2=Right click)
            in the configured list for its extension.
            If no editor list is configured for the extension, it falls back to the default list.
            """
            if not file_path:
                self.logger.error("No file path provided.")
                return
            extension = file_path.split(".")[-1].lower() if "." in file_path else ""
            editor_config_value = self.editor_extensions.get(extension)
            editor_list = []
            if isinstance(editor_config_value, str):
                editor_list = [
                    e.strip() for e in editor_config_value.split(",") if e.strip()
                ]
            elif isinstance(editor_config_value, list):
                editor_list = [e.strip() for e in editor_config_value if e.strip()]
            if not editor_list:
                editor_list = self.default_editors
                self.logger.warning(
                    f"No editor configured for extension '{extension}'. Falling back to ultimate default list: {', '.join(editor_list)}."
                )
            if editor_index >= len(editor_list):
                editor = editor_list[0]
                self.logger.warning(
                    f"Editor index {editor_index} requested for '{file_path}' (only {len(editor_list)} editors configured: {', '.join(editor_list)}). Falling back to first editor: '{editor}'."
                )
            else:
                editor = editor_list[editor_index]
            TUI_EDITORS = ["nvim", "vi", "vim", "emacs", "nano", "micro", "ed"]
            is_tui_editor = editor in TUI_EDITORS
            cmd = None
            success = False
            if is_tui_editor:
                filename = self.os.path.basename(file_path)
                window_title = f"{editor.upper()} ({filename})"
                editor_command = f"{editor} {file_path}"
                for terminal in self.terminal_emulators:
                    if terminal in ["gnome-terminal", "terminator", "tilix"]:
                        cmd = f'{terminal} --title="{window_title}" -- /bin/sh -c "{editor_command}"'
                    elif terminal in ["xfce4-terminal", "lxterminal"]:
                        cmd = f'{terminal} --title="{window_title}" --command "{editor_command}"'
                    elif terminal in [
                        "kitty",
                        "alacritty",
                        "wezterm",
                        "xterm",
                        "urxvt",
                        "st",
                        "rxvt",
                    ]:
                        cmd = f'{terminal} -T "{window_title}" -e {editor_command}'
                    if cmd:
                        try:
                            self.run_cmd(cmd)
                            self.logger.info(
                                f"Opened file {file_path} using {editor} in {terminal} with title '{window_title}'."
                            )
                            success = True
                            break
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to open file using {terminal}: {e}"
                            )
                            continue
                if not success:
                    self.logger.error(
                        f"Could not open file: No working terminal emulator found to launch TUI editor '{editor}'."
                    )
            else:
                cmd = f"{editor} {file_path}"
                try:
                    self.run_cmd(cmd)
                    self.logger.info(
                        f"Opened file {file_path} using GUI editor '{editor}'."
                    )
                    success = True
                except Exception as e:
                    self.logger.error(
                        f"Failed to open file using GUI editor '{editor}': {e}"
                    )
            if self.popover_openwitheditor and success:
                self.popover_openwitheditor.popdown()

        def open_popover_openwitheditor(self, *_):
            if self.popover_openwitheditor and self.popover_openwitheditor.is_visible():
                self.popover_openwitheditor.popdown()
            elif (
                self.popover_openwitheditor
                and not self.popover_openwitheditor.is_visible()
            ):
                if self.active_listbox:
                    self.active_listbox.unselect_all()
                self.popover_openwitheditor.popup()
            elif not self.popover_openwitheditor:
                self.popover_openwitheditor = self.create_popover_openwitheditor()

        def popover_is_open(self, *_):
            if self.active_searchbar:
                self.active_searchbar.grab_focus()
            self.set_keyboard_on_demand()
            self.set_keyboard_on_demand()
            vadjustment = self.scrolled_window.get_vadjustment()
            vadjustment.set_value(0)

        def popover_is_closed(self, *_):
            self.set_keyboard_on_demand(False)
            if hasattr(self, "listbox"):
                self.listbox.invalidate_filter()

        def on_show_searchbar_action_actived(self, action, parameter):
            if self.active_searchbar:
                self.active_searchbar.set_search_mode(True)
                self.active_searchbar.grab_focus()

        def on_search_entry_changed(self, searchentry):
            """Finds the associated listbox and invalidates its filter."""
            searchentry.grab_focus()
            for dir_name, bar in self.searchbar_widgets.items():
                if bar == searchentry:
                    self.listbox = self.listbox_widgets[dir_name]
                    self.listbox.invalidate_filter()
                    return

        def _filter_logic(self, row, searchbar):
            """Internal helper for listbox filter function, receiving the associated searchbar."""
            try:
                child = row.get_child()
                if not child or not hasattr(child, "MYTEXT"):
                    return False
                row_text = child.MYTEXT
                if not isinstance(row_text, str):
                    return False
                text_to_search = searchbar.get_text().strip().lower()
                return text_to_search in row_text.lower()
            except Exception as e:
                self.logger.error(f"Unexpected error occurred in filter logic: {e}")
                return True

        def code_explanation(self):
            """
            This plugin creates a popover UI to search and open files from configured directories using tabs.
            1.  **Configuration & Editor Defaults**:
                - Uses a rich set of **recommended defaults** for editor selection if the user provides no configuration (e.g., `code` for config/web files, `nvim` for programming).
                - The `self.default_editors` list acts as an **ultimate fallback**.
            2.  **Tabbed UI and File Display (Updated)**:
                - The popover width has been **increased to 600px** (`set_min_content_width(600)`) to better display long paths.
                - The displayed file label now shows the **path relative to the configured root directory** (e.g., `subdir/file.py`), instead of just the filename, making it easier to locate files.
            3.  **Editor Selection and Gestures**:
                - Mouse buttons (Left, Middle, Right) determine the index of the editor to launch from the selected list.
            4.  **Lazy Loading & Filtering**: Files are scanned and loaded only when a tab is selected for the first time, and the search bar dynamically controls the filtering of the active tab's file list.
            """
            return self.code_explanation.__doc__

    return OpenWithEditor
