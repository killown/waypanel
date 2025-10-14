import os
from gi.repository import Gtk, Adw  # pyright: ignore
from typing import Any, List, Dict, Union


class ControlCenterHelpers:
    """
    Utility class for the ControlCenter plugin, responsible for translating
    configuration data structures into GTK widgets and retrieving metadata hints.
    """

    def __init__(self, center: Any) -> None:
        """
        Initializes the helper with a reference to the parent ControlCenter plugin.
        Args:
            center: A reference to the parent ControlCenter instance.
        """
        self.parent = center

    def _get_hint_for_path(self, current_dict: Dict[str, Any], *keys: str) -> str:
        """
        Retrieves the hint/description for a given configuration path from the default configuration.
        Args:
            current_dict: The configuration dictionary to traverse (usually self.default_config).
            *keys: The full path segments, resolved to the full config key.
                   (e.g., 'org.waypanel.plugin.bluetooth', 'hide_in_systray' OR
                   'hardware', 'soundcard', 'blacklist').
        Returns:
            The human-readable hint string, or a generic message if none is found.
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
        """
        Recursively creates nested widgets (Expander, ActionRow) for a sub-dictionary.
        Args:
            widget_dict: The dictionary to store the created widgets for saving.
            subdict: The segment of the configuration data to process.
            current_path: The full configuration path leading to this sub-dictionary.
        Returns:
            A Gtk.Box containing the preferences group for the nested settings.
        """
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
                    print(value)
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
        """
        Creates widgets for a list of dictionaries (e.g., a list of commands).
        Args:
            widget_list: The list to store the created widgets for saving.
            data_list: The list of data dictionaries to process.
            current_path: The full configuration path leading to this list.
        Returns:
            A Gtk.Box containing the preferences group for the list editor.
        """
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
        """
        Generates the appropriate Gtk widget based on the data type of the value.
        Args:
            value: The configuration value (str, int, float, bool, list).
        Returns:
            The corresponding Gtk.Widget instance, or None if the type is unhandled.
        """
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

    def display_notify(self, title: str, icon_name: str):
        """Displays an in-app Adw.Toast using the internal ToastOverlay."""
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
        MAIN_CONFIG_KEY = "org.waypanel.panel"
        NESTED_CONFIG_KEY = "theme"
        DEFAULT_KEY = "default"
        if self.parent.config:
            print(self.parent.config)
            if MAIN_CONFIG_KEY not in self.parent.config:
                self.parent.config[MAIN_CONFIG_KEY] = {}
            if NESTED_CONFIG_KEY not in self.parent.config[MAIN_CONFIG_KEY]:
                self.parent.config[MAIN_CONFIG_KEY][NESTED_CONFIG_KEY] = {}
            self.parent.config[MAIN_CONFIG_KEY][NESTED_CONFIG_KEY][DEFAULT_KEY] = (
                selected_theme
            )
        else:
            self.parent.logger.warning(
                "Cannot find the config for the theme selection."
            )
        try:
            self.parent.config_handler.save_config()
            if hasattr(self.parent._panel_instance, "apply_theme"):
                self.parent._panel_instance.apply_theme(selected_theme)
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
        """
        Creates the dedicated settings page for theme selection with all three options.
        """
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
