def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.control_center",
        "name": "ControlCenter",
        "version": "1.0.0",
        "enabled": True,
        "priority": 99,
        "description": "Plugin Control Center for Waypanel",
    }


def get_plugin_class():
    import gi
    from typing import Dict, Any, List

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gtk, Adw, Gdk  # pyright: ignore
    from src.plugins.core._base import BasePlugin
    from ._control_center_helpers import ControlCenterHelpers

    class ControlCenter(BasePlugin):
        """
        The main Control Center window, responsible for loading the configuration
        categories and managing widget state.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.config = {}
            self.widget_map = {}
            self.helper = ControlCenterHelpers(self)
            self.toast_overlay: Adw.ToastOverlay = None
            self.gtk = Gtk
            self.adw = Adw
            self.win = None

        def _generate_plugin_map(self, config):
            plugin_map = {}
            for full_id in config.keys():
                if full_id.startswith("org.waypanel.plugin."):
                    short_name = full_id.split(".")[-1]
                    plugin_map[short_name] = full_id
                else:
                    plugin_map[full_id] = full_id
            return plugin_map

        def create_category_widget(self, category_name: str) -> Gtk.Widget:
            """
            Creates a centered, clickable icon-and-label widget for the category,
            similar to a search engine's main page widget.
            """
            display_name = category_name.replace("_", " ").capitalize()
            icon_name = self.get_icon_for_category(category_name)
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            vbox.set_hexpand(True)
            vbox.set_vexpand(True)
            vbox.set_halign(Gtk.Align.CENTER)
            vbox.set_valign(Gtk.Align.CENTER)
            vbox.add_css_class("control-center-vbox-item")
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(64)
            icon.add_css_class("control-center-category-icon")
            label = Gtk.Label(label=display_name)
            label.set_halign(Gtk.Align.CENTER)
            vbox.append(icon)
            vbox.append(label)
            container = Gtk.Box()
            container.set_size_request(150, 120)
            container.set_halign(Gtk.Align.CENTER)
            container.add_css_class("control-center-category-widget")
            container.append(vbox)
            gesture = Gtk.GestureClick.new()
            gesture.connect("released", self.on_category_widget_clicked, category_name)
            container.add_controller(gesture)
            return container

        def on_back_clicked(self, button):
            """Switches the view back to the main category grid and clears the search."""
            self.main_stack.set_visible_child_name("category_grid")
            self.save_button_stack.set_visible_child_name("empty")
            self.back_button_stack.set_visible_child_name("empty")
            self.search_entry.set_text("")

        def on_close_request(self, window):
            """Handle the close-request signal to properly destroy the window."""
            window.destroy()
            self.win = None
            return True

        def do_activate(self):
            if not self.win:
                self.win = Adw.ApplicationWindow()
                self.win.add_css_class("control-center-window")
                self.win.connect("close-request", self.on_close_request)
                self.win.set_title("Waypanel Control Center")
                self.win.set_default_size(800, 600)
                main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
                header_bar = Adw.HeaderBar()
                header_bar.add_css_class("control-center-header")
                main_vbox.append(header_bar)
                self.back_button = Gtk.Button()
                self.back_button.set_icon_name("go-previous-symbolic")
                self.back_button.add_css_class("flat")
                self.back_button.set_tooltip_text("Back to Categories")
                self.back_button.connect("clicked", self.on_back_clicked)
                self.back_button_stack = Gtk.Stack()
                self.back_button_stack.add_named(Gtk.Box(), "empty")
                self.back_button_stack.add_named(self.back_button, "back_button")
                self.back_button_stack.set_visible_child_name("empty")
                header_bar.pack_start(self.back_button_stack)
                self.save_button = Gtk.Button(label="Save")
                self.save_button.add_css_class("suggested-action")
                self.save_button.add_css_class("control-center-save-button")
                self.save_button.connect("clicked", self.on_save_clicked)
                self.save_button_stack = Gtk.Stack()
                self.save_button_stack.set_vexpand(False)
                self.save_button_stack.set_hexpand(False)
                empty_box = Gtk.Box()
                self.save_button_stack.add_named(empty_box, "empty")
                self.save_button_stack.add_named(self.save_button, "save_button")
                self.save_button_stack.set_visible_child_name("empty")
                header_bar.pack_end(self.save_button_stack)
                search_container = Gtk.Box()
                search_container.set_margin_top(40)
                search_container.set_margin_bottom(20)
                search_container.set_halign(Gtk.Align.CENTER)
                self.search_entry = Gtk.SearchEntry()
                self.search_entry.set_placeholder_text("Search settings or category...")
                self.search_entry.set_width_chars(60)
                self.search_entry.set_max_width_chars(80)
                self.search_entry.connect("search-changed", self.on_search_changed)
                search_container.append(self.search_entry)
                main_vbox.append(search_container)
                self.category_flowbox = Gtk.FlowBox()
                self.category_flowbox.set_homogeneous(False)
                self.category_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
                self.category_flowbox.set_row_spacing(20)
                self.category_flowbox.set_column_spacing(20)
                self.category_flowbox.set_halign(Gtk.Align.CENTER)
                self.category_flowbox.add_css_class("control-center-category-grid")
                flowbox_scrolled = Gtk.ScrolledWindow()
                flowbox_scrolled.set_child(self.category_flowbox)
                flowbox_scrolled.set_policy(
                    Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC
                )
                flowbox_scrolled.set_vexpand(True)
                flowbox_scrolled.set_hexpand(True)
                self.content_stack = Gtk.Stack()
                self.content_stack.set_vexpand(True)
                self.content_stack.set_hexpand(True)
                self.main_stack = Gtk.Stack()
                self.main_stack.set_vexpand(True)
                self.main_stack.set_hexpand(True)
                self.main_stack.add_named(flowbox_scrolled, "category_grid")
                self.main_stack.add_named(self.content_stack, "settings_pages")
                main_vbox.append(self.main_stack)
                self.toast_overlay = Adw.ToastOverlay.new()
                self.toast_overlay.set_child(main_vbox)
                self.win.set_content(self.toast_overlay)
                self.load_config()
                self.setup_categories_grid()
                self.main_stack.set_visible_child_name("category_grid")
                self.save_button_stack.set_visible_child_name("empty")
                self.back_button_stack.set_visible_child_name("empty")
            self.win.present()

        def get_icon_for_category(self, category_name: str) -> str:
            norm_name = category_name.replace("_", " ").split()[0].lower()
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            icon_patterns = [
                norm_name,
                f"{norm_name}-symbolic",
                f"preferences-{norm_name}-symbolic",
                f"utilities-{norm_name}-symbolic",
            ]
            for icon_name in icon_patterns:
                icon_name = self._gtk_helper.icon_exist(norm_name)
                if icon_name:
                    return icon_name
            tmp_cat_name = category_name.split(".")[-1]
            norm_name_patterns = [
                tmp_cat_name,
                f"{norm_name}-symbolic",
                f"preferences-{norm_name}-symbolic",
                f"utilities-{norm_name}-symbolic",
            ]
            for icon_name in norm_name_patterns:
                if icon_theme.has_icon(icon_name):
                    return icon_name
            fallback_map = {
                "wayfire": "preferences-desktop-display-symbolic",
                "scripts": "utilities-terminal-symbolic",
                "wallpaper": "preferences-desktop-wallpaper-symbolic",
                "panel": "preferences-system-symbolic",
                "settings": "preferences-system-symbolic",
                "theme": "preferences-desktop-theme-symbolic",
                "colors": "preferences-desktop-color-symbolic",
                "keyboard": "input-keyboard-symbolic",
                "mouse": "input-mouse-symbolic",
                "network": "network-wired-symbolic",
                "app-launcher": "system-run-symbolic",
                "powermenu": "system-shutdown-symbolic",
                "main": "preferences-panel-symbolic",
                "folders": "folder",
                "menu": "application-menu",
                "launcher": "app-launcher",
                "cmd": "terminal",
            }
            if norm_name in fallback_map:
                return fallback_map[norm_name]
            return "preferences-system-symbolic"

        def load_config(self):
            self.config = self.config_handler.config_data

        def _on_add_field_clicked(self, button, group, category_name):
            """Handler to add a new key-value row with an optional path to the UI."""
            path_entry = Gtk.Entry(placeholder_text="Sub-path (optional, e.g., 'a.b')")
            key_entry = Gtk.Entry(placeholder_text="Key")
            value_entry = Gtk.Entry(placeholder_text="Value")
            if "_dynamic_fields" not in self.widget_map[category_name]:
                self.widget_map[category_name]["_dynamic_fields"] = []
            self.widget_map[category_name]["_dynamic_fields"].append(
                (path_entry, key_entry, value_entry)
            )
            action_row = Adw.ActionRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.append(path_entry)
            box.append(key_entry)
            box.append(value_entry)
            action_row.set_child(box)
            parent = button.get_parent()
            parent.remove(button)
            group.add(action_row)
            parent.append(button)

        def create_content_page(
            self, category_name: str, data: Dict[str, Any]
        ) -> Gtk.ScrolledWindow:
            """
            Creates a scrollable content page for a given category by generating
            appropriate Gtk/Adw widgets for each configuration key-value pair.
            The full configuration path is resolved here to ensure hints are correctly loaded.
            """
            full_config_key = self._generate_plugin_map(self.default_config).get(
                category_name, category_name
            )
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
            )
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            main_box.add_css_class("control-center-content-area")
            main_box.set_margin_top(20)
            main_box.set_margin_bottom(20)
            main_box.set_margin_start(20)
            main_box.set_margin_end(20)
            group_desc = self.helper._get_hint_for_path(
                self.default_config, full_config_key
            )
            preferences_group = Adw.PreferencesGroup(
                title=f"{category_name.replace('_', ' ').capitalize()} Settings",
                description=group_desc,
            )
            preferences_group.add_css_class("control-center-config-group")
            main_box.append(preferences_group)
            self.widget_map[category_name] = {}
            for key, value in data.items():
                current_path: List[str] = [full_config_key, key]
                if key.endswith(("_hint", "_section_hint", "_items_hint")):
                    continue  # pyright: ignore
                if isinstance(value, dict):
                    expander = Gtk.Expander.new(
                        f"<b>{key.replace('_', ' ').capitalize()}</b>"
                    )
                    expander.set_use_markup(True)
                    expander.add_css_class("control-center-config-expander")
                    self.widget_map[category_name][key] = {}
                    expander_content = self.helper.create_nested_widgets(
                        self.widget_map[category_name][key], value, current_path
                    )
                    expander.set_child(expander_content)
                    main_box.append(expander)
                elif isinstance(value, list) and all(
                    isinstance(item, dict) for item in value
                ):
                    expander = Gtk.Expander.new(
                        f"<b>{key.replace('_', ' ').capitalize()}</b>"
                    )
                    expander.set_use_markup(True)
                    expander.add_css_class("control-center-config-expander")
                    self.widget_map[category_name][key] = []
                    list_content_box = self.helper.create_list_widgets(
                        self.widget_map[category_name][key], value, current_path
                    )
                    expander.set_child(list_content_box)
                    main_box.append(expander)
                else:
                    widget = self.helper.create_widget_for_value(value)
                    if not widget:
                        continue
                    hint = self.helper._get_hint_for_path(
                        self.default_config, *current_path
                    )
                    if not isinstance(widget, Gtk.Label):
                        widget.set_tooltip_text(hint)
                    action_row = Adw.ActionRow(
                        title=key.replace("_", " ").capitalize(), subtitle=hint
                    )
                    action_row.add_css_class("control-center-setting-row")
                    if isinstance(widget, (Gtk.Switch, Gtk.Entry, Gtk.SpinButton)):
                        action_row.add_suffix(widget)
                        action_row.set_activatable_widget(widget)
                    else:
                        action_row.set_child(widget)
                    preferences_group.add(action_row)
                    self.widget_map[category_name][key] = widget
            add_button = Gtk.Button(label="Add New Field")
            add_button.connect(
                "clicked", self._on_add_field_clicked, preferences_group, category_name
            )
            main_box.append(add_button)
            scrolled_window.set_child(main_box)
            return scrolled_window

        def setup_categories_grid(self):
            """Populates the FlowBox with category widgets and the Stack with content pages."""
            self.widget_map = {}
            self.category_widgets = {}
            if not self.config:
                label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                label = Gtk.Label(
                    label="No configuration data found or loaded via ConfigHandler.\n\n"
                    "Please ensure config.toml exists and is valid.",
                    halign=Gtk.Align.CENTER,
                    valign=Gtk.Align.CENTER,
                    justify=Gtk.Justification.CENTER,
                )
                label.set_wrap(True)
                label_box.append(label)
                self.content_stack.add_named(label_box, "no_config")
                self.main_stack.set_visible_child_name("settings_pages")
                self.content_stack.set_visible_child_name("no_config")
                return
            for child in self.category_flowbox:
                self.category_flowbox.remove(child)
            THEME_UI_KEY = "theme"
            category_widget = self.create_category_widget(THEME_UI_KEY)
            self.category_flowbox.insert(category_widget, 0)
            self.category_widgets[THEME_UI_KEY] = category_widget
            content_page = self.helper._create_theme_page(THEME_UI_KEY)
            self.content_stack.add_named(content_page, THEME_UI_KEY)
            sorted_config_keys = sorted(self.config.keys())
            for full_config_key in sorted_config_keys:
                category_data = self.config[full_config_key]
                if full_config_key.startswith("org.waypanel.plugin."):
                    ui_key = full_config_key.split(".")[-1]
                else:
                    ui_key = full_config_key
                if ui_key == THEME_UI_KEY:
                    continue
                category_widget = self.create_category_widget(ui_key)
                self.category_flowbox.insert(category_widget, -1)
                self.category_widgets[ui_key] = category_widget
                content_page = self.create_content_page(ui_key, category_data)
                self.content_stack.add_named(content_page, ui_key)

        def on_category_widget_clicked(self, gesture, n_press, x, y, category_name):
            """Called when a category icon/widget is clicked. category_name is the UI key (short name)."""
            self.content_stack.set_visible_child_name(category_name)
            self.main_stack.set_visible_child_name("settings_pages")
            if category_name != "theme":
                self.save_button_stack.set_visible_child_name("save_button")
            else:
                self.save_button_stack.set_visible_child_name("empty")
            self.back_button_stack.set_visible_child_name("back_button")

        def on_search_changed(self, search_entry):
            """Filters the category widgets based on the search query."""
            query = search_entry.get_text().strip().lower()
            if self.main_stack.get_visible_child_name() != "category_grid":
                self.main_stack.set_visible_child_name("category_grid")
                self.save_button_stack.set_visible_child_name("empty")
                self.back_button_stack.set_visible_child_name("empty")
            for category_name, widget in self.category_widgets.items():
                display_name = category_name.replace("_", " ").lower()
                if query in display_name:
                    widget.set_visible(True)
                else:
                    widget.set_visible(False)

        def on_save_clicked(self, button):
            current_category = self.content_stack.get_visible_child_name()
            if current_category:
                self.save_category(current_category)

        def save_category(self, category_name):
            full_config_key = category_name
            plugin_map = self._generate_plugin_map(self.default_config)
            if category_name in plugin_map:
                full_config_key = plugin_map[category_name]

            def get_value_from_widget(widget):
                if isinstance(widget, Gtk.Entry):
                    text = widget.get_text()
                    if hasattr(widget, "original_type") and getattr(
                        widget, "original_type", "str"
                    ):

                        def cast_element(s):
                            s = s.strip()
                            original_type_str = getattr(widget, "original_type", "str")
                            if original_type_str == "int":
                                try:
                                    return int(s)
                                except ValueError:
                                    return s
                            elif original_type_str == "float":
                                try:
                                    return float(s)
                                except ValueError:
                                    return s
                            return s

                        return [
                            cast_element(x) for x in text.split(",") if x.strip() != ""
                        ]
                    try:
                        return int(text)
                    except (ValueError, TypeError):
                        try:
                            return float(text)
                        except (ValueError, TypeError):
                            if text.lower() == "true":
                                return True
                            if text.lower() == "false":
                                return False
                            return text
                elif isinstance(widget, Gtk.SpinButton):
                    val = widget.get_value()
                    if val == int(val):
                        return int(val)
                    return val
                elif isinstance(widget, Gtk.Switch):
                    return widget.get_active()
                return None

            def update_config_from_widgets(config_dict, widget_dict):
                for key, value in widget_dict.items():
                    if key == "_dynamic_fields":
                        continue
                    if isinstance(value, dict):
                        if key in config_dict:
                            update_config_from_widgets(config_dict[key], value)
                    elif isinstance(value, list):
                        if key in config_dict and isinstance(config_dict[key], list):
                            for i, list_item_widgets in enumerate(value):
                                if i < len(config_dict[key]):
                                    cmd_entry = list_item_widgets.get("cmd_entry")
                                    name_entry = list_item_widgets.get("name_entry")
                                    if cmd_entry:
                                        config_dict[key][i]["cmd"] = (
                                            get_value_from_widget(cmd_entry)
                                        )
                                    if name_entry:
                                        config_dict[key][i]["name"] = (
                                            get_value_from_widget(name_entry)
                                        )
                    else:
                        new_value = get_value_from_widget(value)
                        if new_value is not None:
                            config_dict[key] = new_value

            if category_name in self.widget_map:
                if self.config:
                    if full_config_key in self.config:
                        update_config_from_widgets(
                            self.config[full_config_key],
                            self.widget_map[category_name],
                        )
                        if "_dynamic_fields" in self.widget_map[category_name]:
                            dynamic_fields = self.widget_map[category_name][
                                "_dynamic_fields"
                            ]
                            for path_widget, key_widget, value_widget in dynamic_fields:
                                key = key_widget.get_text().strip()
                                path_str = path_widget.get_text().strip()
                                if not key:
                                    continue
                                value = get_value_from_widget(value_widget)
                                current_level = self.config[full_config_key]
                                if path_str:
                                    path_parts = path_str.split(".")
                                    for part in path_parts:
                                        current_level = current_level.setdefault(
                                            part, {}
                                        )
                                current_level[key] = value
                    else:
                        return
            try:
                self.config_handler.save_config()
                self.helper.display_notify(
                    f"The {category_name.replace('_', ' ').capitalize()} settings have been saved successfully!",
                    "configure-symbolic",
                )
            except Exception as e:
                self.helper.display_notify(
                    f"Error saving {category_name.replace('_', ' ').capitalize()} settings: {e}",
                    "dialog-error",
                )

    return ControlCenter
