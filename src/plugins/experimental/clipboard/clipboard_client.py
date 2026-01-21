def get_plugin_metadata(_):
    about = (
        "This plugin serves as the graphical user interface (GUI) for the"
        "asynchronous clipboard history server. It allows users to view,"
        "search, and manage their clipboard history through a pop-up menu."
    )
    return {
        "id": "org.waypanel.plugin.clipboard",
        "name": "Clipboard Client",
        "version": "1.5.0",
        "enabled": True,
        "container": "top-panel-systray",
        "index": 5,
        "deps": ["top_panel", "clipboard_server"],
        "description": about,
    }


def get_plugin_class():
    from pathlib import Path
    from urllib.parse import unquote, urlparse
    import pyperclip
    from gi.repository import GdkPixbuf, Gio, GLib
    from src.plugins.core._base import BasePlugin
    from .clipboard_server import get_plugin_class as get_server_class
    from ._clipboard_template import Helpers
    from ._clipboard_helpers import ClipboardHelpers, ClipboardManager

    class ClipboardClient(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.manager = ClipboardManager(panel_instance, get_server_class)
            self.popover_clipboard = None
            self.delete_btn_map = {}
            self.listbox = None
            self.clipboard_helper = ClipboardHelpers(self)
            self.gio = Gio
            self.glib = GLib

            self._is_populating = False
            self._popover_visible = False

            self.popover_min_width = self.get_plugin_setting_add_hint(
                ["client", "popover_min_width"], 750, "Popover width"
            )
            self.popover_max_height = self.get_plugin_setting_add_hint(
                ["client", "popover_max_height"], 600, "Popover max height"
            )
            self.thumbnail_size = self.get_plugin_setting_add_hint(
                ["client", "thumbnail_size"], 250, "Image thumbnail size"
            )
            self.preview_text_length = self.get_plugin_setting_add_hint(
                ["client", "preview_text_length"], 50, "Text preview limit"
            )
            self.image_row_height = self.get_plugin_setting_add_hint(
                ["client", "image_row_height"], -1, "Min row height for images"
            )

            helpers = Helpers(self)
            helpers.apply_hints()
            self.main_icon = self.get_plugin_setting(
                ["main_icon"], "edit-paste-symbolic"
            )

        def on_enable(self):
            self.run_in_async_task(self.manager.initialize())
            self.create_popover_menu_clipboard()

        def _resolve_local_path(self, content: str) -> str | None:
            if not content or not content.startswith(("file://", "/")):
                return None
            clean_content = content.strip()
            path_candidate = (
                unquote(urlparse(clean_content).path)
                if clean_content.startswith("file://")
                else clean_content
            )
            return path_candidate if Path(path_candidate).exists() else None

        def copy_to_clipboard(self, content):
            real_path = self._resolve_local_path(content)
            if real_path and self.clipboard_helper.is_image_content(real_path):
                self.subprocess.run(
                    ["wl-copy", "-t", "image/png"], stdin=open(real_path, "rb")
                )
            else:
                pyperclip.copy(content)

        async def populate_listbox_async(self):
            """Fetches data and updates UI. Uses guards to prevent layout crashes."""
            if self._is_populating or not self._popover_visible:
                return

            self._is_populating = True
            try:
                history = await self.manager.get_history()

                # If popover closed while waiting for DB, abort UI work
                if not self._popover_visible:
                    return

                # UI Updates must be clean
                self.delete_btn_map.clear()
                while row := self.listbox.get_first_child():  # pyright: ignore
                    row.set_child(None)  # pyright: ignore
                    self.listbox.remove(row)  # pyright: ignore

                sorted_history = sorted(
                    history, key=lambda x: (x[3], x[0]), reverse=True
                )

                for item in sorted_history:
                    if not self._popover_visible:
                        break

                    item_id, content, label, is_pinned = (
                        item[0],
                        item[1],
                        item[2],
                        item[3],
                    )
                    thumbnail_stored = item[4] if len(item) > 4 else None

                    row_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 5)
                    row_hbox.add_css_class("clipboard-row-hbox")
                    row_hbox.ITEM_ID = item_id  # pyright: ignore
                    row_hbox.MYTEXT = f"{item_id} {content} {label if label else ''}"  # pyright: ignore
                    row_hbox.IS_PINNED = is_pinned  # pyright: ignore

                    delete_btn = self.gtk.Button.new_from_icon_name(
                        self.gtk_helper.icon_exist("tag-delete")
                    )
                    delete_btn.add_css_class("clipboard-delete-button")
                    delete_btn.connect("clicked", self.on_delete_selected)
                    self.delete_btn_map[delete_btn] = item_id
                    row_hbox.append(delete_btn)

                    real_image_path = self._resolve_local_path(content)
                    if real_image_path and self.clipboard_helper.is_image_content(
                        real_image_path
                    ):
                        img_widget = self.gtk.Image.new_from_icon_name(
                            "image-loading-symbolic"
                        )
                        img_widget.set_pixel_size(self.thumbnail_size)
                        img_widget.set_can_target(False)
                        row_hbox.append(img_widget)

                        display_path = (
                            thumbnail_stored
                            if thumbnail_stored and Path(thumbnail_stored).exists()
                            else real_image_path
                        )
                        self._load_image_async(display_path, img_widget)
                    else:
                        display_text = label if label else content
                        if len(display_text) > self.preview_text_length:
                            display_text = (
                                display_text[: self.preview_text_length] + "..."
                            )
                        lbl = self.gtk.Label.new(display_text)
                        lbl.add_css_class("clipboard-label-item")
                        lbl.set_halign(self.gtk.Align.START)
                        lbl.set_hexpand(True)
                        row_hbox.append(lbl)

                    if is_pinned:
                        row_hbox.append(
                            self.gtk.Image.new_from_icon_name("object-locked-symbolic")
                        )

                    row = self.gtk.ListBoxRow()
                    row.set_child(row_hbox)
                    gesture = self.gtk.GestureClick.new()
                    gesture.set_button(3)
                    gesture.connect("pressed", self.on_right_click_row)
                    row.add_controller(gesture)

                    self.listbox.append(row)  # pyright: ignore
            finally:
                self._is_populating = False

        def _load_image_async(self, path, widget):
            def on_done(source, res, target):
                if not self._popover_visible:
                    return
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(res)
                    target.set_from_pixbuf(pixbuf)
                except:
                    target.set_from_icon_name("image-missing")

            file_obj = self.gio.File.new_for_path(path)
            file_obj.read_async(
                self.glib.PRIORITY_DEFAULT,
                None,
                lambda obj, res: GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(
                    obj.read_finish(res),
                    self.thumbnail_size,
                    -1,
                    True,
                    None,
                    on_done,
                    widget,
                ),
            )

        def update_clipboard_list(self):
            if self._popover_visible:
                self.run_in_async_task(self.populate_listbox_async())

        def open_popover_clipboard(self, *_):
            if not self.popover_clipboard:
                self.popover_clipboard = self.create_popover_clipboard()

            self._popover_visible = True
            self.update_clipboard_list()
            self.popover_clipboard.popup()

        def create_popover_clipboard(self, *_):
            self.popover_clipboard = self.gtk.Popover.new()
            self.popover_clipboard.set_has_arrow(False)

            def on_popover_closed(*_):
                self._popover_visible = False
                self.set_keyboard_on_demand(False)

                # Explicitly remove the "active" or "hover" state from the button
                # This prevents the icon from staying highlighted
                self.menubutton_clipboard.unset_state_flags(self.gtk.StateFlags.FOCUSED)
                self.menubutton_clipboard.unset_state_flags(self.gtk.StateFlags.ACTIVE)

            self.popover_clipboard.connect("closed", on_popover_closed)
            self.popover_clipboard.connect(
                "notify::visible", lambda *_: self.set_keyboard_on_demand(True)
            )

            main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)
            self.searchbar = self.gtk.SearchEntry.new()
            self.searchbar.connect(
                "search_changed",
                lambda _: self.listbox.invalidate_filter(),  # pyright: ignore
            )
            main_box.append(self.searchbar)

            self.scrolled_window = self.gtk.ScrolledWindow()
            self.scrolled_window.set_min_content_width(self.popover_min_width)
            self.scrolled_window.set_max_content_height(self.popover_max_height)
            self.scrolled_window.set_propagate_natural_height(True)

            self.listbox = self.gtk.ListBox.new()
            self.listbox.connect("row-selected", self.on_copy_row)
            self.listbox.set_filter_func(
                lambda row: self.searchbar.get_text().lower()
                in row.get_child().MYTEXT.lower()
            )

            self.scrolled_window.set_child(self.listbox)
            main_box.append(self.scrolled_window)

            btn_clear = self.gtk.Button.new_with_label("Clear History")
            btn_clear.add_css_class("clipboard-button-clear")
            btn_clear.connect("clicked", self.on_clear_clicked)
            main_box.append(btn_clear)

            self.popover_clipboard.set_child(main_box)
            self.popover_clipboard.set_parent(self.menubutton_clipboard)
            return self.popover_clipboard

        def on_copy_row(self, _, row):
            if not row or not self._popover_visible or self._is_populating:
                return
            item_id = row.get_child().ITEM_ID
            self.run_in_async_task(self._do_copy(item_id))

        async def _do_copy(self, item_id):
            history = await self.manager.get_history()
            for item in history:
                if item[0] == item_id:
                    self.copy_to_clipboard(item[1])
                    self.popover_clipboard.popdown()  # pyright: ignore
                    break

        def on_delete_selected(self, btn):
            if iid := self.delete_btn_map.get(btn):
                self.run_in_async_task(self._do_delete(iid))

        async def _do_delete(self, iid):
            await self.manager.delete_item(iid)
            await self.populate_listbox_async()

        def on_clear_clicked(self, *_):
            self.run_in_async_task(self._do_clear())

        async def _do_clear(self):
            await self.manager.clear_history()
            await self.populate_listbox_async()

        def on_right_click_row(self, gesture, *args):
            row = gesture.get_widget()
            child = row.get_child()

            menu = self.gtk.Popover.new()
            menu.set_parent(row)
            menu.connect("closed", lambda p: p.unparent())

            label = "Unstick from Top" if child.IS_PINNED else "Stick to Top"
            icon = (
                "object-unlocked-symbolic"
                if child.IS_PINNED
                else "object-locked-symbolic"
            )

            btn = self.gtk.Button.new()
            btn.add_css_class("clipboard-menu-item-button")
            hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 10)
            hbox.add_css_class("clipboard-hbox-item")
            img = self.gtk.Image.new_from_icon_name(self.gtk_helper.icon_exist(icon))
            lbl = self.gtk.Label.new(label)
            lbl.add_css_class("clipboard-label-item")
            hbox.append(img)
            hbox.append(lbl)
            btn.set_child(hbox)

            btn.connect(
                "clicked", self.on_toggle_pin, child.ITEM_ID, child.IS_PINNED, menu
            )
            menu.set_child(btn)
            menu.popup()

        def on_toggle_pin(self, _, iid, pinned, menu):
            menu.popdown()
            self.run_in_async_task(self._do_toggle_pin(iid, pinned))

        async def _do_toggle_pin(self, iid, pinned):
            await self.manager.update_item_pin_status(iid, not pinned)
            # This ensures the list is rebuilt only after the DB is updated
            await self.populate_listbox_async()

        def create_popover_menu_clipboard(self):
            self.menubutton_clipboard = self.gtk.Button.new_from_icon_name(
                self.main_icon
            )
            self.main_widget = (self.menubutton_clipboard, "append")
            self.menubutton_clipboard.connect("clicked", self.open_popover_clipboard)

        def on_disable(self):
            self._popover_visible = False
            self.run_in_async_task(self.manager.server.stop())

    return ClipboardClient
