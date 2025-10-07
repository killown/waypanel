def get_plugin_metadata(_):
    return {
        "enabled": True,
        "index": 1,
        "container": "top-panel-box-widgets-left",
        "deps": [
            "top_panel",
        ],
    }


def get_plugin_class():
    import sqlite3
    from src.plugins.core._base import BasePlugin

    class AppMenu(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover_launcher = None
            self.widgets_dict = {}
            self.all_apps = None
            self.appmenu = self.gtk.Button()
            self.search_get_child = None
            self.icons = {}
            self.search_row = []
            self.desired_app_order = []
            self.db_path = self.path_handler.get_data_path("db/appmenu/recent_apps.db")
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()

        def on_start(self):
            self.main_widget = (self.appmenu, "append")
            try:
                self.settings = self.gio.Settings.new("org.gnome.desktop.interface")
            except Exception as e:
                self.logger.error(
                    f"Appmenu: Failed to initialize GSettings for icon-theme: {e}"
                )
                self.settings = None
            self._create_recent_apps_table()
            self.create_menu_popover_launcher()
            self.create_popover_launcher()

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
            self.gtk_helper.add_cursor_effect(self.appmenu)

        def create_popover_launcher(self):
            """
            Create and configure the popover launcher once at startup.
            """
            self.popover_launcher = self._create_and_configure_popover()
            self._setup_scrolled_window_and_flowbox()
            self._populate_flowbox_with_apps()
            self._finalize_popover_setup(is_initial_setup=True)
            return self.popover_launcher

        def _create_and_configure_popover(self):
            """Create and configure the popover."""
            popover = self.create_popover(
                parent_widget=self.appmenu,
                css_class="app-launcher-popover",
                has_arrow=True,
                closed_handler=self.popover_is_closed,
                visible_handler=self.popover_is_open,
            )

            show_searchbar_action = self.gio.SimpleAction.new("show_searchbar")
            show_searchbar_action.connect(
                "activate", self.on_show_searchbar_action_actived
            )
            if hasattr(self, "obj") and self.obj:
                self.obj.add_action(show_searchbar_action)

            return popover

        def _setup_scrolled_window_and_flowbox(self):
            """Set up the scrolled window, search bar, and flowbox."""
            self.scrolled_window = self.gtk.ScrolledWindow()
            self.scrolled_window.set_policy(
                self.gtk.PolicyType.NEVER,
                self.gtk.PolicyType.AUTOMATIC,
            )
            self.main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
            self.main_box.add_css_class("app-launcher-main-box")
            self.searchbar = self.gtk.SearchEntry.new()
            self.searchbar.grab_focus()
            self.searchbar.connect("search_changed", self.on_search_entry_changed)
            self.searchbar.connect("activate", self.on_keypress)
            self.searchbar.connect("stop-search", self.on_searchbar_key_release)
            self.searchbar.set_focus_on_click(True)
            self.searchbar.set_placeholder_text("Search apps...")
            self.searchbar.add_css_class("app-launcher-searchbar")
            self.main_box.append(self.searchbar)
            self.flowbox = self.gtk.FlowBox()
            self.flowbox.set_valign(self.gtk.Align.START)
            self.flowbox.set_halign(self.gtk.Align.FILL)
            self.flowbox.props.max_children_per_line = 30
            self.flowbox.set_max_children_per_line(5)
            self.flowbox.set_homogeneous(False)
            self.flowbox.set_selection_mode(self.gtk.SelectionMode.SINGLE)
            self.flowbox.set_activate_on_single_click(True)
            self.flowbox.connect("child-activated", self.run_app_from_launcher)
            self.flowbox.add_css_class("app-launcher-flowbox")
            self.flowbox.set_sort_func(self.app_sort_func, None)
            self.flowbox.set_filter_func(self.on_filter_invalidate)
            self.main_box.append(self.scrolled_window)
            self.scrolled_window.set_child(self.flowbox)
            self.popover_launcher.set_child(self.main_box)  # pyright: ignore

        def _populate_flowbox_with_apps(self):
            """
            Populates the flowbox with application buttons and ensures all are cached.
            This runs once on first popover open.
            """
            all_apps_list = self.gio.AppInfo.get_all()
            self.all_apps = {i.get_id(): i for i in all_apps_list if i.get_id()}
            for app_id, app_info in self.all_apps.items():
                if app_id not in self.icons:
                    self._add_app_to_flowbox(app_info, app_id)
            self.update_flowbox()

        def _finalize_popover_setup(self, is_initial_setup=False):
            """Finalize the popover setup."""
            min_size, natural_size = self.flowbox.get_preferred_size()
            width = natural_size.width if natural_size else 0
            self.flowbox.add_css_class("app-launcher-flowbox")
            self.scrolled_window.set_size_request(720, 570)
            self.scrolled_window.set_min_content_width(width)
            self.scrolled_window.set_min_content_height(500)
            if self.popover_launcher:
                self.popover_launcher.set_parent(self.appmenu)
                self.popover_launcher.add_css_class("app-launcher-popover")
                if not is_initial_setup:
                    self.popover_launcher.popup()

        def on_keypress(self, *_):
            """Open the app selected from the search bar."""
            cmd = "gtk-launch {}".format(self.search_get_child)
            if hasattr(self, "cmd") and self.cmd:
                self.cmd.run(cmd)
            if self.popover_launcher:
                self.popover_launcher.popdown()

        def update_flowbox(self):
            """
            Updates the flowbox by checking for installed/uninstalled apps
            and reordering existing, cached widgets to prioritize recently opened apps.
            """
            all_apps_list = self.gio.AppInfo.get_all()
            current_installed_apps = {
                a.get_id(): a for a in all_apps_list if a.get_id()
            }
            recent_app_ids = self.get_recent_apps()
            apps_to_remove = set(self.icons.keys()) - set(current_installed_apps.keys())
            for app_id in apps_to_remove:
                widget_data = self.icons.pop(app_id, None)
                if widget_data:
                    vbox = widget_data["vbox"]
                    flowbox_child = vbox.get_parent()
                    if flowbox_child:
                        self.flowbox.remove(flowbox_child)
            for app_id, app in current_installed_apps.items():
                if app_id not in self.icons:
                    self._add_app_to_flowbox(app, app_id)
            desired_app_id_order = []
            recent_ids_set = set(recent_app_ids)
            for app_id in recent_app_ids:
                if app_id in current_installed_apps and app_id in self.icons:
                    desired_app_id_order.append(app_id)
            non_recent_apps = sorted(
                [
                    app_id
                    for app_id in current_installed_apps
                    if app_id not in recent_ids_set and app_id in self.icons
                ],
                key=lambda app_id: current_installed_apps[app_id].get_name().lower()
                if current_installed_apps[app_id].get_name()
                else app_id.lower(),  # pyright: ignore
            )
            desired_app_id_order.extend(non_recent_apps)
            self.desired_app_order = desired_app_id_order
            self.flowbox.invalidate_sort()
            self.flowbox.invalidate_filter()

        def _add_app_to_flowbox(self, app, app_id):
            """
            Adds an application to the flowbox (and to the persistent self.icons cache).
            Args:
                app: The self.gio.AppInfo object representing the app.
                app_id: The unique desktop file ID (e.g., 'firefox.desktop').
            """
            if hasattr(app, "get_keywords"):
                keywords = " ".join(app.get_keywords())
            else:
                keywords = ""
            display_name = app.get_name() if app.get_name() else app_id
            cmd = app_id
            if display_name.count(" ") > 2:
                truncated_display_name = " ".join(display_name.split()[:3])
            else:
                truncated_display_name = display_name
            icon = app.get_icon()
            if icon is None:
                icon = self.gio.ThemedIcon.new_with_default_fallbacks(
                    "application-x-executable-symbolic"
                )
            if app_id not in self.icons:
                vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
                vbox.set_halign(self.gtk.Align.CENTER)
                vbox.set_valign(self.gtk.Align.CENTER)
                vbox.set_margin_top(1)
                vbox.set_margin_bottom(1)
                vbox.set_margin_start(1)
                vbox.set_margin_end(1)
                vbox.add_css_class("app-launcher-vbox")
                vbox.MYTEXT = display_name, cmd, keywords  # pyright: ignore
                image = self.gtk.Image.new_from_gicon(icon)
                image.set_halign(self.gtk.Align.CENTER)
                image.add_css_class("app-launcher-icon-from-popover")
                self.gtk_helper.add_cursor_effect(image)
                label = self.gtk.Label.new(truncated_display_name)
                label.set_max_width_chars(20)
                label.set_ellipsize(self.pango.EllipsizeMode.END)
                label.set_halign(self.gtk.Align.CENTER)
                label.add_css_class("app-launcher-label-from-popover")
                self.icons[app_id] = {"icon": image, "label": label, "vbox": vbox}
                vbox = self.icons[app_id]["vbox"]
                vbox.append(self.icons[app_id]["icon"])
                vbox.append(self.icons[app_id]["label"])
                gesture = self.gtk.GestureClick.new()
                gesture.set_button(self.gdk.BUTTON_SECONDARY)
                gesture.connect("pressed", self.on_right_click_popover, vbox)
                vbox.add_controller(gesture)
                self.flowbox.append(vbox)
                self.flowbox.add_css_class("app-launcher-flowbox")

        def app_sort_func(self, child1, child2, user_data=None):
            """Custom sort function for self.gtk.FlowBox based on index in self.desired_app_order."""
            _, app_id_1, _ = child1.get_child().MYTEXT
            _, app_id_2, _ = child2.get_child().MYTEXT
            try:
                index1 = self.desired_app_order.index(app_id_1)
            except ValueError:
                index1 = len(self.desired_app_order) + 1
            try:
                index2 = self.desired_app_order.index(app_id_2)
            except ValueError:
                index2 = len(self.desired_app_order) + 1
            if index1 < index2:
                return -1
            elif index1 > index2:
                return 1
            else:
                return 0

        def add_recent_app(self, app_id):
            """
            Add or update an app in the recent apps table using the unique app_id.
            """
            self.cursor.execute(
                """
                INSERT OR REPLACE INTO recent_apps (app_name, last_opened_at)
                VALUES (?, ?)
            """,
                (app_id, self.time.time()),
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
            """Get the list of recent app IDs from the SQLite database."""
            self.cursor.execute(
                "SELECT app_name FROM recent_apps ORDER BY last_opened_at DESC LIMIT 50"
            )
            recent_app_ids = [row[0] for row in self.cursor.fetchall()]
            return recent_app_ids

        def run_app_from_launcher(self, x, y):
            """Run the selected app from the launcher."""
            mytext = [i.get_child().MYTEXT for i in x.get_selected_children()][0]
            name, desktop_id, keywords = mytext
            desktop_id_no_ext = desktop_id.split(".desktop")[0]
            cmd = "gtk-launch {}".format(desktop_id_no_ext)
            self.add_recent_app(desktop_id)
            if hasattr(self, "cmd") and self.cmd:
                self.cmd.run(cmd)
            if self.popover_launcher:
                self.popover_launcher.popdown()
            self.update_flowbox()

        def open_popover_launcher(self, *_):
            """Open or close the pre-created popover launcher."""
            if self.popover_launcher:
                if self.popover_launcher.is_visible():
                    self.popover_launcher.popdown()
                    self.popover_is_closed()
                    return
                else:
                    self.update_flowbox()
                    self.flowbox.unselect_all()
                    self.popover_launcher.popup()
                    self.searchbar.set_text("")
                    self.popover_is_open()

        def popover_is_open(self, *_):
            """Set the keyboard mode to ON_DEMAND when the popover is opened."""
            self.set_keyboard_on_demand()
            vadjustment = self.scrolled_window.get_vadjustment()
            vadjustment.set_value(0)
            return

        def popover_is_closed(self, *_):
            """
            Set the keyboard mode to NONE when the popover is closed.
            FIX: No destruction or cache clearing is done here. The UI is simply hidden.
            """
            self.set_keyboard_on_demand(False)
            if hasattr(self, "listbox"):
                self.flowbox.invalidate_filter()

        def on_searchbar_key_release(self, widget, event):
            """
            Handle key release events on the search bar.
            """
            keyval = event.keyval
            if keyval == self.gdk.KEY_Escape:
                if self.popover_launcher:
                    self.popover_launcher.popdown()
                return True
            return False

        def on_show_searchbar_action_actived(self, action, parameter):
            """Show the search bar when the show_searchbar action is activated."""
            self.searchbar.set_search_mode(True)  # pyright: ignore

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
            wclass = self.os.path.splitext(desktop_file)[0]
            if hasattr(self, "config_handler") and self.config_handler:
                new_entry = {
                    "cmd": f"gtk-launch {desktop_file.split('.desktop')[0]}",
                    "icon": wclass,
                    "wclass": wclass,
                    "desktop_file": desktop_file,
                    "name": name,
                    "initial_title": name,
                }
                dockbar_config = self.config_handler.config_data.get("dockbar", {})  # pyright: ignore
                app_config = dockbar_config.get("app", {})
                app_config[name] = new_entry
                dockbar_config["app"] = app_config
                self.config_handler.config_data["dockbar"] = dockbar_config  # pyright: ignore
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
                self.os.path.expanduser("~/.local/share/applications/"),
            ]
            file_path = None
            for location in common_locations:
                path_to_check = self.os.path.join(location, desktop_file)
                if self.os.path.exists(path_to_check):
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
                if hasattr(self, "cmd") and self.cmd:
                    for editor in gui_editors:
                        try:
                            cmd = editor + " " + file_path
                            self.cmd.run(cmd)
                            popover.popdown()
                            if self.popover_launcher:
                                self.popover_launcher.popdown()
                            return
                        except Exception as e:
                            if hasattr(self, "logger") and self.logger:
                                self.logger.error(f"Appmenu: No text editor found: {e}")
                            continue
                for term in terminal_emulators:
                    for editor in terminal_editors:
                        try:
                            cmd = f"{term} -e {editor} {file_path}"
                            self.run_cmd(cmd)
                            popover.popdown()
                            if self.popover_launcher:
                                self.popover_launcher.popdown()
                            return
                        except FileNotFoundError:
                            continue
                if hasattr(self, "logger") and self.logger:
                    self.logger.error(
                        "Error: Could not find an editor to open the .desktop file."
                    )

        def _get_available_icon_themes(self):
            """Scans common XDG directories for icon themes by looking for index.theme files."""
            theme_names = set()
            base_dirs = [
                self.os.path.join(self.os.path.expanduser("~"), ".icons"),
                "/usr/share/icons",
            ]
            for base_dir in base_dirs:
                if self.os.path.exists(base_dir):
                    try:
                        for entry in self.os.listdir(base_dir):
                            theme_path = self.os.path.join(
                                base_dir, entry, "index.theme"
                            )
                            if self.os.path.exists(theme_path) and self.os.path.isdir(
                                self.os.path.join(base_dir, entry)
                            ):
                                theme_names.add(entry)
                    except Exception as e:
                        if hasattr(self, "logger") and self.logger:
                            self.logger.warning(
                                f"Failed to scan icon directory {base_dir}: {e}"
                            )
            theme_names.add("hicolor")
            return sorted(list(theme_names))

        def _on_icon_theme_changed(self, dropdown, pspec):
            """Sets the new icon theme via GSettings."""
            if not self.settings:
                if hasattr(self, "logger") and self.logger:
                    self.logger.error(
                        "GSettings not initialized. Cannot change icon theme."
                    )
                return
            selected_item = dropdown.get_selected_item()
            if selected_item:
                theme_name = selected_item.get_string()
                try:
                    self.settings.set_string("icon-theme", theme_name)
                    if hasattr(self, "logger") and self.logger:
                        self.logger.info(f"Icon theme set to: {theme_name}")
                    if hasattr(self, "gtk_helper") and self.gtk_helper:
                        icon_name = self.gtk_helper.set_widget_icon_name(
                            "appmenu",
                            ["archlinux-logo"],
                        )
                        self.appmenu.set_icon_name(icon_name)
                    parent_popover = dropdown.get_root()
                    if isinstance(parent_popover, self.gtk.Popover):
                        parent_popover.popdown()
                except Exception as e:
                    if hasattr(self, "logger") and self.logger:
                        self.logger.error(
                            f"Failed to set icon theme via GSettings: {e}"
                        )

        def on_right_click_popover(self, gesture, n_press, x, y, vbox):
            """
            Handle right-click event to show a popover menu.
            """
            popover = self.gtk.Popover()
            popover.add_css_class("app-launcher-context-menu")
            menu_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
            menu_box.set_margin_start(10)
            menu_box.set_margin_end(10)
            menu_box.set_margin_top(10)
            menu_box.set_margin_bottom(10)
            config_handler_exists = (
                hasattr(self, "config_handler") and self.config_handler
            )
            if self.settings:
                current_theme = self.settings.get_string("icon-theme")
                available_themes = self._get_available_icon_themes()
                theme_list_store = self.gtk.StringList.new(available_themes)
                theme_dropdown = self.gtk.DropDown.new(theme_list_store, None)
                theme_dropdown.set_hexpand(True)
                theme_dropdown.connect(
                    "notify::selected-item", self._on_icon_theme_changed
                )
                current_index = 0
                for i, theme_name in enumerate(available_themes):
                    if theme_name == current_theme:
                        current_index = i
                        break
                theme_dropdown.set_selected(current_index)
                theme_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
                theme_box.set_halign(self.gtk.Align.FILL)
                theme_box.set_margin_bottom(10)
                theme_label = self.gtk.Label.new("Icon Theme:")
                theme_label.set_halign(self.gtk.Align.CENTER)
                theme_box.append(theme_label)
                theme_box.append(theme_dropdown)
                separator = self.gtk.Separator.new(self.gtk.Orientation.HORIZONTAL)
                theme_box.append(separator)
                menu_box.prepend(theme_box)
            name, desktop_file, keywords = vbox.MYTEXT
            is_in_dockbar = False
            if config_handler_exists:
                is_in_dockbar = desktop_file in self.config_handler.config_data.get(  # pyright: ignore
                    "dockbar", {}
                )
            open_button = self.gtk.Button.new_with_label(f"Open {name}")
            open_button.connect(
                "clicked", self.run_app_from_menu, desktop_file, popover
            )
            menu_box.append(open_button)
            open_desktop_button = self.gtk.Button.new_with_label("Open .desktop File")
            open_desktop_button.connect(
                "clicked", self.open_desktop_file, desktop_file, popover
            )
            menu_box.append(open_desktop_button)
            search_button = self.gtk.Button.new_with_label("Search in GNOME Software")
            search_button.connect(
                "clicked", self.search_in_gnome_software, name, popover
            )
            menu_box.append(search_button)
            if config_handler_exists:
                if is_in_dockbar:
                    remove_button = self.gtk.Button.new_with_label(
                        "Remove from dockbar"
                    )
                    remove_button.connect(
                        "clicked", self.remove_from_dockbar, desktop_file, popover
                    )
                    menu_box.append(remove_button)
                else:
                    add_button = self.gtk.Button.new_with_label("Add to dockbar")
                    add_button.connect(
                        "clicked", self.add_to_dockbar, name, desktop_file, popover
                    )
                    menu_box.append(add_button)
            popover.set_child(menu_box)
            popover.set_parent(vbox)
            popover.set_has_arrow(False)
            popover.popup()
            gesture.set_state(self.gtk.EventSequenceState.CLAIMED)

        def remove_from_dockbar(self, button, desktop_file, popover):
            """
            Removes the selected app from the dockbar configuration.
            """
            if hasattr(self, "config_handler") and self.config_handler:
                dockbar_config = self.config_handler.config_data.get("dockbar", {})  # pyright: ignore
                app_config = dockbar_config.get("app", {})
                key_to_remove = next(
                    (
                        name
                        for name, entry in app_config.items()
                        if entry.get("desktop_file") == desktop_file
                    ),
                    None,
                )
                if key_to_remove:
                    del app_config[key_to_remove]
                    dockbar_config["app"] = app_config
                    self.config_handler.config_data["dockbar"] = dockbar_config  # pyright: ignore
                    self.config_handler.save_config()
                    self.config_handler.reload_config()
            popover.popdown()
            if self.popover_launcher:
                self.popover_launcher.popdown()
            self.update_flowbox()

        def search_in_gnome_software(self, button, name, popover):
            """
            Runs gnome-software with the search parameter for the selected application.
            """
            cmd = f"gnome-software --search={name}"
            try:
                self.run_cmd(cmd)
            except FileNotFoundError:
                if hasattr(self, "logger") and self.logger:
                    self.logger.error("Error: gnome-software command not found.")
            finally:
                popover.popdown()
                if self.popover_launcher:
                    self.popover_launcher.popdown()

        def run_app_from_menu(self, button, desktop_file, popover):
            """
            Runs the app when the 'Open' button in the context menu is clicked.
            """
            desktop_id_no_ext = desktop_file.split(".desktop")[0]
            cmd = "gtk-launch {}".format(desktop_id_no_ext)
            self.add_recent_app(desktop_file)
            if hasattr(self, "cmd") and self.cmd:
                self.cmd.run(cmd)
            popover.popdown()
            if self.popover_launcher:
                self.popover_launcher.popdown()
            self.update_flowbox()

        def on_search_entry_changed(self, searchentry):
            """The filter_func will be called for each row after the call,
            and it will continue to be called each self.time a row changes (via [method`self.gtk`.ListBoxRow.changed])
            or when [method`self.gtk`.ListBox.invalidate_filter] is called."""
            searchentry.grab_focus()
            self.flowbox.invalidate_filter()

        def on_filter_invalidate(self, row):
            """Filter the flowbox rows based on the search entry."""
            text_to_search = self.searchbar.get_text().strip().lower()
            if not isinstance(row, str):
                vbox = row.get_child()
                if not hasattr(vbox, "MYTEXT"):
                    return False
                display_name, desktop_id, keywords = vbox.MYTEXT
                combined_text = f"{display_name} {desktop_id} {keywords}".lower()
                if text_to_search in combined_text:
                    self.search_get_child = desktop_id
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
            Its core logic is centered on dynamic UI generation, state management, and interaction:
            1.  Application Discovery: It retrieves all installed applications using
                self.gio.AppInfo.get_all().
            2.  Recent Apps Persistence: It tracks recently launched applications using a
                SQLite database (recent_apps.db).
            3.  Dynamic Filtering: It uses a self.gtk.SearchEntry connected to a
                self.gtk.FlowBox to provide a fast, real-time search experience.
            4.  Popover and UI: The launcher is displayed in a self.gtk.Popover attached to a main button. Applications are in a grid-like self.gtk.FlowBox.
            5.  Icon Theme Selection: The right-click popover allows changing the system-wide icon theme using self.gio.Settings.
            FIXED ERRORS:
            1. 'not loading all apps' (Previous fix): The code was refactored to use the application's unique **Desktop File ID (app.get_id())** as the primary key for all internal logic (`self.icons`, `self.desired_app_order`, and `recent_apps` database), ensuring every app has a distinct identifier and is loaded.
            2. 'unnecessary widget destruction/re-creation' (Current fix): The core UI elements (`self.gtk.Popover`, `self.gtk.FlowBox`, `Gtk.SearchEntry`) are now created **once** during plugin initialization. The app icon widgets (`self.icons`) are now a **truly persistent cache**. On every open, `self.update_flowbox()` is called to incrementally:
               - Remove uninstalled app widgets from the `self.gtk.FlowBox` and `self.icons` cache.
               - Add newly installed app widgets to the `self.gtk.FlowBox` and `self.icons` cache.
               - Re-sort the existing widgets in the `self.gtk.FlowBox` based on recency.
            This refactoring ensures maximum efficiency by reusing the UI components and only performing updates (add/remove) when necessary, satisfying the requested pattern of incremental updates.
            """
            return self.code_explanation.__doc__

    return AppMenu
