from .package_manager import PackageHelper


class AppMenuHandler:
    """Manages the application context menu logic and actions.

    Attributes:
        plugin (Any): Reference to the main plugin instance.
        logger (Any): Logger instance from the plugin.
        pkg_helper (PackageHelper): Helper for distribution package tasks.
    """

    def __init__(self, plugin):
        """Initializes the menu handler and discovery helper.

        Args:
            plugin: The AppLauncher plugin instance.
        """
        self.plugin = plugin
        self.logger = plugin.logger
        self.pkg_helper = PackageHelper(self.plugin)

    def on_right_click_popover(self, gesture, n_press, x, y, vbox):
        """Builds and displays the context menu for a specific app entry.

        Args:
            gesture: The Gtk gesture controller.
            n_press: Number of clicks detected.
            x: X coordinate of the click.
            y: Y coordinate of the click.
            vbox: The Gtk.Box containing the app entry data.
        """
        popover = self.plugin.gtk.Popover()
        popover.add_css_class("app-launcher-context-menu")
        
        menu_box = self.plugin.gtk.Box.new(self.plugin.gtk.Orientation.VERTICAL, 5)
        for margin in ["start", "end", "top", "bottom"]:
            getattr(menu_box, f"set_margin_{margin}")(10)

        # Handle unpacking safely for both 3-tuple (original) and 4-tuple (remote/updated) formats
        mytext = vbox.MYTEXT
        name, desktop_file, keywords = mytext[:3]
        is_remote = mytext[3] if len(mytext) > 3 else False
        
        dock_config = self.plugin.get_root_setting([self.plugin.dockbar_id], {})
        is_docked = any(
            v.get("desktop_file") == desktop_file 
            for v in dock_config.get("app", {}).values()
        )

        if is_docked:
            dock_btn = self.plugin.gtk.Button.new_with_label("Remove from dockbar")
            dock_btn.connect("clicked", self.remove_from_dockbar, desktop_file, popover)
        else:
            dock_btn = self.plugin.gtk.Button.new_with_label("Add to dockbar")
            dock_btn.connect("clicked", self.add_to_dockbar, name, desktop_file, popover)
        
        menu_box.append(dock_btn)

        edit_btn = self.plugin.gtk.Button.new_with_label("Open .desktop File")
        edit_btn.connect("clicked", self.open_desktop_file, desktop_file, popover)
        menu_box.append(edit_btn)

        if self.pkg_helper.is_supported():
            uninst_btn = self.plugin.gtk.Button.new_with_label("Uninstall")
            uninst_btn.connect("clicked", self.on_uninstall_clicked, desktop_file, popover)
            menu_box.append(uninst_btn)

        # Ignore/Unignore Logic
        ignored = self.plugin.get_plugin_setting(["behavior", "ignored_apps"], [])
        
        if desktop_file in ignored:
            unignore_btn = self.plugin.gtk.Button.new_with_label("Unignore App")
            unignore_btn.add_css_class("app-launcher-menu-item")
            unignore_btn.connect("clicked", self.unignore_app, desktop_file, popover)
            menu_box.append(unignore_btn)
        else:
            ignore_btn = self.plugin.gtk.Button.new_with_label("Ignore App")
            ignore_btn.add_css_class("app-launcher-menu-item")
            ignore_btn.connect("clicked", self.ignore_app, desktop_file, popover)
            menu_box.append(ignore_btn)

        popover.set_child(menu_box)
        popover.set_parent(vbox)
        popover.set_has_arrow(False)
        popover.popup()
        gesture.set_state(self.plugin.gtk.EventSequenceState.CLAIMED)

    def ignore_app(self, button, desktop_file, popover):
        """Adds the desktop file to the ignored list."""
        ignored = self.plugin.get_plugin_setting(["behavior", "ignored_apps"], [])
        if desktop_file not in ignored:
            ignored.append(desktop_file)
            self.plugin.set_plugin_setting(["behavior", "ignored_apps"], ignored)
        popover.popdown()
        self.plugin.update_flowbox()

    def unignore_app(self, button, desktop_file, popover):
        """Removes the desktop file from the ignored list."""
        ignored = self.plugin.get_plugin_setting(["behavior", "ignored_apps"], [])
        if desktop_file in ignored:
            ignored.remove(desktop_file)
            self.plugin.set_plugin_setting(["behavior", "ignored_apps"], ignored)
        popover.popdown()
        self.plugin.update_flowbox()

    def on_uninstall_clicked(self, button, desktop_file, popover):
        """Handler for the uninstall menu entry.

        Args:
            button: The Gtk.Button clicked.
            desktop_file: The identifier for the package.
            popover: The menu popover to close.
        """
        self.logger.info(f"AppLauncher: Uninstall button clicked for {desktop_file}")
        self.pkg_helper.uninstall(desktop_file)
        popover.popdown()
        if self.plugin.popover_launcher:
            self.plugin.popover_launcher.popdown()

    def add_to_dockbar(self, button, name, desktop_file, popover):
        """Adds an application to the dockbar settings."""
        import os
        wclass = os.path.splitext(desktop_file)[0]
        entry = {
            "cmd": f"gtk-launch {desktop_file.split('.desktop')[0]}",
            "icon": wclass,
            "wclass": wclass,
            "desktop_file": desktop_file,
            "name": name,
            "initial_title": name,
        }
        config = self.plugin.get_root_setting([self.plugin.dockbar_id], {})
        apps = config.get("app", {})
        apps[name] = entry
        config["app"] = apps
        self.plugin.config_handler.set_root_setting([self.plugin.dockbar_id], config)
        popover.popdown()

    def remove_from_dockbar(self, button, desktop_file, popover):
        """Removes an application from the dockbar settings."""
        config = self.plugin.get_root_setting([self.plugin.dockbar_id], {})
        apps = config.get("app", {})
        key = next((k for k, v in apps.items() if v.get("desktop_file") == desktop_file), None)
        if key:
            del apps[key]
            config["app"] = apps
            self.plugin.config_handler.set_root_setting([self.plugin.dockbar_id], config)
        popover.popdown()

    def open_desktop_file(self, button, desktop_file, popover):
        """Attempts to open the desktop file in a local text editor."""
        import os
        import shutil
        locations = [
            "/usr/share/applications/",
            self.plugin.os.path.expanduser("~/.local/share/applications/"),
        ]
        target = next((os.path.join(l, desktop_file) for l in locations if os.path.exists(os.path.join(l, desktop_file))), None)
        
        if target:
            editors = ["gedit", "code", "nvim", "nano"]
            for ed in editors:
                if shutil.which(ed):
                    cmd = f"{ed} {target}"
                    if hasattr(self.plugin, "cmd"):
                        self.plugin.cmd.run(cmd)
                    popover.popdown()
                    return