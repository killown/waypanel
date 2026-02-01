def get_logic_class():
    from gi.repository import Gtk, Adw
    from typing import Dict, Any, List

    class ControlCenterLogic:
        def __init__(self, plugin_instance):
            self.p = plugin_instance

        def setup_categories_grid(self):
            """Populates the FlowBox with category widgets and the Stack with content pages."""
            self.p.widget_map = {}
            self.p.category_widgets = {}
            self.p.ui_key_to_plugin_id_map = {}

            if not self.p.config:
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
                self.p.content_stack.add_named(label_box, "no_config")
                self.p.main_stack.set_visible_child_name("settings_pages")
                self.p.content_stack.set_visible_child_name("no_config")
                return

            # Clear the FlowBox (Grid)
            while child := self.p.category_flowbox.get_first_child():
                self.p.category_flowbox.remove(child)

            # Clear the Content Stack (The actual settings pages)
            while child := self.p.content_stack.get_first_child():
                self.p.content_stack.remove(child)

            # Theme Page
            THEME_UI_KEY = "theme"
            category_widget = self.p.ui.create_category_widget(THEME_UI_KEY)
            self.p.category_flowbox.insert(category_widget, 0)
            self.p.category_widgets[THEME_UI_KEY] = category_widget
            content_page = self.p.ui._create_theme_page(THEME_UI_KEY)
            self.p.content_stack.add_named(content_page, THEME_UI_KEY)
            self.p.ui_key_to_plugin_id_map[THEME_UI_KEY] = "theme"

            sorted_config_keys = sorted(self.p.config.keys())
            for full_config_key in sorted_config_keys:
                category_data = self.p.config[full_config_key]
                if full_config_key.startswith("org.waypanel.plugin."):
                    ui_key = full_config_key.split(".")[-1]
                else:
                    ui_key = full_config_key

                if ui_key == THEME_UI_KEY:
                    continue

                self.p.ui_key_to_plugin_id_map[ui_key] = full_config_key
                category_widget = self.p.ui.create_category_widget(ui_key)
                self.p.category_flowbox.insert(category_widget, -1)
                self.p.category_widgets[ui_key] = category_widget

                content_page = self.create_content_page(ui_key, category_data)
                self.p.content_stack.add_named(content_page, ui_key)

        def create_content_page(
            self, category_name: str, data: Dict[str, Any]
        ) -> Gtk.ScrolledWindow:
            """Creates a scrollable content page for a given category."""
            full_config_key = self.p.helper._generate_plugin_map(
                self.p.default_config
            ).get(category_name, category_name)

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
                plugin_id = self.p.ui_key_to_plugin_id_map.get(category_name)
                if plugin_id:
                    status_group = Adw.PreferencesGroup(
                        title="Plugin Status",
                        description="Manage the plugin's runtime state.",
                    )
                    disabled_list = self.p.config_handler.get_root_setting(
                        ["plugins", "disabled"], []
                    )
                    plugin_name = plugin_id.split(".")[-1]
                    is_enabled = plugin_name not in disabled_list

                    toggle_switch = Gtk.Switch()
                    toggle_switch.add_css_class("control-center-plugin-enable-switch")
                    toggle_switch.set_active(is_enabled)
                    toggle_switch.connect(
                        "notify::active",
                        self._on_plugin_enable_toggled,
                        category_name,
                    )

                    # Wipe Button
                    wipe_button = Gtk.Button(icon_name="edit-delete-symbolic")
                    wipe_button.add_css_class("destructive-action")
                    wipe_button.set_tooltip_text(f"Wipe {category_name} configuration")
                    wipe_button.set_valign(Gtk.Align.CENTER)
                    wipe_button.connect(
                        "clicked",
                        self.p.helper.on_delete_config_clicked,
                        category_name,
                    )

                    toggle_row = Adw.ActionRow(
                        title="Enable Plugin",
                        subtitle="Toggle the plugin on or off or wipe all settings.",
                    )
                    toggle_row.add_suffix(toggle_switch)
                    toggle_row.add_suffix(wipe_button)
                    toggle_row.set_activatable_widget(toggle_switch)
                    status_group.add(toggle_row)
                    main_box.append(status_group)

            group_desc = self.p.helper._get_hint_for_path(
                self.p.default_config, full_config_key
            )
            preferences_group = Adw.PreferencesGroup(
                title=f"{category_name.replace('_', ' ').capitalize()} Settings",
                description=group_desc,
            )
            preferences_group.add_css_class("control-center-config-group")
            main_box.append(preferences_group)

            self.p.widget_map[category_name] = {}
            for key, value in data.items():
                current_path: List[str] = [full_config_key, key]
                if key.endswith(("_hint", "_section_hint", "_items_hint")):
                    continue

                if isinstance(value, dict):
                    expander = Gtk.Expander.new(
                        f"<b>{key.replace('_', ' ').capitalize()}</b>"
                    )
                    expander.set_use_markup(True)
                    expander.add_css_class("control-center-config-expander")
                    self.p.widget_map[category_name][key] = {}
                    expander_content = self.p.ui.create_nested_widgets(
                        self.p.widget_map[category_name][key], value, current_path
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
                    self.p.widget_map[category_name][key] = []
                    list_content_box = self.p.ui.create_list_widgets(
                        self.p.widget_map[category_name][key], value, current_path
                    )
                    expander.set_child(list_content_box)
                    main_box.append(expander)
                else:
                    widget = self.p.ui.create_widget_for_value(key, value)
                    if not widget:
                        continue

                    hint = self.p.helper._get_hint_for_path(
                        self.p.default_config, *current_path
                    )

                    action_row = Adw.ActionRow(
                        title=key.replace("_", " ").capitalize(), subtitle=hint
                    )
                    action_row.add_css_class("control-center-setting-row")

                    if isinstance(
                        widget,
                        (Gtk.Switch, Gtk.Entry, Gtk.SpinButton, Gtk.ComboBoxText),
                    ):
                        action_row.add_suffix(widget)
                        action_row.set_activatable_widget(widget)
                    else:
                        action_row.set_child(widget)

                    preferences_group.add(action_row)
                    self.p.widget_map[category_name][key] = widget

            add_button = Gtk.Button(label="Add New Field")
            add_button.connect(
                "clicked",
                self.p._on_add_field_clicked,
                preferences_group,
                category_name,
            )
            main_box.append(add_button)

            scrolled_window.set_child(main_box)
            return scrolled_window

        def on_search_changed(self, search_entry):
            """Filters and re-sorts the grid based on user input."""
            query = search_entry.get_text().strip().lower()
            if self.p.main_stack.get_visible_child_name() != "category_grid":
                self.p.on_back_clicked(None)

            for category_name, widget in self.p.category_widgets.items():
                display_name = category_name.replace("_", " ").lower()
                widget.set_visible(query in display_name)

            self.p.category_flowbox.invalidate_filter()
            self.p.category_flowbox.invalidate_sort()

        def _on_plugin_enable_toggled(self, switch, gparam, category_name):
            """Handles persistent plugin state changes."""
            plugin_id = self.p.ui_key_to_plugin_id_map.get(category_name)
            if not plugin_id:
                return

            is_enabled = switch.get_active()
            try:
                plugin_name = plugin_id.split(".")[-1]
                disabled_list_path = ["plugins", "disabled"]
                current_list = self.p.config_handler.get_root_setting(
                    disabled_list_path, []
                )
                new_list = list(current_list)

                if is_enabled and plugin_name in new_list:
                    new_list.remove(plugin_name)
                    self.p.config_handler.update_config(disabled_list_path, new_list)
                    self.p.plugin_loader.reload_plugin(plugin_name)
                elif not is_enabled and plugin_name not in new_list:
                    new_list.append(plugin_name)
                    self.p.config_handler.update_config(disabled_list_path, new_list)
                    self.p.plugin_loader.disable_plugin(plugin_name)

                toast = Adw.Toast.new(
                    f"Plugin '{category_name.capitalize()}' {'enabled' if is_enabled else 'disabled'}."
                )
                self.p.toast_overlay.add_toast(toast)
            except Exception as e:
                self.p.logger.error(f"Failed to toggle plugin {plugin_id}: {e}")
                switch.set_active(not is_enabled)

    return ControlCenterLogic
