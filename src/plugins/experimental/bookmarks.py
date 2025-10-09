"""[Google]
url = "https://www.google.com"
container = "personal"
icon = "https://www.google.com/favicon.ico"
[GitHub]
url = "https://www.github.com"
container = "dev"
[Google Maps]
url = "https://maps.google.com"
container = "personal"
icon = "https://maps.google.com/favicon.ico"
"""


def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.browser_bookmarks",
        "name": "Browser Bookmarks",
        "version": "1.0.0",
        "enabled": True,
        "index": 2,
        "container": "top-panel-box-widgets-left",
        "deps": ["top_panel"],
    }


def get_plugin_class():
    import re
    from bs4 import BeautifulSoup
    from PIL import Image, ImageDraw
    from src.plugins.core._base import BasePlugin
    from typing import Tuple, Dict, Any, Union
    import tldextract
    import urllib.parse

    class PopoverBookmarks(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover_bookmarks = None
            self.menubutton_bookmarks = None
            self.flowbox = None
            self.scrolled_window = None
            self.final_popover_content = None
            self.icons_loaded = False
            self.icon_cache: Dict[str, Any] = {}
            self.listbox = self.gtk.ListBox.new()
            self.THUMBNAIL_SIZE = (128, 128)
            self.THUMBNAIL_QUALITY = 100

        def _get_cache_path(self) -> str:
            return self.os.path.join(self.config_path, "bookmarks_cache.toml")

        def _load_cache(self) -> Dict[str, Any]:
            cache_path = self._get_cache_path()
            if self.os.path.exists(cache_path):
                try:
                    with open(cache_path, "r") as f:
                        return self.toml.load(f)
                except Exception as e:
                    self.logger.warning(f"Error loading bookmarks cache: {e}")
            return {}

        def _save_cache(self):
            cache_path = self._get_cache_path()
            try:
                self.os.makedirs(self.os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w") as f:
                    self.toml.dump(self.icon_cache, f)
            except Exception as e:
                self.logger.warning(f"Error saving bookmarks cache: {e}")

        def _ensure_default_bookmarks_file(self):
            """
            Checks for and creates the default bookmarks.toml file if it doesn't exist,
            using the global DEFAULT_BOOKMARKS_TEMPLATE.
            """
            bookmarks_path = self._path_handler.get_data_path()
            bookmarks_dir = self.os.path.join(bookmarks_path, "bookmarks")
            bookmarks_file = self.os.path.join(bookmarks_dir, "bookmarks.toml")
            if not self.os.path.exists(bookmarks_file):
                try:
                    self.os.makedirs(bookmarks_dir, exist_ok=True)
                    with open(bookmarks_file, "w") as f:
                        f.write(DEFAULT_BOOKMARKS_TEMPLATE.strip())
                    self.logger.info(
                        f"Created default bookmarks file at: {bookmarks_file}"
                    )
                except Exception as e:
                    self.logger.error(f"Error creating default bookmarks file: {e}")

        def on_start(self):
            self._ensure_default_bookmarks_file()
            self._setup_config_paths()
            self.create_menu_popover_bookmarks()
            self.run_in_async_task(
                self._load_and_update_bookmarks(is_initial_load=True)
            )

        def _setup_config_paths(self):
            self.home = self.os.path.expanduser("~")
            self.config_path = self._path_handler.get_data_path()
            print(self.config_path)
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
            if self.popover_bookmarks and self.popover_bookmarks.get_property(
                "visible"
            ):
                self.popover_bookmarks.popdown()
                return
            if self.icons_loaded and self.final_popover_content:
                if not self.popover_bookmarks:
                    self._create_reusable_popover()
                self.popover_bookmarks.set_child(self.final_popover_content)  # pyright: ignore
                self.popover_bookmarks.popup()  # pyright: ignore
                return
            self._create_loading_popover_and_start_load()

        def _create_reusable_popover(self):
            if not self.popover_bookmarks:
                self.popover_bookmarks = self.create_popover(
                    parent_widget=self.menubutton_bookmarks,
                    closed_handler=self.popover_is_closed,
                    has_arrow=False,
                    css_class="plugin-default-popover bookmarks-popover",
                )

        def _create_loading_popover_and_start_load(self):
            self._create_reusable_popover()
            main_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)
            main_box.set_halign(self.gtk.Align.CENTER)
            main_box.set_valign(self.gtk.Align.CENTER)
            loading_label = self.gtk.Label(label="Loading bookmarks...")
            loading_label.set_margin_top(20)
            loading_label.set_margin_bottom(20)
            main_box.append(loading_label)
            self.popover_bookmarks.set_child(main_box)  # pyright: ignore
            self.popover_bookmarks.popup()  # pyright: ignore
            self.run_in_async_task(self._load_and_update_bookmarks())

        def _get_root_hostname(self, full_url: str) -> str:
            parsed = urllib.parse.urlparse(full_url)
            hostname = parsed.netloc
            if not hostname:
                return ""
            hostname = hostname.split(":")[0]
            extracted = tldextract.extract(full_url)
            return extracted.fqdn if extracted.fqdn else hostname

        def _get_safe_icon_filename(self, url: str) -> str:
            full_hostname = self._get_root_hostname(url)
            if not full_hostname:
                parsed = urllib.parse.urlparse(url)
                full_hostname = (
                    parsed.netloc.split(":")[0] if parsed.netloc else "fallback_icon"
                )
            safe_name = re.sub(r"[^\w\.\-]", "_", full_hostname)
            return safe_name + ".png"

        def _get_root_domain_with_scheme(self, full_url: str) -> str:
            parsed = urllib.parse.urlparse(full_url)
            scheme = parsed.scheme if parsed.scheme else "https"
            full_hostname = self._get_root_hostname(full_url)
            if not full_hostname:
                return full_url
            return f"{scheme}://{full_hostname}"

        def _find_largest_icon_url(self, soup, base_url):
            icon_candidates = []
            icon_rels = [
                "icon",
                "shortcut icon",
                "apple-touch-icon",
                "apple-touch-icon-precomposed",
            ]
            icon_links = soup.find_all(
                "link", rel=lambda rel: rel and rel.lower() in icon_rels
            )
            for link in icon_links:
                href = link.get("href")
                if not href:
                    continue
                size = 0
                size_attr = link.get("sizes")
                if size_attr:
                    try:
                        size_str = size_attr.split()[0].split("x")[0]
                        size = int(size_str)
                    except ValueError:
                        if size_attr.lower() == "any":
                            size = 512
                if size == 0 and "icon" in link.get("rel", [None]):
                    size = 32
                if href.startswith("http"):
                    absolute_url = href
                elif href.startswith("//"):
                    absolute_url = "https:" + href
                elif href.startswith("/"):
                    absolute_url = base_url + href
                else:
                    absolute_url = base_url.rstrip("/") + "/" + href.lstrip("/")
                icon_candidates.append((size, absolute_url))
            if not icon_candidates:
                return None
            largest_icon = max(icon_candidates, key=lambda x: x[0])
            return largest_icon[1]

        def _sync_download_and_save_image(
            self,
            url: str,
            save_path: str,
            explicit_icon_url: str = None,  # pyright: ignore
        ) -> Union[Tuple[Tuple[int, int], str], Tuple[bool, str], bool]:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
            }
            full_url = "https://" + url if not url.startswith("http") else url
            final_image_url = None
            download_type = "scraped"
            if explicit_icon_url and explicit_icon_url.startswith("http"):
                final_image_url = explicit_icon_url
                download_type = "explicit"
            parsed_url = urllib.parse.urlparse(full_url)
            current_scheme = parsed_url.scheme if parsed_url.scheme else "https"
            full_hostname = self._get_root_hostname(full_url)
            current_netloc_url = f"{current_scheme}://{full_hostname}"
            if not final_image_url:
                root_url_for_favicon = self._get_root_domain_with_scheme(full_url)
                try:
                    response = self.requests.get(full_url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, "html.parser")
                        final_image_url = self._find_largest_icon_url(
                            soup, current_netloc_url
                        )
                except Exception:
                    pass
                if not final_image_url:
                    final_image_url = current_netloc_url + "/favicon.ico"
                    download_type = "favicon"
            if final_image_url:
                try:
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
                        try:
                            with Image.open(save_path) as img:
                                self.logger.info(
                                    f"Image downloaded successfully to {save_path} via {download_type}. Size: {img.size}"
                                )
                                return img.size, download_type
                        except Exception as e:
                            self.logger.warning(
                                f"Image downloaded but could not read size for {save_path}: {e}"
                            )
                            return True, download_type
                except Exception as e:
                    self.logger.warning(
                        f"Error during image download for {url} from {final_image_url}: {e}"
                    )
            self.logger.info(
                "No suitable image found/download failed. Check if domain blocks scraping."
            )
            return False

        def _create_round_thumbnail(self, source_path: str, target_path: str) -> bool:
            """Creates a circular thumbnail with padding for low-res icons (specifically favicon.ico)."""
            try:
                THUMB_W, THUMB_H = self.THUMBNAIL_SIZE
                PADDING = 7
                INNER_W, INNER_H = (
                    THUMB_W - 2 * PADDING,
                    THUMB_H - 2 * PADDING,
                )
                with Image.open(source_path).convert("RGBA") as icon_img:
                    icon_img.thumbnail((INNER_W, INNER_H), Image.Resampling.LANCZOS)
                    icon_w, icon_h = icon_img.size
                    mask = Image.new("L", self.THUMBNAIL_SIZE, 0)
                    draw = ImageDraw.Draw(mask)
                    draw.ellipse((0, 0, THUMB_W, THUMB_H), fill=255)
                    final_img = Image.new(
                        "RGBA", self.THUMBNAIL_SIZE, (255, 255, 255, 0)
                    )
                    paste_x = (THUMB_W - icon_w) // 2
                    paste_y = (THUMB_H - icon_h) // 2
                    final_img.paste(icon_img, (paste_x, paste_y), icon_img)
                    final_img.putalpha(mask)
                    self.os.makedirs(self.os.path.dirname(target_path), exist_ok=True)
                    final_img.save(target_path, "PNG", quality=self.THUMBNAIL_QUALITY)
                    return True
            except Exception as e:
                self.logger.warning(
                    f"Failed to create centered round thumbnail for {source_path}: {e}"
                )
                return False

        def _load_raw_bookmarks(self) -> list[Dict[str, Any]]:
            bookmarks_path = self._path_handler.get_data_path()
            bookmarks_dir = self.os.path.join(bookmarks_path, "bookmarks")
            bookmarks_file = self.os.path.join(bookmarks_dir, "bookmarks.toml")
            with open(bookmarks_file, "r") as f:
                all_bookmarks = self.toml.load(f)
            self.icon_cache = self._load_cache()
            prepared_tasks = []
            for name, bookmark_data in all_bookmarks.items():
                url = bookmark_data.get("url", "")
                explicit_icon_url = bookmark_data.get("icon", "")
                safe_filename = self._get_safe_icon_filename(url)
                bookmark_image = self.os.path.join(
                    self.bookmarks_image_path, safe_filename
                )
                cache_entry = self.icon_cache.get(safe_filename, {})
                cached_download_type = cache_entry.get("download_type", "scraped")
                download_type = cached_download_type
                should_download = not self.os.path.exists(bookmark_image)
                if explicit_icon_url and explicit_icon_url.startswith("http"):
                    download_type = "explicit"
                    if (
                        self.os.path.exists(bookmark_image)
                        and cached_download_type == "explicit"
                    ):
                        should_download = False
                    else:
                        should_download = True
                elif (
                    self.os.path.exists(bookmark_image)
                    and cached_download_type != "explicit"
                ):
                    should_download = False
                prepared_tasks.append(
                    {
                        "name": name,
                        "url": url,
                        "container": bookmark_data.get("container", ""),
                        "safe_filename": safe_filename,
                        "explicit_icon_url": explicit_icon_url,
                        "bookmark_image": bookmark_image,
                        "thumbnail_path": self.os.path.join(
                            self.thumbnails_path, safe_filename
                        ),
                        "should_download": should_download,
                        "download_type": download_type,
                    }
                )
            return prepared_tasks

        def _sync_process_single_bookmark(
            self, data: Dict[str, Any]
        ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            url = data["url"]
            name = data["name"]
            container = data["container"]
            safe_filename = data["safe_filename"]
            explicit_icon_url = data["explicit_icon_url"]
            bookmark_image = data["bookmark_image"]
            thumbnail_path = data["thumbnail_path"]
            should_download = data["should_download"]
            download_type = data["download_type"]
            cache_update = {}
            if should_download:
                download_result = self._sync_download_and_save_image(
                    url, bookmark_image, explicit_icon_url=explicit_icon_url
                )
                if isinstance(download_result, tuple) and len(download_result) == 2:
                    download_size, download_type = download_result
                    cache_update[safe_filename] = {
                        "size": download_size
                        if isinstance(download_size, tuple)
                        else self.THUMBNAIL_SIZE,
                        "download_type": download_type,
                    }
                elif download_result is False:
                    cache_update[safe_filename] = {
                        "size": (0, 0),
                        "download_type": "failed",
                    }
                    download_type = "failed"
                    try:
                        self.os.makedirs(
                            self.os.path.dirname(bookmark_image), exist_ok=True
                        )
                        with open(bookmark_image, "w") as f:
                            f.write("")
                        self.logger.info(
                            f"Icon download failed for {url}. Created marker file to skip future network attempts."
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to create marker file for {url}: {e}"
                        )
                else:
                    download_type = "scraped"
            elif not should_download and safe_filename in self.icon_cache:
                download_type = self.icon_cache[safe_filename].get(
                    "download_type", "scraped"
                )
            thumbnail_success = False
            is_valid_image_file = (
                self.os.path.exists(bookmark_image)
                and self.os.path.getsize(bookmark_image) > 0
            )
            if is_valid_image_file:
                needs_thumbnail = not self.os.path.exists(thumbnail_path) or (
                    self.os.path.getmtime(bookmark_image)
                    > self.os.path.getmtime(thumbnail_path)
                )
                if needs_thumbnail:
                    is_round_icon = download_type == "favicon" or (
                        download_type == "scraped" and explicit_icon_url == ""
                    )
                    if is_round_icon:
                        thumbnail_success = self._create_round_thumbnail(
                            bookmark_image, thumbnail_path
                        )
                        if thumbnail_success:
                            self.logger.info(
                                f"Created centered round thumbnail for {download_type}: {thumbnail_path}"
                            )
                    else:
                        try:
                            with Image.open(bookmark_image) as img:
                                img.thumbnail(
                                    self.THUMBNAIL_SIZE, Image.Resampling.LANCZOS
                                )
                                img.save(
                                    thumbnail_path,
                                    "PNG",
                                    quality=self.THUMBNAIL_QUALITY,
                                )
                            thumbnail_success = True
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to open/process standard image file {bookmark_image}. Falling back to symbolic icon: {e}"
                            )
                            thumbnail_success = False
                elif self.os.path.exists(thumbnail_path):
                    thumbnail_success = True
            if thumbnail_success:
                processed_data = {
                    "name": name,
                    "url": url,
                    "container": container,
                    "thumbnail_path": thumbnail_path,
                    "size": self.THUMBNAIL_SIZE,
                }
            else:
                processed_data = {
                    "name": name,
                    "url": url,
                    "container": container,
                    "symbolic_icon": True,
                    "size": self.THUMBNAIL_SIZE,
                }
            return processed_data, cache_update

        async def _load_and_update_bookmarks(self, is_initial_load: bool = False):
            try:
                prepared_tasks = await self.asyncio.to_thread(self._load_raw_bookmarks)
                tasks = []
                for data in prepared_tasks:
                    tasks.append(
                        self.asyncio.to_thread(self._sync_process_single_bookmark, data)
                    )
                results_with_cache = await self.asyncio.gather(*tasks)
                processed_bookmarks = []
                final_cache_updates = {}
                for result, cache_update in results_with_cache:
                    processed_bookmarks.append(result)
                    final_cache_updates.update(cache_update)
                self.icon_cache.update(final_cache_updates)
                await self.asyncio.to_thread(self._save_cache)
            except Exception as e:
                self.logger.exception(f"Error loading and processing bookmarks: {e}")
                processed_bookmarks = None
            self.schedule_in_gtk_thread(
                self._update_popover_ui, processed_bookmarks, is_initial_load
            )

        def _update_popover_ui(
            self, processed_bookmarks, is_initial_load: bool = False
        ):
            if not self.popover_bookmarks:
                return False
            main_box = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, 0)
            if not processed_bookmarks:
                error_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)
                label = self.gtk.Label(label="No bookmarks found or error loading.")
                error_box.append(label)
                main_box.append(error_box)
            else:
                self.scrolled_window = self.gtk.ScrolledWindow()
                self.scrolled_window.set_policy(
                    self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.AUTOMATIC
                )
                self.flowbox = self.gtk.FlowBox()
                self.flowbox.set_valign(self.gtk.Align.START)
                self.flowbox.set_max_children_per_line(3)
                self.flowbox.set_selection_mode(self.gtk.SelectionMode.SINGLE)
                self.flowbox.set_activate_on_single_click(True)
                self.flowbox.connect("child-activated", self.open_url_from_bookmarks)
                self.scrolled_window.set_child(self.flowbox)
                main_box.append(self.scrolled_window)
                for data in processed_bookmarks:
                    name, url, container, size = (
                        data["name"],
                        data["url"],
                        data["container"],
                        data["size"],
                    )
                    row_hbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 5)
                    row_hbox.MYTEXT = (url, container)
                    row_hbox.add_css_class("bookmarks-hbox-row")
                    line = self.gtk.Label.new()
                    line.set_label(name)
                    line.set_halign(self.gtk.Align.CENTER)
                    line.props.margin_start = 0
                    line.props.hexpand = False
                    line.set_max_width_chars(15)
                    line.set_ellipsize(self.pango.EllipsizeMode.END)
                    image = self.gtk.Image()
                    if data.get("symbolic_icon"):
                        image.set_from_icon_name("web-browser-symbolic")
                        image.set_pixel_size(size[0])
                    else:
                        thumbnail_pixbuf = self.gdkpixbuf.Pixbuf.new_from_file_at_scale(
                            data["thumbnail_path"], size[0], size[1], True
                        )
                        image = self.gtk.Image.new_from_pixbuf(thumbnail_pixbuf)
                    image.props.margin_end = 0
                    image.set_halign(self.gtk.Align.CENTER)
                    row_hbox.append(image)
                    row_hbox.append(line)
                    self.add_cursor_effect(row_hbox)
                    self.flowbox.append(row_hbox)
                    line.add_css_class("bookmarks-label-from-popover")
                    image.add_css_class("bookmarks-icon-from-popover")
                self.flowbox.show()
                height = self.flowbox.get_preferred_size().natural_size.height
                width = self.flowbox.get_preferred_size().natural_size.width
                self.scrolled_window.set_min_content_width(width)
                self.scrolled_window.set_min_content_height(height)
            self.final_popover_content = main_box
            self.icons_loaded = True
            if not is_initial_load:
                self.popover_bookmarks.set_child(self.final_popover_content)
                self.popover_bookmarks.popup()
            return False

        def open_url_from_bookmarks(self, x, *_):
            url, container = [i.get_child().MYTEXT for i in x.get_selected_children()][
                0
            ]
            all_windows = self.ipc.list_views()
            view = [
                i["id"]
                for i in all_windows
                if "firefox-developer-edition" in i["app-id"]
            ]
            if view:
                self.ipc.set_focus(view[0])
            cmd = (
                f"firefox-developer-edition 'ext+container:name={container}&url={url}'"
            )
            self.cmd.run(cmd)
            if self.popover_bookmarks:
                self.popover_bookmarks.popdown()

        def popover_is_closed(self, *_):
            if not self.icons_loaded:
                self.popover_bookmarks = None
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
            components. The image fetching logic has been updated to:
            1. **Scrape for Largest Favicon:** It now scrapes the HTML of the bookmark's URL for `<link>` tags with `rel` values like `icon`, `apple-touch-icon`, etc.
            2. **Prioritize by Size:** It parses the `sizes` attribute (e.g., "180x180") to determine the largest available icon and downloads that one, falling back to a standard `/favicon.ico` if none are explicitly linked.
            3. **Subdomain-Specific Icons:** The filename generation has been corrected to use the **full hostname** (e.g., maps.google.com vs www.google.com) to ensure different subdomains use different cached icons, thus fixing the issue of all Google icons being the same.
            4. **Explicit Icon Priority:** The configuration's `icon = "..."` field now explicitly forces that icon URL to be downloaded if present, overriding any scraping logic for that specific bookmark.
            5. **Content Caching:** The fully constructed GTK widget tree is still cached in `self.final_popover_content` for instant re-use after the first successful load, maintaining high performance.
            """
            return self.code_explanation.__doc__

    return PopoverBookmarks
