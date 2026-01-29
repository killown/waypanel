def get_plugin_metadata(panel_instance):
    """Retrieves metadata for the Taskbar plugin."""
    id = "org.waypanel.plugin.taskbar"
    container, id = panel_instance.config_handler.get_plugin_container(
        "bottom-panel-center", id
    )
    return {
        "id": id,
        "name": "Taskbar",
        "version": "1.7.0",
        "enabled": True,
        "container": container,
        "deps": [
            "event_manager",
            "gestures_setup",
            "on_output_connect",
            "view_property_controller",
            "css_generator",
        ],
        "description": "Fully modularized Taskbar with split logic files.",
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin
    from gi.repository import Gtk, GLib
    from .config import TaskbarConfig
    from .menu import TaskbarMenu
    from .ui import TaskbarUI
    from .events import TaskbarEvents
    from .views import TaskbarViews
    from .gestures import TaskbarGestures
    import re
    import gc

    class TitleFormatter:
        @staticmethod
        def clean(raw_title, max_len):
            if not raw_title:
                return ""

            words = raw_title.split(" ")
            filtered = []
            for word in words:
                clean = re.sub(r"[—]+", "", word).strip()
                if clean:
                    filtered.append(clean)

            full_title = " ".join(filtered)
            if len(full_title) > max_len:
                return full_title[: max_len - 3] + "..."
            return full_title

    class TaskbarPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self._debounce_pending = False
            self._debounce_timer_id = None
            self._debounce_interval = 100
            self.is_scale_active = {}
            self.button_pool = []
            self.in_use_buttons = {}
            self.group_popover = None
            self.group_last_focused = {}

            # Handlers
            self.config = TaskbarConfig(self)
            self.config.register_settings()
            self._init_settings_refs()

            self.ui_handler = TaskbarUI(self)
            self.menu_handler = TaskbarMenu(self)
            self.event_handler = TaskbarEvents(self)
            self.view_handler = TaskbarViews(self)
            self.gesture_handler = TaskbarGestures(self)

            self.event_handler.subscribe()

            self.ui_handler.create_main_layout()

            self.run_in_thread(self._initialize_button_pool, 15)
            self.main_widget = (self.center_box, "append")
            self.plugins["css_generator"].install_css("taskbar.css")

        def _init_settings_refs(self):
            """Syncs refs for compatibility."""
            self.icon_size = self.config.icon_size
            self.spacing = self.config.spacing
            self.show_label = self.config.show_label
            self.max_title_length = self.config.max_title_length
            self.group_apps = self.config.group_apps
            self.hide_ungrouped_titles = self.config.hide_ungrouped_titles
            self.show_focused_group_title = self.config.show_focused_group_title
            self.show_group_count = self.config.show_group_count

        def _initialize_button_pool(self, count: int) -> None:
            for _ in range(count):
                button = self._create_new_button()
                button.set_visible(False)
                self.button_pool.append({"view_id": "available", "button": button})

        def _create_new_button(self) -> Gtk.Button:
            button = self.ui_handler.create_button()
            self.gesture_handler.setup_button_gestures(button)
            return button

        def Taskbar(self) -> None:
            if self._debounce_timer_id:
                GLib.source_remove(self._debounce_timer_id)
                self._debounce_timer_id = None
            self._debounce_pending = False
            views = [
                v for v in self.ipc.list_views() if self.view_handler.is_valid_view(v)
            ]
            focused_view = self.ipc.get_focused_view()
            focused_id = focused_view.get("id") if focused_view else None

            if self.group_apps:
                grouped_data = {}
                for v in views:
                    grouped_data.setdefault(v.get("app-id"), []).append(v)
                for key in list(self.in_use_buttons.keys()):
                    if key not in grouped_data:
                        self.remove_button(key)
                for app_id, app_views in grouped_data.items():
                    is_focused = any(v.get("id") == focused_id for v in app_views)
                    representative = next(
                        (v for v in app_views if v.get("id") == focused_id), None
                    )
                    if not representative:
                        last_id = self.group_last_focused.get(app_id)
                        representative = next(
                            (v for v in app_views if v.get("id") == last_id),
                            app_views[0],
                        )
                    if app_id in self.in_use_buttons:
                        self.update_button(
                            self.in_use_buttons[app_id],
                            representative,
                            len(app_views),
                            is_focused,
                        )
                    else:
                        self.add_button_to_taskbar(representative, app_id)
            else:
                current_ids = {v.get("id") for v in views}
                for vid in list(self.in_use_buttons.keys()):
                    if vid not in current_ids:
                        self.remove_button(vid)
                for v in views:
                    vid = v.get("id")
                    if vid in self.in_use_buttons:
                        self.update_button(
                            self.in_use_buttons[vid], v, 1, vid == focused_id
                        )
                    else:
                        self.add_button_to_taskbar(v, vid)

        def add_button_to_taskbar(self, view: dict, identifier: str):
            button = next(
                (i["button"] for i in self.button_pool if i["view_id"] == "available"),
                None,
            )
            if not button:
                button = self._create_new_button()
                self.button_pool.append({"view_id": identifier, "button": button})
            else:
                for item in self.button_pool:
                    if item["button"] == button:
                        item["view_id"] = identifier
            button.view_id = view.get("id")  # pyright: ignore

            self.taskbar.append(button)  # pyright: ignore

            self.in_use_buttons[identifier] = button
            self.update_button(button, view)
            button.set_visible(True)

            # Use the method directly from the instance to maintain signal connection integrity
            try:
                button.disconnect_by_func(self._on_primary_click)
            except Exception:
                pass

            button.connect("clicked", self._on_primary_click, identifier)
            self.gtk_helper.add_cursor_effect(button)

        def _on_primary_click(self, button, identifier):
            views = [
                v for v in self.ipc.list_views() if self.view_handler.is_valid_view(v)
            ]
            target_views = [
                v
                for v in views
                if (
                    v.get("app-id") == identifier
                    if self.config.group_apps
                    else v.get("id") == identifier
                )
            ]
            if not target_views:
                return
            if len(target_views) == 1:
                self.view_handler.set_view_focus(target_views[0])
            else:
                self._show_group_popover(button, target_views)

        def _show_group_popover(self, button, views):
            if self.group_popover:
                self.group_popover.unparent()
            self.group_popover = Gtk.Popover()
            self.group_popover.set_parent(button)
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            focused_id = (self.ipc.get_focused_view() or {}).get("id")
            for v in views:
                row = Gtk.Button(has_frame=False)
                row.set_halign(Gtk.Align.START)
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                if v.get("id") == focused_id:
                    row.add_css_class("focused-group-item")
                    indicator = Gtk.Image.new_from_icon_name("go-next-symbolic")
                    indicator.set_pixel_size(12)
                    hbox.append(indicator)
                img = Gtk.Image.new_from_icon_name(
                    self.gtk_helper.icon_exist(v.get("app-id"))
                )
                lbl = Gtk.Label(label=TitleFormatter.clean(v.get("title", ""), 25))
                hbox.append(img)
                hbox.append(lbl)
                row.set_child(hbox)

                # FIXED: Removed duplicate "clicked" argument
                row.connect(
                    "clicked",
                    lambda *_, view=v: [
                        self.view_handler.set_view_focus(view),
                        self.group_popover.popdown(),
                    ],
                )
                vbox.append(row)
            self.group_popover.set_child(vbox)
            self.group_popover.popup()

        def remove_button(self, identifier: str) -> None:
            btn = self.in_use_buttons.pop(identifier, None)
            if btn:
                # 1. Detach from the UI to stop layout math
                self.taskbar.remove(btn)

                # 2. Reset internal references that hold large data
                btn.set_visible(False)
                btn.view_id = None

                # IMPORTANT: If your button has an image/icon, reset it to a null state
                # to release the GdkTexture/Pixbuf back to the system.
                if hasattr(btn, "set_icon_name"):
                    btn.set_icon_name("image-missing-symbolic")

                # 3. Mark as available in the pool
                for item in self.button_pool:
                    if item["button"] == btn:
                        item["view_id"] = "available"

                # 4. Force GC to break the circular references from the
                # gestures/popovers connected to this specific view ID.
                gc.collect()

        def update_button(
            self, btn, view: dict, count: int = 1, is_focused: bool = False
        ) -> None:
            raw_title = view.get("title", "")
            btn.set_tooltip_text(raw_title)
            btn.view_id = view.get("id")
            ico = self.ipc.get_view_property(btn.view_id, "icon")
            if not isinstance(ico, str):
                ico = self.gtk_helper.icon_exist(view.get("app-id"))  # pyright: ignore
            btn.icon.set_from_icon_name(ico)
            btn.icon.set_pixel_size(self.icon_size)
            if not self.show_label:
                btn.label.set_visible(False)
                return
            if self.group_apps:
                if is_focused and self.show_focused_group_title:
                    title = TitleFormatter.clean(raw_title, self.max_title_length)
                    label_text = (
                        f"({count}) {title}"
                        if (count > 1 and self.show_group_count)
                        else title
                    )
                    btn.label.set_label(label_text)
                    btn.label.set_visible(True)
                elif count > 1 and self.show_group_count:
                    btn.label.set_label(f"({count})")
                    btn.label.set_visible(True)
                else:
                    btn.label.set_visible(False)
            else:
                if self.hide_ungrouped_titles:
                    btn.label.set_visible(False)
                else:
                    title = TitleFormatter.clean(raw_title, self.max_title_length)
                    btn.label.set_label(title)
                    btn.label.set_visible(True)

        def on_view_focused(self, view: dict) -> None:
            self.view_handler.handle_focus_change(view)

    return TaskbarPlugin
