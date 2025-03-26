import os
from subprocess import Popen

import gi
import requests
import toml
import wayfire.ipc as wayfire
from bs4 import BeautifulSoup
from gi.repository import Adw, GdkPixbuf, Gio, Gtk
from gi.repository import Gtk4LayerShell as LayerShell


class PopoverBookmarks(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popover_bookmarks = None
        self.app = None
        self.top_panel = None
        self._setup_config_paths()
        self.listbox = Gtk.ListBox.new()

    def _setup_config_paths(self):
        """Set up configuration paths based on the user's home directory."""
        self.home = os.path.expanduser("~")
        self.scripts = os.path.join(self.home, ".config/hypr/scripts")
        self.config_path = os.path.join(self.home, ".config/waypanel")
        self.dockbar_config = os.path.join(self.config_path, "dockbar.toml")
        self.style_css_config = os.path.join(self.config_path, "style.css")
        self.workspace_list_config = os.path.join(self.config_path, "workspacebar.toml")
        self.topbar_config = os.path.join(self.config_path, "panel.toml")
        self.menu_config = os.path.join(self.config_path, "menu.toml")
        self.window_notes_config = os.path.join(self.config_path, "window-config.toml")
        self.cmd_config = os.path.join(self.config_path, "cmd.toml")
        self.topbar_launcher_config = os.path.join(
            self.config_path, "topbar-launcher.toml"
        )
        self.cache_folder = os.path.join(self.home, ".cache/waypanel")
        self.psutil_store = {}
        self.bookmarks_image_path = os.path.join(self.config_path, "bookmarks/images/")

    def create_menu_popover_bookmarks(self, obj, app, *_):
        self.top_panel = obj.top_panel
        self.app = app
        self.menubutton_bookmarks = Gtk.Button()
        self.menubutton_bookmarks.connect("clicked", self.open_popover_bookmarks)
        self.menubutton_bookmarks.set_icon_name("librewolf")
        self.menubutton_bookmarks.add_css_class("top_left_widgets")
        obj.top_panel_box_widgets_left.append(self.menubutton_bookmarks)

    def create_popover_bookmarks(self, *_):
        """
        Create and configure a popover for bookmarks.
        """
        # Create a new popover menu
        self.popover_bookmarks = Gtk.Popover.new()
        self.popover_bookmarks.set_has_arrow(False)
        self.popover_bookmarks.set_autohide(True)
        self.popover_bookmarks.connect("closed", self.popover_is_closed)
        self.popover_bookmarks.connect("notify::visible", self.popover_is_open)

        # Set up scrolled window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )

        # Set up main box
        self.main_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)

        # Create and configure flow box
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(2)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.connect("child-activated", self.open_url_from_bookmarks)
        self.scrolled_window.set_child(self.flowbox)
        self.main_box.append(self.scrolled_window)

        # Configure popover with main box
        self.popover_bookmarks.set_child(self.main_box)

        # Load bookmarks from file
        bookmarks_path = os.path.join(self.home, ".bookmarks")
        with open(bookmarks_path, "r") as f:
            all_bookmarks = toml.load(f)

        # Populate flow box with bookmarks
        for name, bookmark_data in all_bookmarks.items():
            url = bookmark_data.get("url", "")
            container = bookmark_data.get("container", "")
            self.row_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)

            # Create a box for each bookmark
            self.row_hbox.MYTEXT = url, container

            # Configure bookmark icon
            icon = url
            if "/" in icon:
                icon = [i for i in icon.split("/") if "." in i][0]
                icon = "{0}.png".format(icon)
                print(icon)
            else:
                icon = url + ".png"

            # Create label for the bookmark name
            line = Gtk.Label.new()
            line.add_css_class("label_from_bookmarks")
            line.set_label(name)
            line.props.margin_start = 5
            line.props.hexpand = True
            line.set_halign(Gtk.Align.START)

            bookmark_image = os.path.join(self.bookmarks_image_path, icon)

            # skip this url if there is an exception
            try:
                if not os.path.exists(bookmark_image):
                    if "image" in bookmark_data:
                        new_url = bookmark_data.get("image", "")
                        self.download_image_direct(new_url, bookmark_image)
                    else:
                        self.download_image(url, self.bookmarks_image_path)
                # Inside the loop where you load bookmarks
                # Load the original image as a Pixbuf
                original_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    bookmark_image, 64, 64, True
                )
            except Exception as e:
                print(e)
                continue

            # Create a Gtk.Image widget and set the Pixbuf
            image = Gtk.Image.new_from_pixbuf(original_pixbuf)

            image.add_css_class("icon_from_popover_launcher")
            image.props.margin_end = 5
            image.set_halign(Gtk.Align.END)

            # Add label and image to the bookmark box
            self.row_hbox.append(image)
            self.row_hbox.append(line)
            self.flowbox.append(self.row_hbox)

        # Connect signal for selecting a row
        height = self.flowbox.get_preferred_size().natural_size.height
        width = self.flowbox.get_preferred_size().natural_size.width
        self.scrolled_window.set_min_content_width(width * 2)
        self.scrolled_window.set_min_content_height(height / 1.9)

        # Set the parent and display the popover
        self.popover_bookmarks.set_parent(self.menubutton_bookmarks)
        return self.popover_bookmarks

    def download_image_direct(self, url, save_path):
        # Specify a custom user-agent header
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        # Send a GET request to the URL with custom headers
        if "https://" not in url:
            url = "https://" + url
        response = requests.get(url, headers=headers)
        print(response)

        # Check if the request was successful
        if response.status_code == 200:
            # Save the image
            with open(save_path, "wb") as f:
                f.write(response.content)
            print("Image downloaded successfully.")
        else:
            # If request failed
            print(f"Failed to download image. Status code: {response.status_code}")

    def download_image(self, url, save_path):
        # Specify a custom user-agent header
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        # Send a GET request to the URL with custom headers
        if "https://" not in url:
            url = "https://" + url
        response = requests.get(url, headers=headers)
        print(response)
        # Parse the HTML content of the webpage
        soup = BeautifulSoup(response.text, "html.parser")

        # Check for the og:image meta tag
        og_image_meta = soup.find("meta", property="og:image")
        if og_image_meta:
            image_url = og_image_meta.get("content")
            if image_url:
                # Send a GET request to download the image with custom headers
                image_response = requests.get(image_url, headers=headers)
                if image_response.status_code == 200:
                    # Create the directory if it doesn't exist
                    if not os.path.exists(save_path):
                        os.makedirs(save_path)
                    # Save the image
                    with open(
                        os.path.join(save_path, "{0}.png".format(url)), "wb"
                    ) as f:
                        f.write(image_response.content)
                    print("Image downloaded successfully.")
        # If no suitable image found
        print(
            "No suitable image found. If the domain doesn't allow scraping tools, that may deny the image download"
        )

    def open_url_from_bookmarks(self, x, *_):
        url, container = [i.get_child().MYTEXT for i in x.get_selected_children()][0]
        sock = self.compositor()
        all_windows = sock.list_views()
        view = [
            i["id"] for i in all_windows if "librewolf" in i["app-id"]
        ]
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
            self.popover_bookmarks = self.create_popover_bookmarks(self.app)

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
