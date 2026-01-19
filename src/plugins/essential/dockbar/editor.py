"""GNOME HIG Shortcut Editor with optimized deferred icon loading and memory guard."""

import os
import gc
import configparser


class ShortcutEditor:
    def __init__(self, plugin):
        self.p = plugin
        self.window = None
        self.current_icon = "system-run"
        self._icon_buttons = []
        self._all_icon_names = []

    def _get_theme_location(self, theme_name):
        """Locates the directory for a specific icon theme."""
        theme_dirs = [
            os.path.expanduser("~/.local/share/icons"),
            os.path.expanduser("~/.icons"),
            "/usr/share/icons",
            "/run/host/usr/share/icons",
            "/run/host/user-share/icons",
        ]
        for theme_dir in theme_dirs:
            theme_path = os.path.join(theme_dir, theme_name)
            if os.path.isdir(theme_path):
                return theme_path
        return None

    def _get_inheritance_chain(self, theme_name):
        """Recursively builds the inheritance list from index.theme files."""
        chain = []
        to_process = [theme_name]

        if "-" in theme_name:
            base = theme_name.split("-")[0]
            if base not in to_process:
                to_process.append(base)

        processed = set()
        while to_process:
            current = to_process.pop(0)
            if current in processed:
                continue

            processed.add(current)
            chain.append(current)

            location = self._get_theme_location(current)
            if location:
                index_path = os.path.join(location, "index.theme")
                if os.path.isfile(index_path):
                    config = configparser.ConfigParser(interpolation=None)
                    try:
                        config.read(index_path)
                        if config.has_section("Icon Theme"):
                            inherits = config.get("Icon Theme", "Inherits", fallback="")
                            if inherits:
                                for parent in inherits.split(","):
                                    parent = parent.strip()
                                    if parent and parent not in processed:
                                        to_process.append(parent)
                    except Exception:
                        pass

        if "hicolor" not in chain:
            chain.append("hicolor")
        return chain

    def _get_theme_icons(self):
        """Scans the theme and parents for icon names without loading widgets."""
        settings = self.p.gtk.Settings.get_default()
        active_theme = settings.get_property("gtk-icon-theme-name")

        theme_chain = self._get_inheritance_chain(active_theme)
        icon_names = set()

        for theme in theme_chain:
            location = self._get_theme_location(theme)
            if not location:
                continue

            for root, _, files in os.walk(location):
                for f in files:
                    if f.endswith((".svg", ".png", ".xpm")):
                        icon_names.add(os.path.splitext(f)[0])

        return sorted(list(icon_names))

    def open(self, app_name=None, app_config=None):
        """Initializes and presents the shortcut editor window."""
        is_new = app_name is None
        self.current_icon = app_config["icon"] if app_config else "system-run"

        self.window = self.p.gtk.Window(
            title="Edit Shortcut" if not is_new else "Add Shortcut",
            modal=True,
            default_width=450,
            resizable=False,
        )

        header = self.p.gtk.HeaderBar()
        self.window.set_titlebar(header)

        cancel_btn = self.p.gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.window.close())
        header.pack_start(cancel_btn)

        save_btn = self.p.gtk.Button(label="Save", css_classes=["suggested-action"])
        header.pack_end(save_btn)

        vbox = self.p.gtk.Box(orientation=self.p.gtk.Orientation.VERTICAL, spacing=18)
        vbox.set_margin_top(18)
        vbox.set_margin_bottom(18)
        vbox.set_margin_start(18)
        vbox.set_margin_end(18)

        list_box = self.p.gtk.ListBox(css_classes=["boxed-list"])
        list_box.set_selection_mode(self.p.gtk.SelectionMode.NONE)

        id_ent = self._create_row(list_box, "App ID", app_name or "", "e.g. firefox")
        cmd_ent = self._create_row(
            list_box,
            "Command",
            app_config["cmd"] if app_config else "",
            "Terminal command",
        )
        self.icon_row_image, self.icon_label = self._create_icon_row(list_box)

        vbox.append(list_box)
        self.window.set_child(vbox)

        save_btn.connect(
            "clicked", lambda _: self._on_save(is_new, app_name, id_ent, cmd_ent)
        )
        self.window.present()

    def _create_row(self, list_box, label_text, value, placeholder):
        row = self.p.gtk.ListBoxRow()
        box = self.p.gtk.Box(spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        label = self.p.gtk.Label(label=label_text, xalign=0, width_chars=10)
        entry = self.p.gtk.Entry(
            text=str(value),
            placeholder_text=placeholder,
            hexpand=True,
            css_classes=["flat"],
        )
        box.append(label)
        box.append(entry)
        row.set_child(box)
        list_box.append(row)
        return entry

    def _create_icon_row(self, list_box):
        row = self.p.gtk.ListBoxRow()
        button = self.p.gtk.Button(css_classes=["flat"])
        button.connect("clicked", lambda _: self._open_icon_selector())
        box = self.p.gtk.Box(spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        label = self.p.gtk.Label(label="Icon", xalign=0, width_chars=10)
        inner_box = self.p.gtk.Box(spacing=8, hexpand=True)
        img = self.p.gtk.Image.new_from_icon_name(self.current_icon)
        img.set_pixel_size(24)
        name_label = self.p.gtk.Label(
            label=self.current_icon, css_classes=["dim-label"]
        )
        inner_box.append(img)
        inner_box.append(name_label)
        box.append(label)
        box.append(inner_box)
        box.append(self.p.gtk.Image.new_from_icon_name("go-next-symbolic"))
        button.set_child(box)
        row.set_child(button)
        list_box.append(row)
        return img, name_label

    def _open_icon_selector(self):
        selector = self.p.gtk.Window(
            title="Select Icon", modal=True, transient_for=self.window
        )
        selector.set_default_size(500, 600)
        self._icon_buttons = []

        main_vbox = self.p.gtk.Box(
            orientation=self.p.gtk.Orientation.VERTICAL, spacing=0
        )
        search_bar = self.p.gtk.SearchEntry(placeholder_text="Search (3+ chars)...")
        search_bar.set_margin_start(12)
        search_bar.set_margin_end(12)
        search_bar.set_margin_top(12)
        search_bar.set_margin_bottom(6)
        main_vbox.append(search_bar)

        self.scrolled = self.p.gtk.ScrolledWindow(vexpand=True)
        self.grid = self.p.gtk.FlowBox(
            valign=self.p.gtk.Align.START,
            max_children_per_line=8,
            min_children_per_line=4,
        )
        self.grid.set_selection_mode(self.p.gtk.SelectionMode.NONE)
        self.grid.set_margin_top(12)
        self.grid.set_margin_bottom(12)
        self.grid.set_margin_start(12)
        self.grid.set_margin_end(12)

        self._all_icon_names = self._get_theme_icons()

        def populate_grid(names_to_load):
            self._cleanup_selector()
            for i in range(0, len(names_to_load), 100):
                if not selector.get_visible():
                    return False
                chunk = names_to_load[i : i + 100]
                for name in chunk:
                    btn = self.p.gtk.Button(css_classes=["flat"], tooltip_text=name)
                    img = self.p.gtk.Image.new_from_icon_name(name)
                    img.set_pixel_size(32)
                    btn.set_child(img)
                    btn.connect(
                        "clicked", lambda _, n=name: self._select_icon(n, selector)
                    )
                    self.grid.append(btn)
                    self._icon_buttons.append(btn)
                yield True
            yield False

        loader = populate_grid(self._all_icon_names[:100])
        self.p.glib.idle_add(lambda: next(loader, False))

        def on_search(_):
            txt = search_bar.get_text().lower()
            if len(txt) >= 3:
                matches = [n for n in self._all_icon_names if txt in n.lower()]
                new_loader = populate_grid(matches[:500])
                self.p.glib.idle_add(lambda: next(new_loader, False))
            elif not txt:
                reset_loader = populate_grid(self._all_icon_names[:100])
                self.p.glib.idle_add(lambda: next(reset_loader, False))

        search_bar.connect("search-changed", on_search)

        def check_closed():
            if not selector.get_visible():
                self._cleanup_selector()
                return False
            return True

        self.p.glib.timeout_add(250, check_closed)
        self.scrolled.set_child(self.grid)
        main_vbox.append(self.scrolled)
        selector.set_child(main_vbox)
        selector.present()

    def _cleanup_selector(self):
        """Severs the widget tree and clears references for immediate RAM recovery."""
        if hasattr(self, "scrolled") and self.scrolled:
            self.scrolled.set_child(None)  # Discards the entire FlowBox and children

        self.grid = self.p.gtk.FlowBox(
            valign=self.p.gtk.Align.START,
            max_children_per_line=8,
            min_children_per_line=4,
        )
        self.grid.set_selection_mode(self.p.gtk.SelectionMode.NONE)
        self.grid.set_margin_top(12)
        self.grid.set_margin_bottom(12)
        self.grid.set_margin_start(12)
        self.grid.set_margin_end(12)

        if hasattr(self, "scrolled") and self.scrolled:
            self.scrolled.set_child(self.grid)

        self._icon_buttons.clear()
        gc.collect()

    def _select_icon(self, name, selector_window):
        self.current_icon = name
        self.icon_row_image.set_from_icon_name(name)
        self.icon_label.set_text(name)
        selector_window.close()

    def _on_save(self, is_new, old_name, id_ent, cmd_ent):
        new_id = id_ent.get_text()
        new_conf = {"id": new_id, "cmd": cmd_ent.get_text(), "icon": self.current_icon}
        apps = self.p.get_plugin_setting(["app"], [])
        if not is_new:
            for i, a in enumerate(apps):
                if a.get("id") == old_name:
                    apps[i] = new_conf
                    break
        else:
            apps.append(new_conf)
        self.p.config_handler.set_root_setting([str(self.p.plugin_id), "app"], apps)
        self.p.glib.idle_add(self.p._on_config_changed)
        self.window.close()
