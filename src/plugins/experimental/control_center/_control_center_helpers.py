import os
from gi.repository import Gtk, Adw, Gdk  # pyright: ignore
from typing import Any, List, Dict, Union


class ControlCenterHelpers:
    """
    Utility class for the ControlCenter plugin, responsible for translating
    configuration data structures into GTK widgets and retrieving metadata hints.
    """

    def __init__(self, center: Any) -> None:
        """
        Initializes the helper with a reference to the parent ControlCenter plugin.
        """
        self.parent = center
        self.parent.current_wp_css_provider = Gtk.CssProvider.new()

    def _get_hint_for_path(self, current_dict: Dict[str, Any], *keys: str) -> str:
        """
        Retrieves the hint/description for a given configuration path from the default configuration.
        """
        target_dict = current_dict
        for i, key in enumerate(keys[:-1]):
            if not isinstance(target_dict, dict) or key not in target_dict:
                key_name = key.replace("_", " ").capitalize()
                context = ".".join(keys[:i]) if i > 0 else "Root"
                self.parent.logger.debug(
                    f"Hint missing for intermediate key: '{key_name}' (Context: {context})"
                )
                return ""
            target_dict = target_dict[key]
        if not isinstance(target_dict, dict):
            self.parent.logger.debug(
                "Internal Error: Invalid path structure in default config."
            )
            return ""
        final_key = keys[-1]
        value_hint = target_dict.get(f"{final_key}_hint")
        if value_hint:
            return (
                "\n".join(value_hint)
                if isinstance(value_hint, (tuple, list))
                else str(value_hint)
            )
        target_section = target_dict.get(final_key)
        if isinstance(target_section, dict):
            section_hint = target_section.get("_section_hint")
            if section_hint:
                return (
                    "\n".join(section_hint)
                    if isinstance(section_hint, (tuple, list))
                    else str(section_hint)
                )
            if any(isinstance(v, list) for v in target_section.values()):
                list_hint = target_section.get("list_hint") or target_section.get(
                    "_items_hint"
                )
                if list_hint:
                    return (
                        "\n".join(list_hint)
                        if isinstance(list_hint, (tuple, list))
                        else str(list_hint)
                    )
            key_name = final_key.replace("_", " ").capitalize()
            return f"A configuration section for '{key_name}'."
        key_name = final_key.replace("_", " ").capitalize()
        context = ".".join(keys[:-1]) if len(keys) > 1 else "Root"
        self.parent.logger.debug(
            f"Hint missing for key: '{key_name}' (Context: {context})"
        )
        return ""

    def create_nested_widgets(
        self,
        widget_dict: Dict[str, Any],
        subdict: Dict[str, Any],
        current_path: List[str],
    ) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class("control-center-nested-group-box")
        group_title = current_path[-1].replace("_", " ").capitalize()
        group_desc = self._get_hint_for_path(self.parent.default_config, *current_path)
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
                widget = self.create_widget_for_value(value)
                if not widget:
                    continue
                hint = self._get_hint_for_path(self.parent.default_config, *new_path)
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
        group_desc = self._get_hint_for_path(self.parent.default_config, *current_path)
        preferences_group = Adw.PreferencesGroup(
            title=group_title, description=group_desc
        )
        preferences_group.add_css_class("control-center-config-group")
        for i, item_dict in enumerate(data_list):
            item_key = list(item_dict.keys())[0] if item_dict else f"Item_{i + 1}"
            item_name = item_dict.get("name", item_key.replace("_", " ").capitalize())
            item_name_path = current_path + ["name"]
            item_cmd_path = current_path + ["cmd"]
            name_hint = self._get_hint_for_path(
                self.parent.default_config, *item_name_path
            )
            cmd_hint = self._get_hint_for_path(
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

    def create_widget_for_value(self, value: Any) -> Union[Gtk.Widget, None]:
        if isinstance(value, str):
            entry = Gtk.Entry()
            entry.add_css_class("control-center-text-input")
            entry.set_text(value)
            entry.set_width_chars(5)
            entry.set_max_width_chars(50)
            return entry
        elif isinstance(value, bool):
            switch = Gtk.Switch()
            switch.add_css_class("control-center-toggle-switch")
            switch.set_active(value)
            return switch
        elif isinstance(value, int) or isinstance(value, float):
            entry = Gtk.SpinButton()
            entry.add_css_class("control-center-numeric-input")
            adjustment = Gtk.Adjustment(
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
            if isinstance(value, float):
                entry.set_digits(max(1, len(str(value).split(".")[-1])))
            return entry
        elif isinstance(value, list):
            entry = Gtk.Entry()
            entry.add_css_class("control-center-text-input")
            entry.set_text(", ".join(map(str, value)))
            entry.set_sensitive(True)
            entry.set_width_chars(10)
            entry.set_max_width_chars(100)
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
            value_label = Gtk.Label(label=str(value), xalign=0)
            value_label.add_css_class("control-center-value-display")
            return value_label

    def _list_fs_themes(self, dirs: list[str]) -> list[str]:
        themes = set()
        is_flatpak = os.path.exists("/.flatpak-info")

        resolved_dirs = []
        for d in dirs:
            expanded = os.path.expanduser(d)
            resolved_dirs.append(expanded)

            # Only system paths need the /run/host prefix in Flatpak
            # User paths (~/.local/share/...) are handled by the sandbox's home mapping
            if is_flatpak and expanded.startswith("/usr"):
                host_mirror = os.path.join("/run/host", expanded.lstrip("/"))
                resolved_dirs.append(host_mirror)

        for full_dir in resolved_dirs:
            if os.path.isdir(full_dir):
                try:
                    for item in os.listdir(full_dir):
                        full_path = os.path.join(full_dir, item)
                        if os.path.isdir(full_path) and not item.startswith("."):
                            # Check for valid GTK or Icon theme structure
                            if any(
                                [
                                    os.path.exists(
                                        os.path.join(full_path, "index.theme")
                                    ),
                                    os.path.exists(os.path.join(full_path, "gtk-4.0")),
                                    os.path.exists(os.path.join(full_path, "gtk-3.0")),
                                ]
                            ):
                                themes.add(item)
                except (PermissionError, FileNotFoundError):
                    continue
        return sorted(list(themes))

    def _get_current_gsettings_theme(self, schema: str, key: str) -> str:
        """Retrieves gsettings from the host if in Flatpak, otherwise locally."""
        is_flatpak = os.path.exists("/.flatpak-info")
        cmd_prefix = "flatpak-spawn --host " if is_flatpak else ""
        try:
            # Use subprocess for cleaner output handling than os.popen
            cmd = f"{cmd_prefix}gsettings get {schema} {key}"
            result = os.popen(f"{cmd} 2>/dev/null").read().strip()
            if result and result.startswith("'") and result.endswith("'"):
                return result[1:-1]
            return result
        except Exception:
            return ""

    def display_notify(self, title: str, icon_name: str):
        if not self.parent.toast_overlay:
            print("ERROR: Cannot show toast. Adw.ToastOverlay not initialized.")
            return
        toast = Adw.Toast.new(title)
        if icon_name:
            pass
        self.parent.toast_overlay.add_toast(toast)

    def _on_gsettings_theme_selected(
        self, combobox: Gtk.ComboBoxText, schema: str, key: str
    ):
        selected_theme = combobox.get_active_text()
        if not selected_theme or selected_theme == "(No themes found)":
            return

        is_flatpak = os.path.exists("/.flatpak-info")
        cmd_prefix = "flatpak-spawn --host " if is_flatpak else ""

        try:
            command = f"{cmd_prefix}gsettings set {schema} {key} '{selected_theme}'"
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
        theme_names = self._list_fs_themes(theme_dirs)
        current_theme = self._get_current_gsettings_theme(schema, key)
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
        combobox.connect("changed", self._on_gsettings_theme_selected, schema, key)
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

    def _get_available_themes(self) -> list[str]:
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

    def _get_waypanel_css_path(self, theme_name: str) -> str:
        """Determines the full path to the Waypanel custom CSS file."""
        return os.path.expanduser(
            f"~/.local/share/waypanel/resources/themes/css/{theme_name}.css"
        )

    def _on_theme_selected(self, combobox: Gtk.ComboBoxText):
        """
        Handles the combobox selection, applies the theme *live* by reloading
        the Waypanel custom CSS via Gtk.CssProvider, and saves the preference.
        """
        selected_theme = combobox.get_active_text()
        if not selected_theme:
            return
        MAIN_CONFIG_KEY = "org.waypanel.panel"
        NESTED_CONFIG_KEY = "theme"
        DEFAULT_KEY = "default"
        css_path = self._get_waypanel_css_path(selected_theme)
        display = Gdk.Display.get_default()
        try:
            provider = self.parent.current_wp_css_provider
            provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            self.parent.logger.info(
                f"Waypanel CSS applied live: {selected_theme} from {css_path}"
            )
        except Exception as e:
            self.parent.logger.error(
                f"Failed to load/apply Waypanel CSS theme '{selected_theme}': {e}",
                exc_info=True,
            )
            self.display_notify(
                f"Error applying Waypanel theme: {e}", "dialog-error-symbolic"
            )
        try:
            config_dict = self.parent.config.setdefault(MAIN_CONFIG_KEY, {})
            config_dict.setdefault(NESTED_CONFIG_KEY, {})[DEFAULT_KEY] = selected_theme
            self.parent.config_handler.save_config()
            if hasattr(self.parent._panel_instance, "apply_theme"):
                self.parent._panel_instance.apply_theme(selected_theme)
        except Exception as e:
            self.display_notify(
                f"Error saving theme setting: {e}", "dialog-error-symbolic"
            )

    def _create_theme_selector_widget(self) -> Adw.ActionRow:
        theme_names = self._get_available_themes()
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
        combobox.connect("changed", self._on_theme_selected)
        action_row = Adw.ActionRow(
            title="Waypanel CSS Theme",
            subtitle="Select the theme for Waypanel's internal components.",
        )
        action_row.add_suffix(combobox)
        action_row.set_activatable_widget(combobox)
        action_row.add_css_class("control-center-setting-row")
        return action_row

    def _create_theme_page(self, ui_key: str) -> Gtk.ScrolledWindow:
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
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

    def _generate_plugin_map(self, config):
        plugin_map = {}
        for full_id in config.keys():
            if full_id.startswith("org.waypanel.plugin."):
                short_name = full_id.split(".")[-1]
                plugin_map[short_name] = full_id
            else:
                plugin_map[full_id] = full_id
        return plugin_map

    def save_category(self, category_name):
        full_config_key = category_name
        plugin_map = self._generate_plugin_map(self.parent.default_config)
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

                    return [cast_element(x) for x in text.split(",") if x.strip() != ""]
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
                                    config_dict[key][i]["cmd"] = get_value_from_widget(
                                        cmd_entry
                                    )
                                if name_entry:
                                    config_dict[key][i]["name"] = get_value_from_widget(
                                        name_entry
                                    )
                else:
                    new_value = get_value_from_widget(value)
                    if new_value is not None:
                        config_dict[key] = new_value

        if category_name in self.parent.widget_map:
            if self.parent.config:
                if full_config_key in self.parent.config:
                    update_config_from_widgets(
                        self.parent.config[full_config_key],
                        self.parent.widget_map[category_name],
                    )
                    if "_dynamic_fields" in self.parent.widget_map[category_name]:
                        dynamic_fields = self.parent.widget_map[category_name][
                            "_dynamic_fields"
                        ]
                        for path_widget, key_widget, value_widget in dynamic_fields:
                            key = key_widget.get_text().strip()
                            path_str = path_widget.get_text().strip()
                            if not key:
                                continue
                            value = get_value_from_widget(value_widget)
                            current_level = self.parent.config[full_config_key]
                            if path_str:
                                path_parts = path_str.split(".")
                                for part in path_parts:
                                    current_level = current_level.setdefault(part, {})
                            current_level[key] = value
                else:
                    return
        try:
            self.parent.config_handler.save_config()
            self.display_notify(
                f"The {category_name.replace('_', ' ').capitalize()} settings have been saved successfully!",
                "configure-symbolic",
            )
        except Exception as e:
            self.display_notify(
                f"Error saving {category_name.replace('_', ' ').capitalize()} settings: {e}",
                "dialog-error",
            )
