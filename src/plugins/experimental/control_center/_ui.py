def get_ui_class():
    from gi.repository import Gtk, Adw
    from typing import Any, List, Dict, Union
    from ._helpers import ControlCenterHelpers

    class ControlCenterUI:
        def __init__(self, plugin_instance):
            self.p = plugin_instance
            self.gtk = Gtk
            self.adw = Adw
            self._helpers = ControlCenterHelpers(plugin_instance)
            self.parent = self._helpers.parent

        def create_window(self):
            """Initializes the main application window and its base layout."""
            win = self.adw.ApplicationWindow()
            win.add_css_class("control-center-window")
            win.set_title("Waypanel Control Center")
            win.set_default_size(1600, 800)

            main_vbox = self.gtk.Box(
                orientation=self.gtk.Orientation.VERTICAL, spacing=30
            )

            # Header
            header_bar = self.adw.HeaderBar()
            header_bar.add_css_class("control-center-header")

            # Back Button
            self.p.back_button = self.gtk.Button(icon_name="go-previous-symbolic")
            self.p.back_button.add_css_class("flat")
            self.p.back_button.connect("clicked", self.p.on_back_clicked)

            self.p.back_button_stack = self.gtk.Stack()
            self.p.back_button_stack.add_named(self.gtk.Box(), "empty")
            self.p.back_button_stack.add_named(self.p.back_button, "back_button")
            header_bar.pack_start(self.p.back_button_stack)

            # Save Button
            self.p.save_button = self.gtk.Button(label="Save")
            self.p.save_button.add_css_class("suggested-action")
            self.p.save_button.connect("clicked", self.p.on_save_clicked)

            self.p.save_button_stack = self.gtk.Stack()
            self.p.save_button_stack.add_named(self.gtk.Box(), "empty")
            self.p.save_button_stack.add_named(self.p.save_button, "save_button")
            header_bar.pack_end(self.p.save_button_stack)

            main_vbox.append(header_bar)

            # Search
            search_container = self.gtk.Box(margin_top=40, margin_bottom=20)
            search_container.set_halign(self.gtk.Align.CENTER)
            self.p.search_entry = self.gtk.SearchEntry(
                placeholder_text="Search settings or category..."
            )
            self.p.search_entry.set_width_chars(60)
            self.p.search_entry.set_max_width_chars(80)
            self.p.search_entry.connect("search-changed", self.p.on_search_changed)
            search_container.append(self.p.search_entry)
            main_vbox.append(search_container)

            # FlowBox Setup
            self.p.category_flowbox = self.gtk.FlowBox()
            self.p.category_flowbox.set_homogeneous(True)
            self.p.category_flowbox.set_filter_func(self._flowbox_filter_func)
            self.p.category_flowbox.set_selection_mode(self.gtk.SelectionMode.NONE)
            self.p.category_flowbox.set_row_spacing(20)
            self.p.category_flowbox.set_column_spacing(20)

            # Anchor items to top-left of the FlowBox area
            self.p.category_flowbox.set_halign(self.gtk.Align.START)
            self.p.category_flowbox.set_valign(self.gtk.Align.START)
            self.p.category_flowbox.add_css_class("control-center-category-grid")

            # This keeps the grid in the middle without restricting its width to one column
            centering_box = self.gtk.Box(orientation=self.gtk.Orientation.HORIZONTAL)
            centering_box.set_halign(self.gtk.Align.CENTER)
            centering_box.append(self.p.category_flowbox)

            flowbox_scrolled = self.gtk.ScrolledWindow(vexpand=True, hexpand=True)
            flowbox_scrolled.set_child(centering_box)
            flowbox_scrolled.set_policy(
                self.gtk.PolicyType.NEVER, self.gtk.PolicyType.AUTOMATIC
            )

            self.p.content_stack = self.gtk.Stack(vexpand=True, hexpand=True)
            self.p.main_stack = self.gtk.Stack(vexpand=True, hexpand=True)
            self.p.main_stack.add_named(flowbox_scrolled, "category_grid")
            self.p.main_stack.add_named(self.p.content_stack, "settings_pages")

            main_vbox.append(self.p.main_stack)

            self.p.toast_overlay = self.adw.ToastOverlay.new()
            self.p.toast_overlay.set_child(main_vbox)
            win.set_content(self.p.toast_overlay)

            return win

        def _flowbox_filter_func(self, child):
            """Internal GTK filter to ensure the FlowBox handles hidden children correctly."""
            return child.get_child().get_visible()

        def _create_theme_selector_widget(self) -> Adw.ActionRow:
            theme_names = self._helpers._get_available_themes()
            MAIN_CONFIG_KEY = "org.waypanel.panel"
            NESTED_CONFIG_KEY = "theme"
            DEFAULT_KEY = "default"
            current_theme = (
                self.parent.config.get(MAIN_CONFIG_KEY, {})  # pyright: ignore
                .get(NESTED_CONFIG_KEY, {})
                .get(DEFAULT_KEY, None)
            )
            if not current_theme or current_theme not in theme_names:
                current_theme = theme_names[0] if theme_names else "default"
            combobox = Gtk.ComboBoxText.new()
            active_index = -1
            for i, theme in enumerate(theme_names):
                combobox.append_text(theme)
                if theme == current_theme:
                    active_index = i
            if active_index != -1:
                combobox.set_active(active_index)
            combobox.set_halign(Gtk.Align.END)
            combobox.connect("changed", self._helpers._on_theme_selected)
            action_row = Adw.ActionRow(
                title="Waypanel CSS Theme",
                subtitle="Select the theme for Waypanel's internal components.",
            )
            action_row.add_suffix(combobox)
            action_row.set_activatable_widget(combobox)
            action_row.add_css_class("control-center-setting-row")
            return action_row

        def _create_gsettings_theme_row(
            self,
            title: str,
            subtitle: str,
            schema: str,
            key: str,
            theme_dirs: list[str],
        ) -> Adw.ActionRow:
            theme_names = self._helpers._list_fs_themes(theme_dirs)
            current_theme = self._helpers._get_current_gsettings_theme(schema, key)
            if not theme_names:
                theme_names = ["(No themes found)"]
                current_theme = theme_names[0]
            combobox = Gtk.ComboBoxText.new()
            active_index = -1
            for i, theme in enumerate(theme_names):
                combobox.append_text(theme)
                if theme == current_theme:
                    active_index = i
            if active_index != -1:
                combobox.set_active(active_index)
            elif theme_names and theme_names[0] != "(No themes found)":
                combobox.set_active(0)
            combobox.set_halign(Gtk.Align.END)
            combobox.connect(
                "changed", self._helpers._on_gsettings_theme_selected, schema, key
            )
            action_row = Adw.ActionRow(
                title=title,
                subtitle=subtitle,
            )
            action_row.add_suffix(combobox)
            action_row.set_activatable_widget(combobox)
            action_row.add_css_class("control-center-setting-row")
            if current_theme == "(No themes found)":
                combobox.set_sensitive(False)
            return action_row

        def _create_theme_page(self, ui_key: str) -> Gtk.ScrolledWindow:
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
            preferences_group = Adw.PreferencesGroup(
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

        def create_nested_widgets(
            self,
            widget_dict: Dict[str, Any],
            subdict: Dict[str, Any],
            current_path: List[str],
        ) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.add_css_class("control-center-nested-group-box")
            group_title = current_path[-1].replace("_", " ").capitalize()
            group_desc = self._helpers._get_hint_for_path(
                self.parent.default_config, *current_path
            )
            preferences_group = Adw.PreferencesGroup(
                title=group_title, description=group_desc
            )
            preferences_group.add_css_class("control-center-config-group")
            for key, value in subdict.items():
                new_path = current_path + [key]
                if key.endswith(("_hint", "_section_hint", "_items_hint")):
                    continue
                if isinstance(value, dict):
                    expander = Gtk.Expander.new(
                        f"<b>{key.replace('_', ' ').capitalize()}</b>"
                    )
                    expander.set_use_markup(True)
                    expander.add_css_class("control-center-config-expander")
                    widget_dict[key] = {}
                    nested_box = self.create_nested_widgets(
                        widget_dict[key], value, new_path
                    )
                    expander.set_child(nested_box)
                    preferences_group.add(expander)
                elif isinstance(value, list) and all(
                    isinstance(item, dict) for item in value
                ):
                    expander = Gtk.Expander.new(
                        f"<b>{key.replace('_', ' ').capitalize()}</b>"
                    )
                    expander.set_use_markup(True)
                    expander.add_css_class("control-center-config-expander")
                    widget_dict[key] = []
                    list_content_box = self.create_list_widgets(
                        widget_dict[key], value, new_path
                    )
                    expander.set_child(list_content_box)
                    preferences_group.add(expander)
                else:
                    if isinstance(value, int) and value in (0, 1):
                        try:
                            default_val_container = self.parent.default_config
                            for k in new_path:
                                default_val_container = default_val_container[k]
                            if isinstance(default_val_container, bool):
                                value = bool(value)
                        except (KeyError, TypeError):
                            pass
                    widget = self.create_widget_for_value(key, value)
                    if not widget:
                        continue
                    hint = self._helpers._get_hint_for_path(
                        self.parent.default_config, *new_path
                    )
                    if not isinstance(widget, Gtk.Label):
                        widget.set_tooltip_text(hint)
                    action_row = Adw.ActionRow(
                        title=key.replace("_", " ").capitalize(),
                        subtitle=hint,
                    )
                    action_row.add_css_class("control-center-setting-row")
                    if isinstance(widget, (Gtk.Switch, Gtk.Entry, Gtk.SpinButton)):
                        action_row.add_suffix(widget)
                        action_row.set_activatable_widget(widget)
                    else:
                        action_row.set_child(widget)
                    preferences_group.add(action_row)
                    widget_dict[key] = widget
            box.append(preferences_group)
            return box

        def create_list_widgets(
            self,
            widget_list: List[Dict[str, Any]],
            data_list: List[Dict[str, Any]],
            current_path: List[str],
        ) -> Gtk.Box:
            list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            list_box.add_css_class("control-center-list-editor")
            group_title = current_path[-1].replace("_", " ").capitalize()
            group_desc = self._helpers._get_hint_for_path(
                self.parent.default_config, *current_path
            )
            preferences_group = Adw.PreferencesGroup(
                title=group_title, description=group_desc
            )
            preferences_group.add_css_class("control-center-config-group")
            for i, item_dict in enumerate(data_list):
                item_key = list(item_dict.keys())[0] if item_dict else f"Item_{i + 1}"
                item_name = item_dict.get(
                    "name", item_key.replace("_", " ").capitalize()
                )
                item_name_path = current_path + ["name"]
                item_cmd_path = current_path + ["cmd"]
                name_hint = self._helpers._get_hint_for_path(
                    self.parent.default_config, *item_name_path
                )
                cmd_hint = self._helpers._get_hint_for_path(
                    self.parent.default_config, *item_cmd_path
                )
                name_row = Adw.ActionRow(
                    title=f"{item_name} - Name",
                    subtitle=name_hint,
                )
                name_row.add_css_class("control-center-setting-row")
                name_row.add_css_class("control-center-list-item-row")
                cmd_row = Adw.ActionRow(
                    title=f"{item_name} - Command",
                    subtitle=cmd_hint,
                )
                cmd_row.add_css_class("control-center-setting-row")
                cmd_row.add_css_class("control-center-list-item-row")
                cmd_entry = Gtk.Entry()
                cmd_entry.set_text(item_dict.get("cmd", ""))
                cmd_entry.set_tooltip_text(cmd_hint)
                cmd_entry.add_css_class("control-center-text-input")
                name_entry = Gtk.Entry()
                name_entry.set_text(item_dict.get("name", ""))
                name_entry.set_tooltip_text(name_hint)
                name_entry.add_css_class("control-center-text-input")
                name_row.add_suffix(name_entry)
                name_row.set_activatable_widget(name_entry)
                cmd_row.add_suffix(cmd_entry)
                cmd_row.set_activatable_widget(cmd_entry)
                preferences_group.add(name_row)
                preferences_group.add(cmd_row)
                widget_list.append({"name_entry": name_entry, "cmd_entry": cmd_entry})
            list_box.append(preferences_group)
            return list_box

        def create_widget_for_value(self, key: str, value: Any) -> Gtk.Widget:
            container_options = [
                "top-panel",
                "top-panel-left",
                "top-panel-box-widgets-left",
                "top-panel-center",
                "top-panel-right",
                "top-panel-systray",
                "top-panel-after-systray",
                "bottom-panel",
                "bottom-panel-left",
                "bottom-panel-box-widgets-left",
                "bottom-panel-center",
                "bottom-panel-right",
                "bottom-panel-box-systray",
                "bottom-panel-box-for-buttons",
                "left-panel",
                "left-panel-top",
                "left-panel-center",
                "left-panel-bottom",
                "right-panel",
                "right-panel-top",
                "right-panel-center",
                "right-panel-bottom",
                "background",
            ]

            if key.lower() in ["container", "position", "target_container"]:
                combo = self.gtk.ComboBoxText()
                for option in container_options:
                    combo.append_text(option)
                if value in container_options:
                    combo.set_active(container_options.index(value))
                else:
                    combo.set_active(0)
                combo.set_hexpand(True)
                combo.set_valign(self.gtk.Align.CENTER)
                return combo

            if isinstance(value, str):
                entry = self.gtk.Entry()
                entry.add_css_class("control-center-text-input")
                entry.set_text(value)
                entry.set_width_chars(5)
                entry.set_max_width_chars(50)
                entry.set_valign(self.gtk.Align.CENTER)
                return entry

            elif isinstance(value, bool):
                switch = self.gtk.Switch()
                switch.add_css_class("control-center-toggle-switch")
                switch.set_active(value)
                switch.set_halign(self.gtk.Align.END)
                switch.set_valign(self.gtk.Align.CENTER)
                return switch

            elif isinstance(value, (int, float)):
                entry = self.gtk.SpinButton()
                entry.add_css_class("control-center-numeric-input")
                adjustment = self.gtk.Adjustment.new(
                    value=float(value),
                    lower=-10000.0,
                    upper=10000.0,
                    step_increment=1.0 if isinstance(value, int) else 0.1,
                    page_increment=10.0,
                    page_size=0.0,
                )
                entry.set_adjustment(adjustment)
                entry.set_width_chars(5)
                entry.set_max_width_chars(10)
                entry.set_valign(self.gtk.Align.CENTER)
                if isinstance(value, float):
                    entry.set_digits(max(1, len(str(value).split(".")[-1])))
                return entry

            elif isinstance(value, list):
                entry = self.gtk.Entry()
                entry.add_css_class("control-center-text-input")
                entry.set_text(", ".join(map(str, value)))
                entry.set_sensitive(True)
                entry.set_width_chars(10)
                entry.set_max_width_chars(100)
                entry.set_valign(self.gtk.Align.CENTER)
                if value:
                    first_element_type = type(value[0])
                    if first_element_type is int:
                        entry.original_type = "int"  # pyright: ignore
                    elif first_element_type is float:
                        entry.original_type = "float"  # pyright: ignore
                    else:
                        entry.original_type = "str"  # pyright: ignore
                else:
                    entry.original_type = "str"  # pyright: ignore
                return entry

            else:
                value_label = self.gtk.Label(label=str(value), xalign=0)
                value_label.add_css_class("control-center-value-display")
                value_label.set_valign(self.gtk.Align.CENTER)
                return value_label

        def create_category_widget(self, category_name: str) -> Gtk.Widget:
            """Creates a centered, clickable icon-and-label widget."""
            display_name = category_name.replace("_", " ").capitalize()
            icon_name = self.p.get_icon_for_category(category_name)

            vbox = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL, spacing=5)
            vbox.set_hexpand(True)
            vbox.set_vexpand(True)
            vbox.set_halign(self.gtk.Align.CENTER)
            vbox.set_valign(self.gtk.Align.CENTER)
            vbox.add_css_class("control-center-vbox-item")

            icon = self.gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(64)
            icon.add_css_class("control-center-category-icon")

            label = self.gtk.Label(label=display_name)
            label.set_halign(self.gtk.Align.CENTER)

            vbox.append(icon)
            vbox.append(label)

            container = self.gtk.Box()
            container.set_size_request(150, 120)
            container.set_halign(self.gtk.Align.CENTER)
            container.add_css_class("control-center-category-widget")
            container.append(vbox)

            gesture = self.gtk.GestureClick.new()
            gesture.connect(
                "released", self.p.on_category_widget_clicked, category_name
            )
            container.add_controller(gesture)

            return container

    return ControlCenterUI
