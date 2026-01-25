def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.control_center",
        "name": "ControlCenter",
        "version": "1.0.0",
        "enabled": True,
        "priority": 99,
        "deps": ["css_generator"],
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
            self.ui_key_to_plugin_id_map: Dict[str, str] = {}
            self.helper = ControlCenterHelpers(self)
            self.toast_overlay: Adw.ToastOverlay = None
            self.gtk = Gtk
            self.adw = Adw
            self.win = None
            self.plugins["css_generator"].install_css("control-center.css")

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
            """
            full_config_key = self.helper._generate_plugin_map(self.default_config).get(
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
            if category_name != "control_center":
                plugin_id = self.ui_key_to_plugin_id_map.get(category_name)
                if plugin_id:
                    status_group = Adw.PreferencesGroup(
                        title="Plugin Status",
                        description="Manage the plugin's runtime state.",
                    )
                    disabled_list = self.config_handler.get_root_setting(
                        ["plugins", "disabled"], []
                    )
                    plugin_name = plugin_id.split(".")[-1]
                    is_enabled = plugin_name not in disabled_list
                    toggle_switch = Gtk.Switch()
                    toggle_switch.add_css_class("control-center-plugin-enable-switch")
                    toggle_switch.set_active(is_enabled)
                    toggle_switch.connect(
                        "notify::active", self._on_plugin_enable_toggled, category_name
                    )
                    toggle_row = Adw.ActionRow(
                        title="Enable Plugin",
                        subtitle="Toggle the plugin on or off. Changes are persistent.",
                    )
                    toggle_row.add_suffix(toggle_switch)
                    toggle_row.set_activatable_widget(toggle_switch)
                    status_group.add(toggle_row)
                    main_box.append(status_group)
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
            self.ui_key_to_plugin_id_map = {}
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
            self.ui_key_to_plugin_id_map[THEME_UI_KEY] = "theme"
            sorted_config_keys = sorted(self.config.keys())
            for full_config_key in sorted_config_keys:
                category_data = self.config[full_config_key]
                if full_config_key.startswith("org.waypanel.plugin."):
                    ui_key = full_config_key.split(".")[-1]
                else:
                    ui_key = full_config_key
                if ui_key == THEME_UI_KEY:
                    continue
                self.ui_key_to_plugin_id_map[ui_key] = full_config_key
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
            """Handles saving the configuration for the currently visible category."""
            current_category = self.content_stack.get_visible_child_name()
            if current_category:
                self.helper.save_category(current_category)

        def _on_plugin_enable_toggled(
            self, switch: Gtk.Switch, gparam, category_name: str
        ):
            """
            Handles the 'Enable Plugin' switch state change.
            This method orchestrates both persistent and runtime state changes.
            1.  Persists the change by adding/removing the plugin's full ID
                from `[plugins].disabled` via ConfigHandler.
            2.  Stops/starts the running instance via PluginLoader.
            """
            plugin_id = self.ui_key_to_plugin_id_map.get(category_name)
            if not plugin_id:
                self.logger.error(
                    f"Could not find full plugin ID for UI key: {category_name}. Cannot toggle."
                )
                return
            is_enabled = switch.get_active()
            self.logger.info(
                f"Request to toggle plugin '{plugin_id}'. New state: {'ENABLED' if is_enabled else 'DISABLED'}"
            )
            try:
                plugin_name = plugin_id.split(".")[-1]
                disabled_list_path = ["plugins", "disabled"]
                current_disabled_list = self.config_handler.get_root_setting(
                    disabled_list_path, []
                )
                new_disabled_list = list(current_disabled_list)
                if is_enabled:
                    if plugin_name in new_disabled_list:
                        new_disabled_list.remove(plugin_name)
                        self.config_handler.update_config(
                            disabled_list_path, new_disabled_list
                        )
                    self.plugin_loader.reload_plugin(plugin_name)
                    toast = Adw.Toast.new(
                        f"Plugin '{category_name.capitalize()}' enabled."
                    )
                else:
                    if plugin_name not in new_disabled_list:
                        new_disabled_list.append(plugin_name)
                        self.config_handler.update_config(
                            disabled_list_path, new_disabled_list
                        )
                    self.plugin_loader.disable_plugin(plugin_name)
                    toast = Adw.Toast.new(
                        f"Plugin '{category_name.capitalize()}' disabled."
                    )
                self.toast_overlay.add_toast(toast)
            except Exception as e:
                self.logger.error(
                    f"Failed to toggle plugin '{plugin_id}': {e}", exc_info=True
                )
                toast = Adw.Toast.new(f"Error toggling plugin: {category_name}")
                self.toast_overlay.add_toast(toast)
                switch.set_active(not is_enabled)

    return ControlCenter
