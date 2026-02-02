def get_plugin_metadata(_):
    about = """
            A system dashboard for quick access to system actions,
            power management, and settings.
            """
    return {
        "id": "org.waypanel.plugin.window_controls",
        "name": "Window Controls",
        "version": "1.0.0",
        "enabled": True,
        "index": 1,
        "priority": 985,
        "container": "top-panel-after-systray",
        "deps": ["css_generator"],
        "description": about,
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

            self.cf_box.append(self.minimize_button)  # pyright: ignore
            self.cf_box.append(self.maximize_button)  # pyright: ignore
            self.cf_box.append(self.close_button)  # pyright: ignore
            self.gtk_helper.add_cursor_effect(self.cf_box)

            self.cf_box.add_css_class("window-controls-box")
            self.plugins["css_generator"].install_css("window-controls.css")

        def create_control_button(self, icon_name, css_class, callback):
            button = self.gtk_helper.create_button(
                icon_name,
                "",
                css_class,
                False,
                use_function=callback,  # pyright: ignore
            )
            return button

        def maximize_last_focused_view(self, *_):
            view_id = self._wf_helper.get_the_last_focused_view_id(skip_maximized=True)
            self.ipc.set_view_minimized(view_id, False)
            self.ipc.assign_slot(view_id, "slot_c")

        def _on_close_clicked(self, vid):
            self.glib.timeout_add_seconds(3, self.wf_helper._check_hanging_process, vid)

        def close_last_focused_view(self, *_):
            view_id = self._wf_helper.get_the_last_focused_view_id()
            self.ipc.close_view(view_id)
            self._on_close_clicked(view_id)

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
        #     if id in self.ipc.list_view_ids():
        #         self.ipc.unhide_view(id)
        #         # ***Warning*** this was freezing the panel
        #         # set focus will return an Exception in case the view is not toplevel
        #         GLib.idle_add(lambda *_: self.utils.focus_view_when_ready(view))
        #         if self.utils.widget_exists(widget):
        #             self.update_widget_safely(self.top_panel_box_center.remove, widget)

    return WindowControlsPlugin
