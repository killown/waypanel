def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.control_center",
        "name": "ControlCenter",
        "version": "1.0.0",
        "enabled": True,
        "description": "Plugin Control Center for Waypanel",
    }


def get_plugin_class():
    import gi
    from typing import Dict, Any
    import os

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gtk, Adw, Gdk  # pyright: ignore
    from src.plugins.core._base import BasePlugin
    from ._control_center_helpers import ControlCenterHelpers

    class ControlCenter(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.default_config: Dict = self.config_handler.default_config
            self.config = {}
            self.widget_map = {}
            self.helper = ControlCenterHelpers(self)
            self.gtk = Gtk
            self.adw = Adw
            self.toast_overlay: Adw.ToastOverlay = None
            self.win = None
            self.short_to_full_key = self._generate_plugin_map(self.default_config)

        def _generate_plugin_map(self, config):
            plugin_map = {}
            for full_id in config.keys():
                if full_id.startswith("org.waypanel.plugin."):
                    short_name = full_id.split(".")[-1]
                    plugin_map[short_name] = full_id
                else:
                    plugin_map[full_id] = full_id
            return plugin_map

        def display_notify(self, title: str, icon_name: str):
            """Displays an in-app Adw.Toast using the internal ToastOverlay."""
            if not self.toast_overlay:
                print("ERROR: Cannot show toast. Adw.ToastOverlay not initialized.")
                return
            toast = Adw.Toast.new(title)
            if icon_name:
                pass
            self.toast_overlay.add_toast(toast)

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
                if icon_theme.has_icon(icon_name):
                    return icon_name
            tmp_cat_name = category_name.split(".")[-1]
            norm_name_patterns = [
                self._gtk_helper.icon_exist(tmp_cat_name),
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

        def create_content_page(self, category_name, data: Dict[str, Any]):
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
            group_desc = self.helper._get_hint_for_path(category_name)
            preferences_group = Adw.PreferencesGroup(
                title=f"{category_name.replace('_', ' ').capitalize()} Settings",
                description=group_desc,
            )
            preferences_group.add_css_class("control-center-config-group")
            main_box.append(preferences_group)
            self.widget_map[category_name] = {}
            for key, value in data.items():
                current_path = [category_name, key]
                if key.endswith(("_hint", "_section_hint", "_items_hint")):
                    continue
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
                    hint = self.helper._get_hint_for_path(*current_path)
                    if not isinstance(widget, Gtk.Label):
                        widget.set_tooltip_text(hint)
                    action_row = Adw.ActionRow(
                        title=key.replace("_", " ").capitalize(),
                    )
                    action_row.add_css_class("control-center-setting-row")
                    if isinstance(widget, (Gtk.Switch, Gtk.Entry, Gtk.SpinButton)):
                        action_row.add_suffix(widget)
                        action_row.set_activatable_widget(widget)
                    else:
                        action_row.set_child(widget)
                    preferences_group.add(action_row)
                    self.widget_map[category_name][key] = widget
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
            content_page = self._create_theme_page(THEME_UI_KEY)
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
            if category_name in self.short_to_full_key:
                full_config_key = self.short_to_full_key[category_name]

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
                            return text
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
                    else:
                        return
            try:
                self.config_handler.save_config()
                self.display_notify(
                    f"The {category_name.replace('_', ' ').capitalize()} settings have been saved successfully!",
                    "configure-symbolic",
                )
            except Exception as e:
                self.display_notify(
                    f"Error saving {category_name.replace('_', ' ').capitalize()} settings: {e}",
                    "dialog-error",
                )

        def _list_fs_themes(self, dirs: list[str]) -> list[str]:
            """
            Scans directories for theme/icon folders. A theme must contain 'index.theme' or 'gtk-4.0'
            for GTK/Icon themes to be included in the list.
            """
            themes = set()
            for d in dirs:
                full_dir = os.path.expanduser(d)
                if os.path.isdir(full_dir):
                    for item in os.listdir(full_dir):
                        full_path = os.path.join(full_dir, item)
                        if os.path.isdir(full_path) and not item.startswith("."):
                            if os.path.exists(
                                os.path.join(full_path, "index.theme")
                            ) or os.path.exists(os.path.join(full_path, "gtk-4.0")):
                                themes.add(item)
            return sorted(list(themes))

        def _get_current_gsettings_theme(self, schema: str, key: str) -> str:
            """Reads the current theme setting using gsettings."""
            try:
                result = (
                    os.popen(f"gsettings get {schema} {key} 2>/dev/null").read().strip()
                )
                if result and result.startswith("'") and result.endswith("'"):
                    return result[1:-1]
                return result
            except Exception:
                return ""

        def _on_gsettings_theme_selected(
            self, combobox: Gtk.ComboBoxText, schema: str, key: str
        ):
            """Applies the selected theme using gsettings set."""
            selected_theme = combobox.get_active_text()
            if not selected_theme or selected_theme == "(No themes found)":
                return
            try:
                command = f"gsettings set {schema} {key} '{selected_theme}'"
                os.system(command)
                display_name = key.replace("-", " ").capitalize()
                self.display_notify(
                    f"{display_name} set to {selected_theme}.",
                    "preferences-desktop-theme-symbolic",
                )
            except Exception as e:
                self.display_notify(
                    f"Error applying {key.replace('-', ' ')}: {e}",
                    "dialog-error-symbolic",
                )

        def _create_gsettings_theme_row(
            self,
            title: str,
            subtitle: str,
            schema: str,
            key: str,
            theme_dirs: list[str],
        ) -> Adw.ActionRow:
            """Creates an Adw.ActionRow with a ComboBoxText for a gsettings theme."""
            theme_names = self._list_fs_themes(theme_dirs)
            current_theme = self._get_current_gsettings_theme(schema, key)
            if not theme_names:
                theme_names = ["(No themes found)"]
                current_theme = theme_names[0]
            combobox = self.gtk.ComboBoxText.new()
            active_index = -1
            for i, theme in enumerate(theme_names):
                combobox.append_text(theme)
                if theme == current_theme:
                    active_index = i
            if active_index != -1:
                combobox.set_active(active_index)
            elif theme_names and theme_names[0] != "(No themes found)":
                combobox.set_active(0)
            combobox.set_halign(self.gtk.Align.END)
            combobox.connect("changed", self._on_gsettings_theme_selected, schema, key)
            action_row = self.adw.ActionRow(
                title=title,
                subtitle=subtitle,
            )
            action_row.add_suffix(combobox)
            action_row.set_activatable_widget(combobox)
            action_row.add_css_class("control-center-setting-row")
            if current_theme == "(No themes found)":
                combobox.set_sensitive(False)
            return action_row

        def _get_available_themes(self) -> list[str]:
            """
            Fetches a list of available Waypanel CSS themes by scanning the local directory.
            """
            css_dir = os.path.expanduser("~/.local/share/waypanel/resources/themes/css")
            if not os.path.isdir(css_dir):
                return []
            return sorted(
                [
                    f.split(".")[0]
                    for f in os.listdir(css_dir)
                    if os.path.isfile(os.path.join(css_dir, f)) and f.endswith(".css")
                ]
            )

        def _on_theme_selected(self, combobox: Gtk.ComboBoxText):
            """
            Handles the combobox selection, applies the theme via Gtk.Settings,
            and saves the preference to the Waypanel config under [panel.theme] default.
            """
            selected_theme = combobox.get_active_text()
            if not selected_theme:
                return
            MAIN_CONFIG_KEY = "panel"
            NESTED_CONFIG_KEY = "theme"
            DEFAULT_KEY = "default"
            if self.config:
                if MAIN_CONFIG_KEY not in self.config:
                    self.config[MAIN_CONFIG_KEY] = {}
                if NESTED_CONFIG_KEY not in self.config[MAIN_CONFIG_KEY]:
                    self.config[MAIN_CONFIG_KEY][NESTED_CONFIG_KEY] = {}
                self.config[MAIN_CONFIG_KEY][NESTED_CONFIG_KEY][DEFAULT_KEY] = (
                    selected_theme
                )
            else:
                self.logger.warning("Cannot find the config for the theme selection.")
            try:
                self.config_handler.save_config()
                if hasattr(self._panel_instance, "apply_theme"):
                    self._panel_instance.apply_theme(selected_theme)
                self.display_notify(
                    f"Waypanel theme set to {selected_theme}. Panel may require restart to fully apply to all widgets.",
                    "preferences-desktop-theme-symbolic",
                )
            except Exception as e:
                self.display_notify(
                    f"Error saving theme setting: {e}", "dialog-error-symbolic"
                )

        def _create_theme_selector_widget(self) -> Adw.ActionRow:
            """
            Creates the Adw.ActionRow with the Gtk.ComboBoxText for Waypanel theme selection.
            """
            theme_names = self._get_available_themes()
            MAIN_CONFIG_KEY = "panel"
            NESTED_CONFIG_KEY = "theme"
            DEFAULT_KEY = "default"

            current_theme = (
                self.config.get(MAIN_CONFIG_KEY, {})  # pyright: ignore
                .get(NESTED_CONFIG_KEY, {})
                .get(DEFAULT_KEY, None)
            )
            if not current_theme or current_theme not in theme_names:
                current_theme = theme_names[0] if theme_names else "default"
            combobox = self.gtk.ComboBoxText.new()
            active_index = -1
            for i, theme in enumerate(theme_names):
                combobox.append_text(theme)
                if theme == current_theme:
                    active_index = i
            if active_index != -1:
                combobox.set_active(active_index)
            combobox.set_halign(self.gtk.Align.END)
            combobox.connect("changed", self._on_theme_selected)
            action_row = self.adw.ActionRow(
                title="Waypanel CSS Theme",
                subtitle="Select the theme for Waypanel's internal components.",
            )
            action_row.add_suffix(combobox)
            action_row.set_activatable_widget(combobox)
            action_row.add_css_class("control-center-setting-row")
            return action_row

        def _create_theme_page(self, ui_key: str) -> Gtk.ScrolledWindow:
            """
            Creates the dedicated settings page for theme selection with all three options.
            """
            scrolled_window = self.gtk.ScrolledWindow()
            scrolled_window.set_policy(
                self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.AUTOMATIC
            )
            main_box = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=10
            )
            main_box.add_css_class("control-center-content-area")
            main_box.set_margin_top(20)
            main_box.set_margin_bottom(20)
            main_box.set_margin_start(20)
            main_box.set_margin_end(20)
            preferences_group = self.adw.PreferencesGroup(
                title="Appearance Settings",
                description="Change the look and feel of Waypanel and GTK applications.",
            )
            preferences_group.add_css_class("control-center-config-group")
            waypanel_theme_row = self._create_theme_selector_widget()
            preferences_group.add(waypanel_theme_row)
            gtk_theme_dirs = ["/usr/share/themes", "~/.local/share/themes", "~/.themes"]
            gtk_theme_row = self._create_gsettings_theme_row(
                title="GTK Theme",
                subtitle="Select the theme for GTK 4/3 applications (applied via gsettings).",
                schema="org.gnome.desktop.interface",
                key="gtk-theme",
                theme_dirs=gtk_theme_dirs,
            )
            preferences_group.add(gtk_theme_row)
            icon_theme_dirs = ["/usr/share/icons", "~/.local/share/icons", "~/.icons"]
            icon_theme_row = self._create_gsettings_theme_row(
                title="Icon Theme",
                subtitle="Select the icon theme for applications (applied via gsettings).",
                schema="org.gnome.desktop.interface",
                key="icon-theme",
                theme_dirs=icon_theme_dirs,
            )
            preferences_group.add(icon_theme_row)
            main_box.append(preferences_group)
            scrolled_window.set_child(main_box)
            return scrolled_window

    return ControlCenter
