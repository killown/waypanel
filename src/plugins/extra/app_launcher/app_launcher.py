CONTAINER = ""


def get_plugin_metadata(panel):
    """
    Returns the metadata for the App Launcher plugin.
    """
    about = "A dynamic application launcher with a search bar and a grid view of installed and recently used applications."
    default_container = "top-panel-box-widgets-left"
    id = "org.waypanel.plugin.app_launcher"
    CONTAINER, id = panel.config_handler.get_plugin_container(default_container, id)
    return {
        "id": id,
        "name": "App Launcher",
        "version": "1.0.0",
        "enabled": True,
        "index": 1,
        "priority": 987,
        "container": CONTAINER,
        "deps": ["css_generator"],
        "description": about,
    }


def get_plugin_class():
    """
    Dynamically imports dependencies and returns the AppLauncher class.
    """
    import distro
    import os
    from src.plugins.core._base import BasePlugin
    from ._database import RecentAppsDatabase
    from ._scanner import AppScanner
    from ._menu import AppMenuHandler
    from ._remote_apps import RemoteApps
    from ._uninstall_window import FlatpakUninstallWindow

    class AppLauncher(BasePlugin):
        """
        Plugin class for the application launcher interface.
        """

        def __init__(self, panel_instance):
            """
            Initializes the launcher settings, scanner, database, menu handler and UI.
            """
            super().__init__(panel_instance)
            self.remote_widgets = []
            self.search_timeout_id = None
            self.popover_width = self.get_plugin_setting_add_hint(
                ["layout", "popover_width"],
                600,
                "The fixed width (in pixels) of the main launcher popover window.",
            )
            self.popover_height = self.get_plugin_setting_add_hint(
                ["layout", "popover_height"],
                570,
                "The fixed height (in pixels) of the main launcher popover window.",
            )
            self.min_app_grid_height = self.get_plugin_setting_add_hint(
                ["layout", "min_app_grid_height"],
                500,
                "The minimum height (in pixels) reserved for the application grid (FlowBox) inside the popover.",
            )
            self.max_apps_per_row = self.get_plugin_setting_add_hint(
                ["layout", "max_apps_per_row"],
                5,
                "The maximum number of application icons to display horizontally per row in the grid layout.",
            )
            self.max_recent_apps_db = self.get_plugin_setting_add_hint(
                ["behavior", "max_recent_apps_db"],
                50,
                "The maximum number of recently launched applications to store in the database for sorting/prioritization.",
            )
            self.main_icon = self.get_plugin_setting_add_hint(
                ["main_icon"],
                "start-here",
                "The default icon name (Gnome/Freedesktop standard) for the launcher button on the panel.",
            )

            # System Action Commands
            self.exit_panel_command = self.get_plugin_setting_add_hint(
                ["commands", "exit_panel"],
                "pkill -f waypanel/main.py",
                "Command to immediately stop all Waypanel processes.",
            )
            self.logout_command = self.get_plugin_setting_add_hint(
                ["commands", "logout"],
                "wayland-logout",
                "Command to end the Wayland session.",
            )
            self.shutdown_command = self.get_plugin_setting_add_hint(
                ["commands", "shutdown"],
                "shutdown -h now",
                "Command to immediately power off the system.",
            )
            self.suspend_command = self.get_plugin_setting_add_hint(
                ["commands", "suspend"],
                "systemctl suspend",
                "Command to put the system into a low-power sleep state.",
            )
            self.reboot_command = self.get_plugin_setting_add_hint(
                ["commands", "reboot"],
                "reboot",
                "Command to restart the system.",
            )
            self.lock_command = self.get_plugin_setting_add_hint(
                ["commands", "lock_screen"],
                "swaylock",
                "The full command used to lock the screen.",
            )

            # Customizable System Action Icons
            self.system_button_config = {
                "Settings": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "settings"],
                        [
                            "settings-configure-symbolic",
                            "systemsettings-symbolic",
                            "settings",
                        ],
                    ),
                },
                "Compositor": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "settings"],
                        [
                            "settings-configure-symbolic",
                            "systemsettings-symbolic",
                            "settings",
                        ],
                    ),
                },
                "Lock": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "lock"],
                        ["system-lock-screen-symbolic", "lock-symbolic"],
                    ),
                },
                "Logout": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "logout"],
                        ["system-log-out-symbolic", "gnome-logout-symbolic"],
                    ),
                },
                "Suspend": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "suspend"],
                        [
                            "system-suspend-hibernate-symbolic",
                            "system-suspend-symbolic",
                        ],
                    ),
                },
                "Reboot": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "system-reboot-symbolic"],
                        ["system-reboot-symbolic", "reboot"],
                    ),
                },
                "Shutdown": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "system-shutdown-symbolic"],
                        [
                            "system-shutdown-symbolic",
                            "system-shutdown-panel",
                            "gnome-shutdown-symbolic",
                            "system-shutdown-symbolic",
                            "switch-off-symbolic",
                            "preferences-system-power-symbolic",
                        ],
                    ),
                },
                "Exit Panel": {
                    "icons": self.get_plugin_setting(
                        ["buttons", "icons", "exit"],
                        ["application-exit-symbolic", "application-exit", "exit"],
                    ),
                },
            }

            distributor_id = distro.id()
            distributor_logo_fallback_icons = [
                f"distributor-{distributor_id}",
                f"{distributor_id}-logo",
                f"{distributor_id}_logo",
                f"distributor_{distributor_id}",
                f"logo{distributor_id}",
                f"{distributor_id}logo",
            ]
            self.fallback_main_icons = self.get_plugin_setting_add_hint(
                ["fallback_main_icons"],
                distributor_logo_fallback_icons,
                "A prioritized list of fallback icons to use if the main icon is not found.",
            )

            self.scanner = AppScanner()
            self.menu_handler = AppMenuHandler(self)
            self.remote_apps = RemoteApps(self)
            self.popover_launcher = None
            self.widgets_dict = {}
            self.all_apps = None
            self.appmenu = self.gtk.Button()
            self.search_get_child = None
            self.icons = {}
            self.search_row = []
            self.desired_app_order = []
            self.db_path = self.path_handler.get_data_path("db/appmenu/recent_apps.db")

            self.recent_db = RecentAppsDatabase(
                db_path=self.db_path,
                max_recent=self.max_recent_apps_db,
                time_handler=self.time,
            )

            self.dockbar_id = "org.waypanel.plugin.dockbar"
            icon_name = self._gtk_helper.icon_exist(
                self.main_icon, self.fallback_main_icons
            )
            self.appmenu.set_icon_name(icon_name)
            self.show_ignored = self.get_plugin_setting_add_hint(
                ["behavior", "show_ignored"],
                False,
                "Whether to show applications marked as ignored.",
            )

        def on_start(self):
            """Triggered when the plugin starts. Initializes UI and database."""
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
            self.plugins["css_generator"].install_css("app-launcher.css")

        def _create_recent_apps_table(self):
            """Ensures the database table is ready."""
            self.recent_db.initialize_schema()

        def close(self):
            """Closes the database connection on plugin shutdown."""
            self.recent_db.disconnect()

        def create_menu_popover_launcher(self):
            """Configures the launcher button click handler."""
            self.appmenu.connect("clicked", self.open_popover_launcher)
            self.appmenu.add_css_class("app-launcher-menu-button")
            self.gtk_helper.add_cursor_effect(self.appmenu)

        def create_popover_launcher(self):
            """Constructs the popover UI."""
            self.popover_launcher = self._create_and_configure_popover()
            self._setup_scrolled_window_and_flowbox()
            self._populate_flowbox_with_apps()
            self._finalize_popover_setup(is_initial_setup=True)
            return self.popover_launcher

        def _create_and_configure_popover(self):
            """Creates and returns the popover widget."""
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
            """Initializes the search bar, app grid, and sidebar actions."""
            self.main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
            self.main_box.add_css_class("app-launcher-main-box")

            # Content area with Sidebar
            self.middle_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
            self.middle_hbox.add_css_class("app-launcher-middle-hbox")

            # Sidebar Column
            self.sidebar_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 4)
            self.sidebar_vbox.add_css_class("app-launcher-sidebar-vbox")
            self.sidebar_vbox.set_valign(self.gtk.Align.FILL)
            self.sidebar_vbox.set_margin_start(10)
            self.sidebar_vbox.set_margin_end(10)
            self.sidebar_vbox.set_margin_top(10)
            self.sidebar_vbox.set_margin_bottom(10)

            for action_label, config in self.system_button_config.items():
                btn = self.gtk.Button()
                btn.add_css_class("app-launcher-sidebar-button")
                self.gtk_helper.add_cursor_effect(btn)

                btn_content = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 12)
                icon_name = self.icon_exist(config["icons"][0])
                img = self.gtk.Image.new_from_icon_name(icon_name)
                img.set_pixel_size(22)
                img.add_css_class("app-launcher-system-button-icon")
                lbl = self.gtk.Label.new(action_label)
                lbl.add_css_class("app-launcher-system-button-label")
                lbl.set_halign(self.gtk.Align.START)

                btn_content.append(img)
                btn_content.append(lbl)
                btn.set_child(btn_content)
                btn.connect("clicked", self.on_system_action_clicked, action_label)
                self.sidebar_vbox.append(btn)

            # Bottom of Column: Show Ignored Switch
            separator = self.gtk.Separator.new(self.gtk.Orientation.HORIZONTAL)
            separator.set_margin_top(10)
            separator.set_margin_bottom(10)
            self.sidebar_vbox.append(separator)

            ignore_container = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 6)
            ignore_container.set_halign(self.gtk.Align.START)
            ignore_label = self.gtk.Label.new("Show Ignored")
            ignore_label.add_css_class("app-launcher-footer-label")
            ignore_label.set_halign(self.gtk.Align.START)

            self.ignore_switch = self.gtk.Switch.new()
            self.ignore_switch.set_active(self.show_ignored)
            self.ignore_switch.set_halign(self.gtk.Align.START)
            self.ignore_switch.add_css_class("app-launcher-ignore-switch")
            self.ignore_switch.connect("state-set", self.on_ignore_switch_toggled)

            ignore_container.append(ignore_label)
            ignore_container.append(self.ignore_switch)
            self.sidebar_vbox.append(ignore_container)

            # Center Container: Search bar + Scrolled Window
            self.center_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 0)
            self.center_vbox.set_hexpand(True)
            self.center_vbox.add_css_class("app-launcher-center-vbox")

            self.searchbar = self.gtk.SearchEntry.new()
            self.searchbar.grab_focus()
            self.searchbar.connect("search_changed", self.on_search_entry_changed)
            self.searchbar.connect("activate", self.on_keypress)
            self.searchbar.connect("stop-search", self.on_searchbar_key_release)
            self.searchbar.set_focus_on_click(True)
            self.searchbar.set_placeholder_text("Search apps...")
            self.searchbar.add_css_class("app-launcher-searchbar")
            self.searchbar.set_valign(self.gtk.Align.START)
            self.searchbar.set_hexpand(True)
            self.center_vbox.append(self.searchbar)

            self.scrolled_window = self.gtk.ScrolledWindow()
            self.scrolled_window.set_policy(
                self.gtk.PolicyType.NEVER,
                self.gtk.PolicyType.AUTOMATIC,
            )
            self.flowbox = self.gtk.FlowBox()
            self.flowbox.set_valign(self.gtk.Align.START)
            self.flowbox.set_halign(self.gtk.Align.FILL)
            self.flowbox.set_max_children_per_line(self.max_apps_per_row)
            self.flowbox.set_selection_mode(self.gtk.SelectionMode.SINGLE)
            self.flowbox.set_activate_on_single_click(True)
            self.flowbox.connect("child-activated", self.run_app_from_launcher)
            self.flowbox.add_css_class("app-launcher-flowbox")
            self.flowbox.set_sort_func(self.app_sort_func, None)
            self.flowbox.set_filter_func(self.on_filter_invalidate)

            self.scrolled_window.set_child(self.flowbox)
            self.scrolled_window.set_vexpand(True)
            self.center_vbox.append(self.scrolled_window)

            self.middle_hbox.append(self.center_vbox)
            self.middle_hbox.append(self.sidebar_vbox)
            self.main_box.append(self.middle_hbox)
            self.popover_launcher.set_child(self.main_box)

        def view_id_found(self, title="Wayfire Configuration"):
            return [
                i["id"]
                for i in self.ipc.list_views()
                if i["app-id"] == "org.waypanel" and i["title"] == title
            ]

        def launch_config_viewer(self):
            config_viewer = self.plugins.get("wayfire_config_viewer")
            if hasattr(config_viewer, "window"):
                # set the view focus
                if config_viewer.window and config_viewer.window.get_visible():
                    id_found = self.view_id_found()
                    if id_found:
                        self.ipc.set_focus(id_found[0])
                        self.popover_launcher.popdown()
                # open a new window instance
                if hasattr(config_viewer, "_open_viewer"):
                    config_viewer._open_viewer()

        def on_system_action_clicked(self, button, action):
            """Executes requested system action and closes popover."""
            if action == "Exit Panel":
                self.subprocess.Popen(self.exit_panel_command.split())
            elif action == "Logout":
                self.subprocess.Popen(self.logout_command.split())
            elif action == "Shutdown":
                self.subprocess.Popen(self.shutdown_command.split())
            elif action == "Suspend":
                self.subprocess.Popen(self.suspend_command.split())
            elif action == "Reboot":
                self.subprocess.Popen(self.reboot_command.split())
            elif action == "Lock":
                self.subprocess.Popen(self.lock_command.split())
            elif action == "Settings":
                control_center = self.plugins.get("control_center")
                if control_center:
                    control_center.do_activate()
            elif action == "Compositor":
                self.launch_config_viewer()

            if self.popover_launcher:
                self.popover_launcher.popdown()

        def on_ignore_switch_toggled(self, switch, state):
            """Updates visibility preference for ignored applications."""
            self.show_ignored = state
            self.set_plugin_setting(["behavior", "show_ignored"], state)
            self.update_flowbox()
            return False

        def _populate_flowbox_with_apps(self):
            """Discovers and adds desktop applications to the launcher grid."""
            self.all_apps = self.scanner.scan()
            for app_id, app_info in self.all_apps.items():
                if app_id not in self.icons:
                    self._add_app_to_flowbox(app_info, app_id)
            self.update_flowbox()

        def update_flowbox(self):
            """Synchronizes grid UI with installed apps and usage history."""
            self.all_apps = self.scanner.scan()
            current_installed_apps = self.all_apps
            recent_app_ids = self.get_recent_apps()

            # Mass removal of remote widgets
            # Using list() to avoid mutation issues, then clearing
            if self.remote_widgets:
                for widget in list(self.remote_widgets):
                    if widget.get_parent() == self.flowbox:
                        self.flowbox.remove(widget)
                self.remote_widgets.clear()

            # Handle uninstalled apps
            apps_to_remove = set(self.icons.keys()) - set(current_installed_apps.keys())
            if apps_to_remove:
                for app_id in apps_to_remove:
                    widget_data = self.icons.pop(app_id, None)
                    if widget_data:
                        vbox = widget_data["vbox"]
                        flowbox_child = vbox.get_parent()
                        if flowbox_child and flowbox_child.get_parent() == self.flowbox:
                            self.flowbox.remove(flowbox_child)

                # Reclaim memory from uninstalled app icons immediately
                self._panel_instance.gc.collect()

            for app_id, app in current_installed_apps.items():
                if app_id not in self.icons:
                    self._add_app_to_flowbox(app, app_id)

            # Sort logic...
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
                key=lambda app_id: current_installed_apps[app_id].get_name().lower(),
            )
            desired_app_id_order.extend(non_recent_apps)
            self.desired_app_order = desired_app_id_order

            self.flowbox.invalidate_sort()
            self.flowbox.invalidate_filter()

        def _finalize_popover_setup(self, is_initial_setup=False):
            """Applies final layout sizing to the popover."""
            min_size, natural_size = self.flowbox.get_preferred_size()
            width = natural_size.width if natural_size else 0
            self.scrolled_window.set_size_request(
                self.popover_width, self.popover_height
            )
            self.scrolled_window.set_min_content_width(width)
            self.scrolled_window.set_min_content_height(self.min_app_grid_height)
            if self.popover_launcher:
                self.popover_launcher.set_parent(self.appmenu)
                if not is_initial_setup:
                    self.popover_launcher.popup()

        def on_keypress(self, *_):
            """Launches the searched application escaping the sandbox if needed."""
            if not self.search_get_child:
                return

            desktop_id = f"{self.search_get_child}.desktop"
            app_info = self.all_apps.get(desktop_id)

            if app_info:
                exec_cmd = app_info.get_exec()
                if not exec_cmd:
                    return

                cmd_parts = [p for p in exec_cmd.split() if not p.startswith("%")]

                if os.path.exists("/.flatpak-info"):
                    final_cmd = ["flatpak-spawn", "--host"] + cmd_parts
                else:
                    final_cmd = cmd_parts

                import subprocess

                try:
                    subprocess.Popen(final_cmd)
                    self.add_recent_app(desktop_id)
                except Exception as e:
                    self.logger.error(f"AppLauncher: Launch failed: {e}")

            if self.popover_launcher:
                self.popover_launcher.popdown()

        def _add_app_to_flowbox(self, app, app_id):
            """Creates visual entry for an application and adds to grid."""
            keywords = (
                " ".join(app.get_keywords()) if hasattr(app, "get_keywords") else ""
            )
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
                vbox.add_css_class("app-launcher-vbox")
                vbox.MYTEXT = (display_name, cmd, keywords, False)
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
                vbox.append(image)
                vbox.append(label)
                gesture = self.gtk.GestureClick.new()
                gesture.set_button(self.gdk.BUTTON_SECONDARY)
                gesture.connect(
                    "pressed", self.menu_handler.on_right_click_popover, vbox
                )
                vbox.add_controller(gesture)
                self.flowbox.append(vbox)

        def app_sort_func(self, child1, child2, user_data=None):
            """Orders applications based on the desired sort order."""
            v1, v2 = child1.get_child(), child2.get_child()
            if (
                not v1
                or not v2
                or not hasattr(v1, "MYTEXT")
                or not hasattr(v2, "MYTEXT")
            ):
                return 0

            data1, data2 = v1.MYTEXT, v2.MYTEXT
            app_id_1, app_id_2 = data1[1], data2[1]
            is_rem_1 = data1[3] if len(data1) > 3 else False
            is_rem_2 = data2[3] if len(data2) > 3 else False

            if is_rem_1 != is_rem_2:
                return 1 if is_rem_1 else -1

            try:
                index1 = self.desired_app_order.index(app_id_1)
            except ValueError:
                index1 = 999
            try:
                index2 = self.desired_app_order.index(app_id_2)
            except ValueError:
                index2 = 999
            return (index1 > index2) - (index1 < index2)

        def add_recent_app(self, app_id: str):
            """Proxies the application ID to the database manager."""
            self.recent_db.add_app(app_id)

        def get_recent_apps(self):
            """Retrieves recent application IDs from the database manager."""
            return self.recent_db.fetch_recent()

        def run_app_from_launcher(self, x, y):
            """Executes the selected application escaping the sandbox if needed."""
            selected = x.get_selected_children()
            if not selected:
                return
            vbox = selected[0].get_child()
            if not hasattr(vbox, "MYTEXT"):
                return

            data = vbox.MYTEXT
            desktop_id = data[1]
            is_remote = data[3] if len(data) > 3 else False

            if is_remote:
                return

            app_info = self.all_apps.get(desktop_id)
            if app_info:
                exec_cmd = app_info.get_exec()
                if not exec_cmd:
                    return

                cmd_parts = [p for p in exec_cmd.split() if not p.startswith("%")]

                if os.path.exists("/.flatpak-info"):
                    final_cmd = ["flatpak-spawn", "--host"] + cmd_parts
                else:
                    final_cmd = cmd_parts

                import subprocess

                try:
                    subprocess.Popen(final_cmd)
                    self.add_recent_app(desktop_id)
                except Exception as e:
                    self.logger.error(f"AppLauncher: Launch failed: {e}")

            if self.popover_launcher:
                self.popover_launcher.popdown()
            self.update_flowbox()

        def open_popover_launcher(self, *_):
            """Toggles the visibility of the launcher popover."""
            if self.popover_launcher:
                if self.popover_launcher.is_visible():
                    self.popover_launcher.popdown()
                else:
                    self.update_flowbox()
                    self.flowbox.unselect_all()
                    self.popover_launcher.popup()
                    self.searchbar.set_text("")

        def popover_is_open(self, *_):
            """Handles UI logic when the popover opens."""
            self.update_flowbox()
            self.set_keyboard_on_demand()
            vadjustment = self.scrolled_window.get_vadjustment()
            vadjustment.set_value(0)

        def popover_is_closed(self, *_):
            """Handles UI logic when the popover closes."""
            self.set_keyboard_on_demand(False)
            for widget in list(self.remote_widgets):
                if widget.get_parent():
                    self.flowbox.remove(widget)
            self.remote_widgets.clear()
            self.flowbox.invalidate_filter()

        def on_searchbar_key_release(self, widget, event):
            """Closes popover on Escape key press."""
            if event.keyval == self.gdk.KEY_Escape:
                if self.popover_launcher:
                    self.popover_launcher.popdown()
                return True
            return False

        def on_show_searchbar_action_actived(self, action, parameter):
            """Activates the search mode."""
            self.searchbar.set_search_mode(True)

        def on_search_entry_changed(self, searchentry):
            """Updates grid filter and schedules a remote search."""
            from gi.repository import GLib

            searchentry.grab_focus()
            if self.search_timeout_id:
                GLib.source_remove(self.search_timeout_id)
                self.search_timeout_id = None

            for widget in list(self.remote_widgets):
                if widget.get_parent():
                    self.flowbox.remove(widget)
            self.remote_widgets.clear()

            self.flowbox.invalidate_filter()
            query = searchentry.get_text().strip().lower()
            if len(query) >= 3:
                self.search_timeout_id = GLib.timeout_add(
                    350, self.remote_apps._trigger_remote_search, query
                )

        def manage_local_app(self, app_id, app_info):
            """Opens the Uninstall Window for local Flatpaks."""
            hit_data = {
                "name": app_info.get_name(),
                "_local_icon": None,  # AppScanner info usually handles icon differently
            }

            FlatpakUninstallWindow(self, hit_data, app_id)

            def configure_uninstall_view():
                id_found = self.view_id_found(title="Flatpak Uninstaller")
                if id_found:
                    self.wf_helper.center_view_on_output(id_found[0], 800, 710)

            self.glib.timeout_add(150, configure_uninstall_view)

        def install_remote_app(self, hit: dict):
            """Triggers installation and closes the launcher popover."""
            self.menu_handler.pkg_helper.install_flatpak(hit)
            if self.popover_launcher:
                self.popover_launcher.popdown()

            def configure_view_later():
                id_found = self.view_id_found(title="Flatpak Installer")
                if id_found:
                    id = id_found[0]
                    self.wf_helper.center_view_on_output(id, 800, 710)

            self.glib.timeout_add(100, configure_view_later)

        def on_filter_invalidate(self, row):
            """Filters based on search query and the ignore list."""
            text_to_search = self.searchbar.get_text().strip().lower()
            child = row.get_child()

            if not child or not hasattr(child, "MYTEXT"):
                return False

            data = child.MYTEXT
            display_name, desktop_id, keywords = data[0], data[1], data[2]
            is_remote = data[3] if len(data) > 3 else False

            if is_remote:
                return True

            ignored_list = self.get_plugin_setting(["behavior", "ignored_apps"], [])
            if not self.show_ignored and desktop_id in ignored_list:
                return False

            combined_text = f"{display_name} {desktop_id} {keywords}".lower()
            if text_to_search in combined_text:
                self.search_get_child = desktop_id.split(".desktop")[0]
                return True
            return False

    return AppLauncher
