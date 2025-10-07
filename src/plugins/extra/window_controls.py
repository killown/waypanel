def get_plugin_metadata(_):
    return {
        "enabled": True,
        "index": 1,
        "container": "top-panel-after-systray",
        "deps": [
            "top_panel",
        ],
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class WindowControlsPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

            self.last_toplevel_focused_view = None
            self.cf_box = self.gtk.Box()
            self.main_widget = (self.cf_box, "append")
            self.maximize_button = self.create_control_button(
                "window-maximize-symbolic",
                "window-controls-maximize-button",
                self.maximize_last_focused_view,
            )

            self.close_button = self.create_control_button(
                "window-close-symbolic",
                "window-controls-close-button",
                self.close_last_focused_view,
            )

            self.minimize_button = self.create_control_button(
                "window-minimize-symbolic",
                "window-controls-minimize-button",
                self.minimize_view,
            )

            self.cf_box.append(self.minimize_button)
            self.cf_box.append(self.maximize_button)
            self.cf_box.append(self.close_button)
            self.gtk_helper.add_cursor_effect(self.cf_box)

            self.cf_box.add_css_class("window-controls-box")

        def create_control_button(self, icon_name, css_class, callback):
            button = self.gtk_helper.create_button(
                icon_name, None, css_class, None, use_function=callback
            )
            return button

        def maximize_last_focused_view(self, *_):
            view_id = self._wf_helper.get_the_last_focused_view_id(skip_maximized=True)
            self.ipc.set_view_minimized(view_id, False)
            self.ipc.assign_slot(view_id, "slot_c")

        def close_last_focused_view(self, *_):
            view_id = self._wf_helper.get_the_last_focused_view_id()
            self.ipc.close_view(view_id)

        def minimize_view(self, *_):
            view_id = self._wf_helper.get_the_last_focused_view_id(skip_minimized=True)
            self.ipc.set_view_minimized(view_id, True)

        # # Hide desktop-environment views with unknown type
        # for view in self.ipc.list_views():
        # if view["role"] == "desktop-environment" and view["type"] == "unknown":
        # self.hide_view_instead_closing(view, ignore_toplevel=True)

        # def hide_view_instead_closing(self, view, ignore_toplevel=None):
        #     if view:
        #         if view["role"] != "toplevel" and ignore_toplevel is None:
        #             return
        #         button = Gtk.Button()
        #         button.connect("clicked", lambda widget: self.on_hidden_view(widget, view))
        #         self.update_widget_safely(self.obj.top_panel_box_center.append, button)
        #         self.utils.handle_icon_for_button(view, button)
        #         self.ipc.hide_view(view["id"])
        #
        # def on_hidden_view(self, widget, view):
        #     id = view["id"]
        #     if id in self.ipc.list_ids():
        #         self.ipc.unhide_view(id)
        #         # ***Warning*** this was freezing the panel
        #         # set focus will return an Exception in case the view is not toplevel
        #         GLib.idle_add(lambda *_: self.utils.focus_view_when_ready(view))
        #         if self.utils.widget_exists(widget):
        #             self.update_widget_safely(self.top_panel_box_center.remove, widget)

        def about(self):
            """
            A system dashboard for quick access to system actions,
            power management, and settings.
            """
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin creates a popover-based user interface for managing
            system-level actions. It provides a single access point for
            common tasks such as logging out, shutting down, or accessing
            settings.

            Its core logic is centered on **dynamic UI generation and
            system command execution**:

            1.  **UI Generation**: It creates a popover with a grid of buttons.
                Each button represents a system action, and the plugin
                dynamically selects the most suitable icon for each.
            2.  **System Command Execution**: For each button, it executes a
                corresponding system command (e.g., `reboot`, `shutdown`)
                using `subprocess.Popen`, allowing it to interact with the
                underlying operating system.
            3.  **External Tool Integration**: It checks for an external
                application (`waypanel-settings`) and launches it if available,
                providing graceful error handling if the dependency is not met.
            4.  **Session Management**: It includes actions specifically for
                managing the panel's session, such as exiting and restarting
                the panel itself.
            """
            return self.code_explanation.__doc__

    return WindowControlsPlugin
