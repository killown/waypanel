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
        "version": "1.5.2",
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
    import pyperclip
    from gi.repository import GdkPixbuf
    from src.plugins.core._base import BasePlugin
    from .clipboard_server import get_plugin_class as get_server_class
    from ._clipboard_template import Helpers
    from ._clipboard_helpers import ClipboardHelpers, ClipboardManager

    class ClipboardClient(BasePlugin):
        """
        GTK-based clipboard client handling history display and interaction.
        """

        def __init__(self, panel_instance):
            """
            Initializes the client with configuration and managers.
            """
            super().__init__(panel_instance)
            self.manager = ClipboardManager(panel_instance, get_server_class)
            self.popover_clipboard = None
            self.delete_btn_map = {}
            self.listbox = None
            self.clipboard_helper = ClipboardHelpers(self)

            self._is_populating = False

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
            """
            Starts the server and creates the UI components.
            """
            self.run_in_async_task(self.manager.initialize())
            self.create_popover_menu_clipboard()

        def _resolve_local_path(self, content: str) -> str | None:
            """
            Resolves a string path or URI to a local file system path.
            """
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
            """
            Copies text or image files to the system clipboard.
            """
            real_path = self._resolve_local_path(content)
            if real_path and self.clipboard_helper.is_image_content(real_path):
                self.subprocess.run(
                    ["wl-copy", "-t", "image/png"], stdin=open(real_path, "rb")
                )
            else:
                pyperclip.copy(content)

        async def populate_listbox_async(self):
            """
            Compares DB history with current UI rows and appends only new items.
            """
            if self._is_populating:
                return

            self._is_populating = True
            try:
                history = await self.manager.get_history()

                existing_ids = set()
                row = self.listbox.get_first_child()  # pyright: ignore
                while row:
                    child = row.get_child()  # pyright: ignore
                    if hasattr(child, "ITEM_ID"):
                        existing_ids.add(child.ITEM_ID)
                    row = row.get_next_sibling()

                new_items = [item for item in history if item[0] not in existing_ids]

                if not new_items:
                    return

                for item in reversed(new_items):
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
                    delete_btn.set_focus_on_click(False)
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

                    row_widget = self.gtk.ListBoxRow()
                    row_widget.set_child(row_hbox)
                    row_widget.set_activatable(True)
                    row_widget.set_selectable(False)
                    gesture = self.gtk.GestureClick.new()
                    gesture.set_button(3)
                    gesture.connect("pressed", self.on_right_click_row)
                    row_widget.add_controller(gesture)

                    self.listbox.prepend(row_widget)  # pyright: ignore
            finally:
                self._is_populating = False

        def _load_image_async(self, path, widget):
            """
            Loads thumbnails asynchronously to avoid UI freezing.
            """

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

        def update_clipboard_list(self):
            """
            Triggers a background population of the history list.
            """
            self.run_in_async_task(self.populate_listbox_async())

        def create_popover_clipboard(self):
            """
            Constructs the Popover UI using the automated helper with proper return types.
            """
            self.popover_clipboard, self.scrolled_window, self.listbox = (  # pyright: ignore
                self.gtk_helper.create_popover(
                    parent_widget=self.button_clipboard,
                    has_arrow=False,
                    use_scrolled=True,
                    use_listbox=True,
                )
            )

            if self.listbox:
                self.listbox.connect("row-activated", self.on_copy_row)
            else:
                self.logger.critical(
                    "Widget listbox returned None, clipboard row copying is disabled."
                )

            self.scrolled_window.set_min_content_width(self.popover_min_width)
            self.scrolled_window.set_max_content_height(self.popover_max_height)

            main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)

            self.searchbar = self.gtk.SearchEntry.new()
            self.searchbar.connect(
                "search_changed",
                lambda _: self.listbox.invalidate_filter(),  # pyright: ignore
            )

            main_box.append(self.searchbar)
            main_box.append(self.scrolled_window)

            btn_clear = self.gtk.Button.new_with_label("Clear History")
            btn_clear.add_css_class("clipboard-button-clear")
            btn_clear.connect("clicked", self.on_clear_clicked)
            main_box.append(btn_clear)

            self.popover_clipboard.set_child(main_box)
            self.popover_clipboard.connect(
                "map", lambda _: self.update_clipboard_list()
            )

            return self.popover_clipboard

        def on_copy_row(self, _, row):
            """
            Callback for copying selected history items.
            """
            if not row:
                return
            item_id = row.get_child().ITEM_ID
            self.run_in_async_task(self._do_copy(item_id))

        async def _do_copy(self, item_id):
            """
            Executes the copy operation and hides the popover.
            """
            history = await self.manager.get_history()
            for item in history:
                if item[0] == item_id:
                    self.copy_to_clipboard(item[1])
                    if self.popover_clipboard:
                        self.popover_clipboard.popdown()
                    break

        def on_delete_selected(self, btn):
            """
            Callback to delete a specific item from history.
            """
            if iid := self.delete_btn_map.get(btn):
                btn.set_state_flags(self.gtk.StateFlags.NORMAL, True)
                self.run_in_async_task(self._do_delete(iid))

        async def _do_delete(self, iid):
            """
            Removes item from database and refreshes the UI list.
            """
            await self.manager.delete_item(iid)
            row = self.listbox.get_first_child()  # pyright: ignore
            while row:
                if row.get_child().ITEM_ID == iid:  # pyright: ignore
                    row.unmap()
                    self.listbox.remove(row)  # pyright: ignore
                    break
                row = row.get_next_sibling()

        def on_clear_clicked(self, *_):
            """
            Callback to clear entire history.
            """
            self.run_in_async_task(self._do_clear())

        async def _do_clear(self):
            """
            Wipes the database and clears the UI list.
            """
            await self.manager.clear_history()
            while row := self.listbox.get_first_child():  # pyright: ignore
                row.unmap()
                self.listbox.remove(row)  # pyright: ignore

        def on_right_click_row(self, gesture, *args):
            """
            Displays a context menu for pinning/unpinning items.
            """
            row = gesture.get_widget()
            child = row.get_child()

            menu = self.gtk.Popover.new()
            menu.set_parent(row)
            menu.set_autohide(True)
            menu.connect("closed", lambda p: p.unparent())

            label = "Unstick from Top" if child.IS_PINNED else "Stick to Top"
            icon = (
                "object-unlocked-symbolic"
                if child.IS_PINNED
                else "object-locked-symbolic"
            )

            btn = self.gtk.Button.new()
            btn.set_focus_on_click(False)
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
            """
            Closes context menu and triggers pin status update.
            """
            menu.popdown()
            self.run_in_async_task(self._do_toggle_pin(iid, pinned))

        async def _do_toggle_pin(self, iid, pinned):
            """
            Updates pin status in database and refreshes UI.
            """
            await self.manager.update_item_pin_status(iid, not pinned)
            while row := self.listbox.get_first_child():  # pyright: ignore
                row.unmap()
                self.listbox.remove(row)  # pyright: ignore
            await self.populate_listbox_async()

        def create_popover_menu_clipboard(self):
            """
            Initializes the clipboard button and popover.
            Fixed: Order of initialization to prevent AttributeError.
            """
            self.button_clipboard = self.gtk.Button()
            self.create_popover_clipboard()
            self._gtk_helper.create_popover_button(
                icon_name=self.main_icon,
                popover_widget=self.popover_clipboard,
                button_instance=self.button_clipboard,  # pyright: ignore
            )

            self.main_widget = (self.button_clipboard, "append")

        def on_clipboard_button_clicked(self, _):
            """Manually toggles the popover visibility."""
            if self.popover_clipboard.get_visible():  # pyright: ignore
                self.popover_clipboard.popdown()  # pyright: ignore
            else:
                self.popover_clipboard.popup()  # pyright: ignore

        def on_disable(self):
            """
            Stops the server on plugin disable.
            """
            self.run_in_async_task(self.manager.server.stop())

    return ClipboardClient
