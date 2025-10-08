from typing import Any, List


class ControlCenterHelpers:
    def __init__(self, center) -> None:
        self.center = center
        self.gtk = self.center.gtk
        self.adw = self.center.adw

    def _get_hint_for_path(self, *keys) -> str:
        resolved_keys = list(keys)
        if keys:
            first_key = keys[0]
            plugin_resolved = False
            if hasattr(self, "short_to_full_key"):
                for short_name, full_name in self.center.short_to_full_key.items():
                    if first_key.startswith(f"{short_name}_"):
                        plugin_section_key = first_key[len(short_name) + 1 :]
                        resolved_keys = [full_name, plugin_section_key] + list(keys[1:])
                        plugin_resolved = True
                        break
                    if first_key == short_name and not plugin_resolved:
                        resolved_keys[0] = self.center.short_to_full_key[first_key]
                        plugin_resolved = True
                        break
            if (
                not plugin_resolved
                and hasattr(self, "short_to_full_key")
                and first_key in self.center.short_to_full_key
            ):
                resolved_keys[0] = self.center.short_to_full_key[first_key]
                plugin_resolved = True
        keys = tuple(resolved_keys)
        current_dict = self.center.default_config
        parent_dict = None
        last_key = None
        for i, key in enumerate(keys):
            if not isinstance(current_dict, dict) or key not in current_dict:
                key_name = key.replace("_", " ").capitalize()
                context = ".".join(keys[:i]) if i > 0 else "Root"
                return f"Hint missing for key: '{key_name}' (Context: {context})"
            parent_dict = current_dict
            last_key = key
            current_dict = current_dict[key]
        if isinstance(current_dict, dict):
            section_hint = current_dict.get("_section_hint")
            if isinstance(section_hint, str):
                return section_hint
            key_name = keys[-1].replace("_", " ").capitalize() if keys else "Setting"
            return f"A configuration section for '{key_name}'."
        if parent_dict and last_key:
            value_hint = parent_dict.get(f"{last_key}_hint")
            if isinstance(value_hint, str):
                return value_hint
            if isinstance(current_dict, list):
                list_hint = parent_dict.get("list_hint") or parent_dict.get(
                    "_items_hint"
                )
                if isinstance(list_hint, str):
                    return list_hint
        key_name = keys[-1].replace("_", " ").capitalize() if keys else "Setting"
        return f"A configuration option for '{key_name}'."

    def create_nested_widgets(self, widget_dict, subdict, current_path: List[str]):
        box = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class("control-center-nested-group-box")
        group_title = current_path[-1].replace("_", " ").capitalize()
        group_desc = self._get_hint_for_path(*current_path)
        preferences_group = self.adw.PreferencesGroup(
            title=group_title, description=group_desc
        )
        preferences_group.add_css_class("control-center-config-group")
        for key, value in subdict.items():
            new_path = current_path + [key]
            if key.endswith(("_hint", "_section_hint", "_items_hint")):
                continue
            if isinstance(value, dict):
                expander = self.gtk.Expander.new(
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
                expander = self.gtk.Expander.new(
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
                widget = self.create_widget_for_value(value)
                if not widget:
                    continue
                hint = self._get_hint_for_path(*new_path)
                if not isinstance(widget, self.gtk.Label):
                    widget.set_tooltip_text(hint)
                action_row = self.adw.ActionRow(
                    title=key.replace("_", " ").capitalize(),
                )
                action_row.add_css_class("control-center-setting-row")
                if isinstance(
                    widget, (self.gtk.Switch, self.gtk.Entry, self.gtk.SpinButton)
                ):
                    action_row.add_suffix(widget)
                    action_row.set_activatable_widget(widget)
                else:
                    action_row.set_child(widget)
                preferences_group.add(action_row)
                widget_dict[key] = widget
        box.append(preferences_group)
        return box

    def create_list_widgets(self, widget_list, data_list, current_path: List[str]):
        list_box = self.gtk.Box(orientation=self.gtk.Orientation.VERTICAL, spacing=10)
        list_box.add_css_class("control-center-list-editor")
        group_title = current_path[-1].replace("_", " ").capitalize()
        group_desc = self._get_hint_for_path(*current_path)
        preferences_group = self.adw.PreferencesGroup(
            title=group_title, description=group_desc
        )
        preferences_group.add_css_class("control-center-config-group")
        for i, item_dict in enumerate(data_list):
            item_key = list(item_dict.keys())[0] if item_dict else f"Item_{i + 1}"
            item_name = item_dict.get("name", item_key.replace("_", " ").capitalize())
            item_name_path = current_path + ["name"]
            item_cmd_path = current_path + ["cmd"]
            name_hint = self._get_hint_for_path(*item_name_path)
            cmd_hint = self._get_hint_for_path(*item_cmd_path)
            name_row = self.adw.ActionRow(
                title=f"{item_name} - Name",
            )
            name_row.add_css_class("control-center-setting-row")
            name_row.add_css_class("control-center-list-item-row")
            cmd_row = self.adw.ActionRow(
                title=f"{item_name} - Command",
            )
            cmd_row.add_css_class("control-center-setting-row")
            cmd_row.add_css_class("control-center-list-item-row")
            cmd_entry = self.gtk.Entry()
            cmd_entry.set_text(item_dict.get("cmd", ""))
            cmd_entry.set_tooltip_text(cmd_hint)
            cmd_entry.add_css_class("control-center-text-input")
            name_entry = self.gtk.Entry()
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

    def create_widget_for_value(self, value: Any):
        if isinstance(value, str):
            entry = self.gtk.Entry()
            entry.add_css_class("control-center-text-input")
            entry.set_text(value)
            entry.set_width_chars(30)
            entry.set_max_width_chars(50)
            return entry
        elif isinstance(value, int) or isinstance(value, float):
            entry = self.gtk.SpinButton()
            entry.add_css_class("control-center-numeric-input")
            adjustment = self.gtk.Adjustment(
                value=float(value),
                lower=-10000.0,
                upper=10000.0,
                step_increment=1.0,
                page_increment=10.0,
                page_size=0.0,
            )
            entry.set_adjustment(adjustment)
            entry.set_width_chars(15)
            entry.set_max_width_chars(20)
            return entry
        elif isinstance(value, bool):
            switch = self.gtk.Switch()
            switch.add_css_class("control-center-toggle-switch")
            switch.set_active(value)
            return switch
        elif isinstance(value, list):
            entry = self.gtk.Entry()
            entry.add_css_class("control-center-text-input")
            entry.set_text(", ".join(map(str, value)))
            entry.set_sensitive(True)
            entry.set_width_chars(30)
            entry.set_max_width_chars(50)
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
            return value_label
