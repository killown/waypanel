def get_plugin_metadata(_):
    about = ("A system dashboard providing quick access to common system actions",)
    return {
        "id": "org.waypanel.plugin.exit_dashboard",
        "name": "Exit Dashboard",
        "version": "1.0.0",
        "enabled": True,
        "index": 99,
        "container": "top-panel-systray",
        "deps": [
            "top_panel",
        ],
        "description": about,
    }


def get_plugin_class():
    import psutil
    from src.plugins.core._base import BasePlugin

    SYSTEM_BUTTON_CONFIG = {
        "Logout": {
            "icons": ["system-log-out-symbolic", "gnome-logout-symbolic"],
        },
        "Reboot": {
            "icons": ["system-reboot-update-symbolic", "system-reboot-symbolic"],
        },
        "Shutdown": {
            "icons": ["gnome-shutdown-symbolic", "system-shutdown-symbolic"],
        },
        "Suspend": {
            "icons": ["system-suspend-hibernate-symbolic", "system-suspend-symbolic"],
        },
        "Lock": {
            "icons": ["system-lock-screen-symbolic", "lock-symbolic"],
        },
        "Exit Waypanel": {
            "icons": ["application-exit-symbolic", "application-exit", "exit"],
        },
        "Restart Waypanel": {
            "icons": ["system-restart-symbolic", "system-restart-panel"],
        },
        "Settings": {
            "icons": [
                "settings-configure-symbolic",
                "systemsettings-symbolic",
                "settings",
                "system-settings-symbolic",
                "preferences-activities-symbolic",
                "preferences-system",
            ],
        },
    }

    class ExitDashboard(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.plugin_css_class = self.get_plugin_setting_add_hint(
                ["layout", "css_class"],
                "exit-dashboard-widget",
                "The base CSS class applied to the button and popover widgets for styling via the theme.",
            )
            self.dashboard_columns = self.get_plugin_setting_add_hint(
                ["layout", "max_buttons_per_row"],
                3,
                "The number of system action buttons to display horizontally in the popover dashboard.",
            )
            self.restart_delay_seconds = self.get_plugin_setting_add_hint(
                ["timing", "restart_delay_seconds"],
                0.1,
                "Delay (in seconds) before executing the Waypanel restart command, allowing the kill signal to process first.",
            )
            self.exit_waypanel_command = self.get_plugin_setting_add_hint(
                ["commands", "exit_waypanel"],
                "pkill -f waypanel/main.py",
                "Command to immediately stop all Waypanel processes.",
            )
            self.restart_waypanel_command = self.get_plugin_setting_add_hint(
                ["commands", "restart_waypanel"],
                "waypanel &",
                "Command to launch a new Waypanel instance after a delay.",
            )
            self.logout_command = self.get_plugin_setting_add_hint(
                ["commands", "logout"],
                "wayland-logout",
                "Command to end the Wayland session (e.g., to return to the display manager).",
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
                """swaylock --screenshots --clock --indicator --grace-no-mouse --indicator-radius 99 --indicator-thickness 6 --effect-blur 7x5 --effect-vignette -1.5:0.5 --ring-color ffffff --key-hl-color 880032 --line-color 00000000 --inside-color 00000087 --separator-color 00000000 --grace 1 --fade-in 4""",
                "The full command used to lock the screen (defaults to a complex swaylock command, change this to your preferred locker).",
            )
            self.system_button_config = self.get_plugin_setting_add_hint(
                ["buttons", "system_actions"],
                SYSTEM_BUTTON_CONFIG,
                "A dictionary structure to override the default system action buttons, including labels, icons, and summaries. Use this to customize the dashboard buttons.",
            )
            self.popover_dashboard = None
            self.panel_instance = panel_instance
            self.menubutton_dashboard = None

        def add_css_class_to_children(self, widget):
            """Recursively add the plugin's CSS class to the widget and all its children."""
            if hasattr(widget, "add_css_class"):
                widget.add_css_class(self.plugin_css_class)
            if hasattr(widget, "get_children"):
                for child in widget.get_children():
                    self.add_css_class_to_children(child)
            elif hasattr(widget, "get_child") and widget.get_child():
                self.add_css_class_to_children(widget.get_child())

        def on_start(self):
            self.create_menu_popover_system()
            if self.menubutton_dashboard:
                self.menubutton_dashboard.add_css_class(self.plugin_css_class)

        def message(self, msg):
            dialog = self.gtk.MessageDialog(
                transient_for=None,
                message_type=self.gtk.MessageType.INFO,
                buttons=self.gtk.ButtonsType.NONE,
                text=msg,
            )
            close_btn = self.gtk.Button(label="_Close", use_underline=True)
            close_btn.connect("clicked", lambda *_: dialog.close())
            dialog.get_message_area().append(close_btn)  # pyright: ignore
            self.add_css_class_to_children(dialog)
            dialog.show()

        def launch_settings(self):
            control_center = self.plugins["control_center"]
            control_center.do_activate()

        def get_system_list(self):
            devices = (
                self.subprocess.check_output("systemctl devices".split())
                .decode()
                .strip()
                .split("\n")
            )
            return [" ".join(i.split(" ")[1:]) for i in devices]

        def create_menu_popover_system(self):
            self.menubutton_dashboard = self.gtk.Button()
            self.main_widget = (self.menubutton_dashboard, "append")
            self.menubutton_dashboard.connect("clicked", self.open_popover_dashboard)
            icon_name = self.gtk_helper.set_widget_icon_name(
                "exit-symbolic",
                [
                    "exit-symbolic",
                    "application-exit-symbolic",
                ],
            )
            self.menubutton_dashboard.set_icon_name(icon_name)
            self.gtk_helper.add_cursor_effect(self.menubutton_dashboard)
            self.menubutton_dashboard.add_css_class("exit-dashboard-button")
            self.menubutton_dashboard.add_css_class(self.plugin_css_class)
            return self.menubutton_dashboard

        def create_popover_system(self, *_):
            """
            Creates the system dashboard popover using the reusable helper method
            self.create_dashboard_popover and the global configuration data.
            """
            if not self.menubutton_dashboard:
                self.logger.error("menubutton_dashboard not initialized.")
                return
            self.popover_dashboard = self.create_dashboard_popover(
                parent_widget=self.menubutton_dashboard,
                popover_closed_handler=self.popover_is_closed,
                popover_visible_handler=self.popover_is_open,
                action_handler=self.on_action,
                button_config=self.system_button_config,
                module_name="exit-dashboard",
                max_children_per_line=self.dashboard_columns,
            )
            self.add_css_class_to_children(self.popover_dashboard)
            return self.popover_dashboard

        def on_system_clicked(self, device, *_):
            device_id = device.split()[0]
            cmd = "systemctl connect {0}".format(device_id).split()
            self.subprocess.Popen(cmd)
            connected_devices = "systemctl info".split()
            try:
                connected_devices = self.subprocess.check_output(
                    connected_devices
                ).decode()
            except Exception as e:
                self.logger.error(f"{e}")
                return
            if device_id in connected_devices:
                cmd = "systemctl disconnect {0}".format(device_id).split()
                self.subprocess.Popen(cmd)

        def run_app_from_dashboard(self, x):
            selected_text, filename = x.get_child().MYTEXT
            cmd = "gtk-launch {}".format(filename)
            self.cmd.run(cmd)
            self.popover_dashboard.popdown()  # pyright: ignore

        def open_popover_dashboard(self, *_):
            if self.popover_dashboard and self.popover_dashboard.is_visible():
                self.popover_dashboard.popdown()
            elif self.popover_dashboard and not self.popover_dashboard.is_visible():
                self.popover_dashboard.popup()
            elif not self.popover_dashboard:
                self.popover_dashboard = self.create_popover_system()

        def kill_process_by_name(self, name):
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if name in proc.info["name"]:
                        proc.kill()
                        self.logger.info(
                            f"Killed process {proc.info['name']} with PID {proc.info['pid']}"
                        )
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    pass

        def run_later(self, command, delay):
            self.subprocess.Popen(["bash", "-c", f"sleep {delay} && {command}"])

        def on_action(self, button, action):
            if action == "Exit Waypanel":
                self.subprocess.Popen(self.exit_waypanel_command.split())
            if action == "Restart Waypanel":
                self.run_later(
                    self.restart_waypanel_command, self.restart_delay_seconds
                )
            if action == "Logout":
                self.subprocess.Popen(self.logout_command.split())
            if action == "Shutdown":
                self.subprocess.Popen(self.shutdown_command.split())
            if action == "Suspend":
                self.subprocess.Popen(self.suspend_command.split())
            if action == "Reboot":
                self.subprocess.Popen(self.reboot_command.split())
            if action == "Lock":
                self.subprocess.Popen(self.lock_command.split())
            if action == "Settings":
                self.launch_settings()
                self.popover_dashboard.popdown()  # pyright: ignore

        def popover_is_open(self, *_):
            return

        def popover_is_closed(self, *_):
            return

        def on_show_searchbar_action_actived(self, action, parameter):
            self.searchbar.set_search_mode(True)  # pyright: ignore

        def code_explanation(self):
            """
            This plugin creates a popover-based user interface for managing system-level actions.
            The system actions are defined in a configuration dictionary (`self.system_button_config`),
            and the UI generation logic is delegated to the reusable helper method (`self.create_dashboard_popover`)
            provided by the BasePlugin.
            Key elements now controlled by configuration settings:
            - **`max_buttons_per_row`**: Controls the grid layout columns.
            - **`timing/restart_delay_seconds`**: Controls the delay for the Waypanel restart command.
            - **All System Commands**: The underlying shell commands for 'Shutdown', 'Reboot', 'Lock', 'Logout', 'Exit Waypanel', and 'Restart Waypanel' are all exposed as separate configuration settings (e.g., `commands/lock_screen`) to support various display managers or lockers (like GDM, SDDM, or swaylock).
            - **`buttons/system_actions`**: Allows users to entirely customize the labels, icons, and summaries of the dashboard buttons.
            The plugin's core methods are:
            1. `create_menu_popover_system`: Sets up the panel button.
            2. `create_popover_system`: Calls the external helper to build the popover using configurable settings.
            3. `on_action`: Executes the configurable system command based on the button label.
            """
            return self.code_explanation.__doc__

    return ExitDashboard
