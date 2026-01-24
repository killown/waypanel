def get_plugin_metadata(_):
    """
    Returns the metadata for the Clipboard Client plugin.
    """
    about = (
        "This plugin serves as the graphical user interface (GUI) for the"
        "asynchronous clipboard history server. It allows users to view,"
        "search, and manage their clipboard history through a pop-up menu."
    )
    return {
        "id": "org.waypanel.plugin.clipboard",
        "name": "Clipboard Client",
        "version": "1.6.5",
        "enabled": True,
        "container": "top-panel-systray",
        "index": 5,
        "deps": ["top_panel", "clipboard_server"],
        "description": about,
    }


def get_plugin_class():
    """
    Returns the ClipboardClient class with necessary imports scoped inside.
    """
    from pathlib import Path
    from urllib.parse import unquote, urlparse
    from gi.repository import GdkPixbuf, Gtk, Gdk
    from src.plugins.core._base import BasePlugin
    from .clipboard_server import get_plugin_class as get_server_class
    from ._clipboard_template import Helpers
    from ._clipboard_helpers import ClipboardHelpers, ClipboardManager

    class ClipboardClient(BasePlugin):
        """
        GTK-based clipboard client handling history display and interaction.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.manager = ClipboardManager(panel_instance, get_server_class)
            self.popover_clipboard = None
            self.delete_btn_map = {}
            self.listbox = None
            self.clipboard_helper = ClipboardHelpers(self)
            self._is_populating = False

            self.popover_min_width = self.get_plugin_setting_add_hint(
                ["client", "popover_min_width"], 400, "Popover width"
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

            helpers = Helpers(self)
            helpers.apply_hints()
            self.main_icon = self.get_plugin_setting(
                ["main_icon"], "edit-paste-symbolic"
            )

        def on_enable(self):
            self.run_in_async_task(self.manager.initialize())
            self.create_clipboard_ui()

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
            display = Gdk.Display.get_default()
            if not display:
                return
            clipboard = display.get_clipboard()
            real_path = self._resolve_local_path(content)

            if real_path and self.clipboard_helper.is_image_content(real_path):
                try:
                    file_obj = self.gio.File.new_for_path(real_path)
                    texture = Gdk.Texture.new_from_file(file_obj)
                    texture_provider = Gdk.ContentProvider.new_for_value(texture)
                    file_provider = Gdk.ContentProvider.new_for_value(content)
                    self._active_clipboard_provider = Gdk.ContentProvider.new_union(
                        [texture_provider, file_provider]
                    )
                    clipboard.set_content(self._active_clipboard_provider)
                except Exception as e:
                    self.logger.error(f"Clipboard: Native image copy failed: {e}")
            else:
                self._active_clipboard_provider = Gdk.ContentProvider.new_for_value(
                    content
                )
                clipboard.set_content(self._active_clipboard_provider)

        async def populate_listbox_async(self):
            if self._is_populating:
                return
            self._is_populating = True
            try:
                while row := self.listbox.get_first_child():
                    self.listbox.remove(row)
                self.delete_btn_map.clear()
                history = await self.manager.get_history()
                if not history:
                    return

                for item in history:
                    item_id, content, label, is_pinned = (
                        item[0],
                        item[1],
                        item[2],
                        item[3],
                    )
                    thumbnail_stored = item[4] if len(item) > 4 else None

                    row_hbox = Gtk.Box(
                        orientation=Gtk.Orientation.HORIZONTAL, spacing=10
                    )
                    row_hbox.add_css_class("clipboard-row-hbox")
                    row_hbox.ITEM_ID = item_id
                    row_hbox.IS_PINNED = is_pinned
                    row_hbox.RAW_CONTENT = content

                    delete_btn = Gtk.Button.new_from_icon_name("edit-delete-symbolic")
                    delete_btn.add_css_class("clipboard-delete-button")
                    delete_btn.connect("clicked", self.on_delete_selected)
                    self.delete_btn_map[delete_btn] = item_id
                    row_hbox.append(delete_btn)

                    real_image_path = self._resolve_local_path(content)
                    if real_image_path and self.clipboard_helper.is_image_content(
                        real_image_path
                    ):
                        img_widget = Gtk.Image(pixel_size=self.thumbnail_size)
                        row_hbox.append(img_widget)
                        display_path = (
                            thumbnail_stored
                            if thumbnail_stored and Path(thumbnail_stored).exists()
                            else real_image_path
                        )
                        self._load_image_async(display_path, img_widget)
                    else:
                        display_text = (label if label else content)[
                            : self.preview_text_length
                        ]
                        lbl = Gtk.Label(label=display_text, xalign=0, hexpand=True)
                        lbl.add_css_class("clipboard-label-item")
                        row_hbox.append(lbl)

                    if is_pinned:
                        row_hbox.append(Gtk.Image.new_from_icon_name("pin-symbolic"))

                    row_widget = Gtk.ListBoxRow(child=row_hbox)
                    gesture = Gtk.GestureClick(button=3)
                    gesture.connect("pressed", self.on_right_click_row)
                    row_widget.add_controller(gesture)
                    self.listbox.append(row_widget)

            except Exception as e:
                self.logger.error(f"Clipboard: Population failed: {e}")
            finally:
                self._is_populating = False

        def _load_image_async(self, path, widget):
            def on_done(source, res, target):
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

        def create_clipboard_ui(self):
            self.button_clipboard = Gtk.Button()
            self.button_clipboard.add_css_class("panel-button")
            icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            icon_image = Gtk.Image.new_from_icon_name(
                self.gtk_helper.icon_exist(self.main_icon)
            )
            icon_box.append(icon_image)
            self.button_clipboard.set_child(icon_box)

            if hasattr(self.gtk_helper, "add_cursor_effect"):
                self.gtk_helper.add_cursor_effect(self.button_clipboard)

            self.popover_clipboard = Gtk.Popover()
            self.popover_clipboard.set_parent(self.button_clipboard)
            self.popover_clipboard.set_autohide(True)

            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            main_box.add_css_class("clipboard-main-container")

            self.searchbar = Gtk.SearchEntry(placeholder_text="Search...")
            self.searchbar.connect(
                "search_changed", lambda _: self.listbox.invalidate_filter()
            )

            self.sw = Gtk.ScrolledWindow(propagate_natural_height=True, vexpand=True)
            self.sw.set_max_content_height(max(self.popover_max_height, 100))
            self.sw.set_min_content_width(max(self.popover_min_width, 100))

            self.listbox = Gtk.ListBox()
            self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            self.listbox.connect("row-activated", self.on_copy_row)
            self.sw.set_child(self.listbox)

            btn_clear = Gtk.Button(label="Clear History")
            btn_clear.add_css_class("clipboard-button-clear")
            btn_clear.connect("clicked", self.on_clear_clicked)

            main_box.append(self.searchbar)
            main_box.append(self.sw)
            main_box.append(btn_clear)

            self.popover_clipboard.set_child(main_box)
            self.popover_clipboard.connect(
                "map", lambda _: self.update_clipboard_list()
            )

            def on_button_clicked(btn):
                if not btn.get_realized():
                    btn.realize()
                if self.popover_clipboard.get_visible():
                    self.popover_clipboard.popdown()
                else:
                    self.popover_clipboard.popup()

            self.button_clipboard.connect("clicked", on_button_clicked)
            self.main_widget = (self.button_clipboard, "append")

        def update_clipboard_list(self):
            self.run_in_async_task(self.populate_listbox_async())

        def on_copy_row(self, _, row):
            if not row:
                return
            content = row.get_child().RAW_CONTENT
            self.copy_to_clipboard(content)
            self.popover_clipboard.popdown()

        def on_delete_selected(self, btn):
            if iid := self.delete_btn_map.get(btn):
                self.run_in_async_task(self._do_delete(iid))

        async def _do_delete(self, iid):
            await self.manager.delete_item(iid)
            row = self.listbox.get_first_child()
            while row:
                if row.get_child().ITEM_ID == iid:
                    self.listbox.remove(row)
                    break
                row = row.get_next_sibling()

        def on_clear_clicked(self, *_):
            self.run_in_async_task(self._do_clear())

        async def _do_clear(self):
            await self.manager.clear_history()
            while row := self.listbox.get_first_child():
                self.listbox.remove(row)

        def on_right_click_row(self, gesture, *args):
            row = gesture.get_widget()
            child = row.get_child()

            menu = Gtk.Popover()
            menu.set_parent(row)
            menu.set_autohide(True)
            menu.connect("closed", lambda p: p.unparent())

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            vbox.set_margin_end(10)

            # Pin Toggle
            pin_label = "Unstick from Top" if child.IS_PINNED else "Stick to Top"
            btn_pin = Gtk.Button(label=pin_label)
            btn_pin.add_css_class("clipboard-menu-item-button")
            btn_pin.connect(
                "clicked", self.on_toggle_pin, child.ITEM_ID, child.IS_PINNED, menu
            )
            vbox.append(btn_pin)

            # Edit Label Section
            sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            vbox.append(sep)

            lbl_edit = Gtk.Label(label="Edit Alias:", xalign=0)
            vbox.append(lbl_edit)

            entry = Gtk.Entry()
            entry.set_placeholder_text("Enter label...")
            entry.connect(
                "activate", self.on_label_entry_activated, child.ITEM_ID, menu
            )
            vbox.append(entry)

            menu.set_child(vbox)
            if not row.get_realized():
                row.realize()
            menu.popup()

        def on_label_entry_activated(self, entry, iid, menu):
            label = entry.get_text().strip()
            menu.popdown()
            self.run_in_async_task(self._do_update_label(iid, label if label else None))

        async def _do_update_label(self, iid, label):
            await self.manager.update_item_label(iid, label)
            while row := self.listbox.get_first_child():
                self.listbox.remove(row)
            await self.populate_listbox_async()

        def on_toggle_pin(self, _, iid, pinned, menu):
            menu.popdown()
            self.run_in_async_task(self._do_toggle_pin(iid, pinned))

        async def _do_toggle_pin(self, iid, pinned):
            await self.manager.update_item_pin_status(iid, not pinned)
            while row := self.listbox.get_first_child():
                self.listbox.remove(row)
            await self.populate_listbox_async()

        def on_disable(self):
            self.run_in_async_task(self.manager.server.stop())

    return ClipboardClient
