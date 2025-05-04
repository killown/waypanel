import os
from subprocess import Popen
from PIL import Image

import requests
import toml
import wayfire.ipc as wayfire
from bs4 import BeautifulSoup
from gi.repository import GdkPixbuf, Gtk

from src.plugins.core._base import BasePlugin

# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    position = "top-panel-left"
    order = 2
    return position, order


def initialize_plugin(panel_instance):
    """
    Initialize the plugin by checking for the existence of a bookmarks file.
    If the file exists, create a bookmarks popover menu.

    Args:
        obj: The object where the popover will be added.
        app: The application instance.
    """
    # Expand the user's home directory directly in the function
    bookmarks_file = os.path.join(os.path.expanduser("~"), ".bookmarks")

    if os.path.exists(bookmarks_file):
        if ENABLE_PLUGIN:
            bookmarks = PopoverBookmarks(panel_instance)
            bookmarks.create_menu_popover_bookmarks()
            return bookmarks


class PopoverBookmarks(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover_bookmarks = None
        self.obj = panel_instance
        self.logger = self.obj.logger
        self.top_panel = None
        self._setup_config_paths()
        self.listbox = Gtk.ListBox.new()

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.bookmarks_image_path = os.path.join(self.config_path, "bookmarks/images/")
        self.thumbnails_path = os.path.join(self.bookmarks_image_path, "thumbnails")
        os.makedirs(self.thumbnails_path, exist_ok=True)

    def create_menu_popover_bookmarks(self):
        self.menubutton_bookmarks = Gtk.Button()
        self.menubutton_bookmarks.connect("clicked", self.open_popover_bookmarks)
        self.main_widget = (self.menubutton_bookmarks, "append")
        waypanel_config_path = os.path.join(self.config_path, "waypanel.toml")
        if os.path.exists(waypanel_config_path):
            with open(waypanel_config_path, "r") as f:
                config = toml.load(f)
                bookmarks_icon = (
                    config.get("panel", {})
                    .get("top", {})
                    .get("bookmarks_icon", "librewolf")
                )
                self.menubutton_bookmarks.set_icon_name(bookmarks_icon)
        else:
            self.menubutton_bookmarks.set_icon_name("librewolf")
        self.menubutton_bookmarks.add_css_class("bookmarks-menu-button")

    def create_popover_bookmarks(self, *_):
        """
        Create and configure a popover for bookmarks with optimized thumbnails.
        """
        # Initialize the popover
        self._initialize_popover()

        # Set up the layout (scrolled window, main box, and flowbox)
        self._setup_layout()

        # Load and process bookmarks
        self._load_and_process_bookmarks()

        # Finalize popover setup
        self._finalize_popover_setup()

        return self.popover_bookmarks

    def _initialize_popover(self):
        """Initialize the popover widget."""
        self.popover_bookmarks = Gtk.Popover.new()
        self.popover_bookmarks.set_has_arrow(False)
        self.popover_bookmarks.set_autohide(True)
        self.popover_bookmarks.connect("closed", self.popover_is_closed)
        self.popover_bookmarks.connect("notify::visible", self.popover_is_open)

    def _setup_layout(self):
        """Set up the layout components: scrolled window, main box, and flowbox."""
        # Scrolled window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )

        # Main box
        self.main_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)

        # Flowbox
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(2)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.open_url_from_bookmarks)

        # Attach widgets
        self.scrolled_window.set_child(self.flowbox)
        self.main_box.append(self.scrolled_window)
        if self.popover_bookmarks:
            self.popover_bookmarks.set_child(self.main_box)

    def _load_and_process_bookmarks(self):
        """Load bookmarks from file and populate the flowbox."""
        bookmarks_path = os.path.join(self.home, ".bookmarks")
        with open(bookmarks_path, "r") as f:
            all_bookmarks = toml.load(f)

        THUMBNAIL_SIZE = (32, 32)
        THUMBNAIL_QUALITY = 75

        for name, bookmark_data in all_bookmarks.items():
            url = bookmark_data.get("url", "")
            container = bookmark_data.get("container", "")
            row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            row_hbox.MYTEXT = (url, container)

            # Configure bookmark icon
            icon = url
            if "/" in icon:
                icon = [i for i in icon.split("/") if "." in i][0]
                icon = "{0}.png".format(icon)
            else:
                icon = url + ".png"

            # Create label for the bookmark name
            line = Gtk.Label.new()
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            bookmark_image = os.path.join(self.bookmarks_image_path, icon)
            thumbnail_path = os.path.join(self.thumbnails_path, icon)

            # Try to load or generate thumbnail
            try:
                if not os.path.exists(bookmark_image):
                    if "image" in bookmark_data:
                        new_url = bookmark_data.get("image", "")
                        self.download_image(new_url, bookmark_image)

                # Generate thumbnail if needed
                if (not os.path.exists(thumbnail_path)) or (
                    os.path.getmtime(bookmark_image) > os.path.getmtime(thumbnail_path)
                ):
                    with Image.open(bookmark_image) as img:
                        img.thumbnail(THUMBNAIL_SIZE)
                        img.save(thumbnail_path, quality=THUMBNAIL_QUALITY)

                # Load the thumbnail
                thumbnail_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    thumbnail_path, THUMBNAIL_SIZE[0], THUMBNAIL_SIZE[1], True
                )
                image = Gtk.Image.new_from_pixbuf(thumbnail_pixbuf)
            except Exception as e:
                self.log_error(
                    f"Error processing image for {url}: {e}"
                )
                # Fallback to symbolic icon
                image = Gtk.Image.new_from_icon_name("web-browser-symbolic")
                image.set_pixel_size(THUMBNAIL_SIZE[0])

            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)

            # Add label and image to the bookmark box
            row_hbox.append(image)
            row_hbox.append(line)
            self.flowbox.append(row_hbox)
            line.add_css_class("bookmarks-label-from-popover")
            image.add_css_class("bookmarks-icon-from-popover")

    def _finalize_popover_setup(self):
        """Finalize the popover setup, including dimensions and parent."""
        height = self.flowbox.get_preferred_size().natural_size.height
        width = self.flowbox.get_preferred_size().natural_size.width
        self.scrolled_window.set_min_content_width(width)
        self.scrolled_window.set_min_content_height(height)

        if self.popover_bookmarks:
            self.popover_bookmarks.set_parent(self.menubutton_bookmarks)

        def download_image_direct(self, url, save_path):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
            }

            if "https://" not in url:
                url = "https://" + url
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                self.logger.info("Image downloaded successfully.")
            else:
                self.logger.info(
                    f"Failed to download image. Status code: {response.status_code}"
                )

    def download_image(self, url, save_path):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        if "https://" not in url:
            url = "https://" + url
        response = requests.get(url, headers=headers)

        soup = BeautifulSoup(response.text, "html.parser")
        og_image_meta = soup.find("meta", property="og:image")

        if og_image_meta:
            image_url = og_image_meta.get("content")
            if image_url:
                image_response = requests.get(image_url, headers=headers)
                if image_response.status_code == 200:
                    if not os.path.exists(save_path):
                        os.makedirs(save_path)
                    with open(os.path.join(save_path, f"{url}.png"), "wb") as f:
                        f.write(image_response.content)
                    self.logger.info("Image downloaded successfully.")

        self.logger.info(
            "No suitable image found. If the domain doesn't allow scraping tools, that may deny the image download"
        )

    def open_url_from_bookmarks(self, x, *_):
        url, container = [i.get_child().MYTEXT for i in x.get_selected_children()][0]
        sock = self.compositor()
        all_windows = sock.list_views()
        view = [i["id"] for i in all_windows if "librewolf" in i["app-id"]]
        if view:
            sock.set_focus(view[0])
        cmd = [
            "librewolf",
            "ext+container:name={0}&url={1}".format(container, url),
        ]
        Popen(cmd)
        self.popover_bookmarks.popdown()

    def open_popover_bookmarks(self, *_):
        if self.popover_bookmarks is None:
            self.popover_bookmarks = self.create_popover_bookmarks()

        if self.popover_bookmarks and self.popover_bookmarks.is_visible():
            self.popover_bookmarks.popdown()
            del self.listbox
            del self.popover_bookmarks
            self.listbox = Gtk.ListBox.new()
            self.popover_bookmarks = None

        if self.popover_bookmarks and not self.popover_bookmarks.is_visible():
            self.popover_bookmarks.popup()

    def popover_is_open(self, *_):
        return

    def popover_is_closed(self, *_):
        return

    def compositor(self):
        addr = os.getenv("WAYFIRE_SOCKET")
        return wayfire.WayfireSocket(addr)
