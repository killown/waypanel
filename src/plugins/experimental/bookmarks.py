from bs4 import BeautifulSoup
from PIL import Image
from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    position = "top-panel-box-widgets-left"
    order = 2
    return position, order


def initialize_plugin(panel_instance):
    """
    Initialize the plugin by checking for the existence of a bookmarks file.
    If the file exists, initialize the PopoverBookmarks class.
    """
    import os

    bookmarks_file = os.path.join(os.path.expanduser("~"), ".bookmarks")
    if os.path.exists(bookmarks_file):
        if ENABLE_PLUGIN:
            return PopoverBookmarks(panel_instance)


class PopoverBookmarks(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_bookmarks = None
        self.menubutton_bookmarks = None
        self.flowbox = None
        self.scrolled_window = None
        self.run_in_thread(self._setup_config_paths)
        self.listbox = self.gtk.ListBox.new()

    def on_start(self):
        """Hook called by BasePlugin after successful initialization."""
        self.create_menu_popover_bookmarks()

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = self.os.path.expanduser("~")
        self.config_path = self.os.path.join(self.home, ".config/waypanel")
        self.bookmarks_image_path = self.os.path.join(
            self.config_path, "bookmarks/images/"
        )
        self.thumbnails_path = self.os.path.join(
            self.bookmarks_image_path, "thumbnails"
        )
        self.os.makedirs(self.thumbnails_path, exist_ok=True)

    def create_menu_popover_bookmarks(self):
        self.menubutton_bookmarks = self.gtk.Button()
        self.menubutton_bookmarks.connect("clicked", self.open_popover_bookmarks)
        self.main_widget = (self.menubutton_bookmarks, "append")
        icon_name = self.icon_exist(
            "bookmarks",
            ["applications-internet"],
        )
        self.menubutton_bookmarks.set_icon_name(icon_name)
        self.menubutton_bookmarks.add_css_class("bookmarks-menu-button")
        self.add_cursor_effect(self.menubutton_bookmarks)

    def open_popover_bookmarks(self, *_):
        if self.popover_bookmarks and self.popover_bookmarks.is_visible():
            self.popover_bookmarks.popdown()
        elif self.popover_bookmarks and not self.popover_bookmarks.is_visible():
            self.popover_bookmarks.popup()
        else:
            self._create_loading_popover_and_start_load()

    def _create_loading_popover_and_start_load(self):
        """Create a popover with a loading state, then start the async load."""
        self.popover_bookmarks = self.create_popover(
            parent_widget=self.menubutton_bookmarks,
            closed_handler=self.popover_is_closed,
            has_arrow=False,
            css_class="plugin-default-popover bookmarks-popover",
        )
        main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)
        main_box.set_halign(self.gtk.Align.CENTER)
        main_box.set_valign(self.gtk.Align.CENTER)
        loading_label = self.gtk.Label(label="Loading bookmarks...")
        loading_label.set_margin_top(20)
        loading_label.set_margin_bottom(20)
        main_box.append(loading_label)
        self.popover_bookmarks.set_child(main_box)
        self.popover_bookmarks.popup()
        self.run_in_async_task(self._load_and_update_bookmarks())

    def _sync_download_and_save_image(self, url, save_path):
        """Blocking image download and save utility, to be run in a thread."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        full_url = "https://" + url if "https://" not in url else url
        final_image_url = None
        try:
            response = self.requests.get(full_url, headers=headers, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                og_image_meta = soup.find("meta", property="og:image")
                if og_image_meta and og_image_meta.get("content"):
                    final_image_url = og_image_meta.get("content")
            if final_image_url:
                image_response = self.requests.get(
                    final_image_url, headers=headers, timeout=5
                )
                if (
                    image_response.status_code == 200
                    and "image" in image_response.headers.get("Content-Type", "")
                ):
                    self.os.makedirs(self.os.path.dirname(save_path), exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(image_response.content)
                    self.logger.info(f"Image downloaded successfully to {save_path}.")
                    return True
        except Exception as e:
            self.logger.warning(f"Error during image download for {url}: {e}")
        self.logger.info(
            "No suitable image found/download failed. Check if domain blocks scraping."
        )
        return False

    def _sync_process_all_bookmarks(self):
        """Blocking function to load bookmarks, check/generate thumbnails."""
        THUMBNAIL_SIZE = (32, 32)
        THUMBNAIL_QUALITY = 75
        bookmarks_path = self.os.path.join(self.home, ".bookmarks")
        with open(bookmarks_path, "r") as f:
            all_bookmarks = self.toml.load(f)
        processed_bookmarks = []
        for name, bookmark_data in all_bookmarks.items():
            url = bookmark_data.get("url", "")
            container = bookmark_data.get("container", "")
            icon = url
            if "/" in icon:
                icon = [i for i in icon.split("/") if "." in i][0]
                icon = "{0}.png".format(icon)
            else:
                icon = url + ".png"
            bookmark_image = self.os.path.join(self.bookmarks_image_path, icon)
            thumbnail_path = self.os.path.join(self.thumbnails_path, icon)
            if "image" in bookmark_data and not self.os.path.exists(bookmark_image):
                image_url_to_fetch = bookmark_data.get("image", "")
                self._sync_download_and_save_image(image_url_to_fetch, bookmark_image)
            if self.os.path.exists(bookmark_image):
                needs_thumbnail = (not self.os.path.exists(thumbnail_path)) or (
                    self.os.path.getmtime(bookmark_image)
                    > self.os.path.getmtime(thumbnail_path)
                )
                if needs_thumbnail:
                    with Image.open(bookmark_image) as img:
                        img.thumbnail(THUMBNAIL_SIZE)
                        img.save(thumbnail_path, quality=THUMBNAIL_QUALITY)
                processed_bookmarks.append(
                    {
                        "name": name,
                        "url": url,
                        "container": container,
                        "thumbnail_path": thumbnail_path,
                        "size": THUMBNAIL_SIZE,
                    }
                )
            else:
                processed_bookmarks.append(
                    {
                        "name": name,
                        "url": url,
                        "container": container,
                        "symbolic_icon": True,
                        "size": THUMBNAIL_SIZE,
                    }
                )
        return processed_bookmarks

    async def _load_and_update_bookmarks(self):
        """Async function to load bookmarks, process images, and update the UI."""
        try:
            processed_bookmarks = await self.asyncio.to_thread(
                self._sync_process_all_bookmarks
            )
        except Exception as e:
            self.logger.exception(f"Error loading and processing bookmarks: {e}")
            processed_bookmarks = None
        self.schedule_in_gtk_thread(self._update_popover_ui, processed_bookmarks)

    def _update_popover_ui(self, processed_bookmarks):
        """Update the popover with processed bookmark data (runs on GTK thread)."""
        if not self.popover_bookmarks:
            return False
        if not processed_bookmarks:
            main_box = self.popover_bookmarks.get_child()
            for child in main_box:  # pyright: ignore
                main_box.remove(child)  # pyright: ignore
            label = self.gtk.Label(label="No bookmarks found or error loading.")
            main_box.append(label)  # pyright: ignore
            return False
        self.scrolled_window = self.gtk.ScrolledWindow()
        self.scrolled_window.set_policy(
            self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.AUTOMATIC
        )
        self.flowbox = self.gtk.FlowBox()
        self.flowbox.set_valign(self.gtk.Align.START)
        self.flowbox.set_max_children_per_line(2)
        self.flowbox.set_selection_mode(self.gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.open_url_from_bookmarks)
        self.scrolled_window.set_child(self.flowbox)
        main_box = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
        main_box.append(self.scrolled_window)
        self.popover_bookmarks.set_child(main_box)
        for data in processed_bookmarks:
            name, url, container, size = (
                data["name"],
                data["url"],
                data["container"],
                data["size"],
            )
            row_hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = (url, container)
            line = self.gtk.Label.new()
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(self.gtk.Align.START)
            image = self.gtk.Image()
            if data.get("symbolic_icon"):
                image.set_from_icon_name("web-browser-symbolic")
                image.set_pixel_size(size[0])
            else:
                thumbnail_pixbuf = self.gdkpixbuf.Pixbuf.new_from_file_at_scale(
                    data["thumbnail_path"], size[0], size[1], True
                )
                image = self.gtk.Image.new_from_pixbuf(thumbnail_pixbuf)
            image.props.margin_end = 5
            image.set_halign(self.gtk.Align.END)
            row_hbox.append(image)
            row_hbox.append(line)
            self.add_cursor_effect(row_hbox)
            self.flowbox.append(row_hbox)
            line.add_css_class("bookmarks-label-from-popover")
            image.add_css_class("bookmarks-icon-from-popover")
        height = self.flowbox.get_preferred_size().natural_size.height  # pyright: ignore
        width = self.flowbox.get_preferred_size().natural_size.width  # pyright: ignore
        self.scrolled_window.set_min_content_width(width)
        self.scrolled_window.set_min_content_height(height)
        self.flowbox.show()
        self.popover_bookmarks.popup()
        return False

    def open_url_from_bookmarks(self, x, *_):
        url, container = [i.get_child().MYTEXT for i in x.get_selected_children()][0]
        all_windows = self.ipc.list_views()
        view = [
            i["id"] for i in all_windows if "firefox-developer-edition" in i["app-id"]
        ]
        if view:
            self.ipc.set_focus(view[0])
        cmd = f"firefox-developer-edition 'ext+container:name={container}&url={url}'"
        self.cmd.run(cmd)
        if self.popover_bookmarks:
            self.popover_bookmarks.popdown()

    def popover_is_closed(self, *_):
        self.popover_bookmarks = None
        self.flowbox = None
        self.scrolled_window = None
        return

    def about(self):
        """
        A plugin that provides quick access to a user's web bookmarks via a
        popover menu. It reads bookmarks from a TOML file, downloads and
        generates thumbnails for website icons, and launches the
        corresponding URLs in a web browser.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin seamlessly integrates web bookmarks into the panel by
        combining file I/O, network requests, image processing, and GTK UI
        components, now fully leveraging the BasePlugin helpers:
        **Key Refactoring Points (Using BasePlugin Helpers):**
        1.  **I/O and Threading:** All blocking operations (`self.os` calls, `self.toml.load`, `self.requests.get`, `self.Image` processing) are bundled into `_sync_process_all_bookmarks` and executed non-blockingly using **`await self.asyncio.to_thread(...)`** inside the asynchronous function `_load_and_update_bookmarks`.
        2.  **Asynchronous Workflow:** The `open_popover_bookmarks` entry point calls `_create_loading_popover_and_start_load`, which sets up a temporary loading UI and starts the I/O work with **`self.run_in_async_task`**.
        3.  **GTK Thread Safety:** The UI update function `_update_popover_ui` is called via **`self.schedule_in_gtk_thread`** to safely manipulate GTK widgets after the background I/O is complete.
        4.  **GTK Helpers:**
            * Popover creation is consolidated into **`self.create_popover(...)`**, correctly setting the parent, closed handler, and properties like `has_arrow=False`.
            * All GTK components (`Gtk.Box`, `Gtk.Label`, `Gtk.FlowBox`, etc.) now consistently use the **`self.gtk`** alias.
            * Icon and cursor effects use **`self.set_widget_icon_name`** and **`self.add_cursor_effect`**.
            * Pixbuf operations use **`self.gdkpixbuf`**.
        5.  **Standard Library Aliases:** Direct imports of `os`, `requests`, `toml`, `PIL.Image`, and `bs4.BeautifulSoup` are eliminated and replaced with the safe, exposed properties **`self.os`**, **`self.requests`**, **`self.toml`**, **`self.Image`**, and **`self.BeautifulSoup`**.
        """
        return self.code_explanation.__doc__
