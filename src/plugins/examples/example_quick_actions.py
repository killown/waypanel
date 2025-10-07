def get_plugin_metadata(_):
    return {
        "enabled": True,
        "container": "top-panel-center",
        "index": 900,
        "deps": ["top_panel"],
    }


def get_plugin_class():
    import os
    from src.plugins.core._base import BasePlugin

    class QuickActionsPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover = None

            self.menu_button = self.gtk.MenuButton()
            self.menu_button.set_icon_name("system-shutdown-symbolic")
            self.menu_button.add_css_class("quick-actions-button")

            self.main_widget = (self.menu_button, "append")

            self.create_menu_popover()

        def create_menu_popover(self):
            self.popover = self.gtk.Popover()
            vbox = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL, spacing=6)

            actions = [
                ("Lock Screen", self.lock_screen),
                ("Log Out", self.logout),
                ("Restart", self.restart),
                ("Shut Down", self.shutdown),
            ]

            for label, callback in actions:
                button = self.gtk.Button(label=label)
                button.connect("clicked", callback)
                vbox.append(button)

            self.popover.set_child(vbox)
            self.menu_button.set_popover(self.popover)

        def lock_screen(self, _):
            os.system("loginctl lock-session &")

        def logout(self, _):
            os.system("swaymsg exit &")

        def restart(self, _):
            os.system("systemctl reboot &")

        def shutdown(self, _):
            os.system("systemctl poweroff &")

        def about(self):
            """A plugin that provides a popover menu with quick actions to control the system (e.g., lock, log out, shut down)."""
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin creates a quick actions menu with buttons to control the system.
            It's designed to be a convenient one-click way for users to lock their screen,
            log out, restart, or shut down.

            The core logic is centered on **popover menu creation and system command execution**:

            1.  **UI Creation**: It creates a `Gtk.MenuButton` and a `Gtk.Popover` widget.
                The button acts as the anchor for the popover menu.
            2.  **Action Buttons**: Inside the popover, it dynamically creates buttons
                for common actions like "Lock Screen" and "Shut Down."
            3.  **Command Execution**: Each button is connected to a handler method that
                executes a corresponding shell command using `os.system()`. For example,
                the "Shut Down" button runs `systemctl poweroff`.
            4.  **Placement**: The `get_plugin_metadata` function sets the plugin's
                position on the `top-panel-center`, with a high order to place it
                to the right of other plugins.
            """
            return self.code_explanation.__doc__

    return QuickActionsPlugin
