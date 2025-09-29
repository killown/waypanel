import os
import gi
from typing import Dict, Any, List
from gi.repository import Gtk, Adw, Gdk
import sys

try:
    from src.shared.notify_send import Notifier  # pyright: ignore
except ImportError:

    class Notifier:
        def notify_send(self, title, message, icon):
            print(f"[Notifier] {title}: {message}")


sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
)
import config_handler  # pyright: ignore

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")


class ControlCenter(Adw.Application):
    def __init__(self, panel_instance):
        super().__init__(application_id="org.waypanel.ControlCenter")
        self.config_handler = config_handler.ConfigHandler(panel_instance)
        self.default_config: Dict = self.config_handler.default_config
        self.config = {}
        self.widget_map = {}
        self.notifier = Notifier()
        self.toast_overlay: Adw.ToastOverlay = None

    def _get_hint_for_path(self, *keys) -> str:
        current_dict = self.default_config
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
            if (
                isinstance(current_dict, list)
                and parent_dict.get(f"{last_key}_hint") is None
            ):
                list_hint = parent_dict.get("_items_hint")
                if isinstance(list_hint, str):
                    return list_hint
        key_name = keys[-1].replace("_", " ").capitalize() if keys else "Setting"
        return f"A configuration option for '{key_name}'."

    def create_content_page(self, category_name, data: Dict[str, Any]):
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.add_css_class("control-center-content-area")
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        group_desc = self._get_hint_for_path(category_name)
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
                expander_content = self.create_nested_widgets(
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
                list_content_box = self.create_list_widgets(
                    self.widget_map[category_name][key], value, current_path
                )
                expander.set_child(list_content_box)
                main_box.append(expander)
            else:
                widget = self.create_widget_for_value(value)
                if not widget:
                    continue
                hint = self._get_hint_for_path(*current_path)
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

    def create_list_widgets(self, widget_list, data_list, current_path: List[str]):
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        list_box.add_css_class("control-center-list-editor")
        group_title = current_path[-1].replace("_", " ").capitalize()
        group_desc = self._get_hint_for_path(*current_path)
        preferences_group = Adw.PreferencesGroup(
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
            name_row = Adw.ActionRow(
                title=f"{item_name} - Name",
            )
            name_row.add_css_class("control-center-setting-row")
            name_row.add_css_class("control-center-list-item-row")
            cmd_row = Adw.ActionRow(
                title=f"{item_name} - Command",
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

    def create_nested_widgets(self, widget_dict, subdict, current_path: List[str]):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class("control-center-nested-group-box")
        group_title = current_path[-1].replace("_", " ").capitalize()
        group_desc = self._get_hint_for_path(*current_path)
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
                widget = self.create_widget_for_value(value)
                if not widget:
                    continue
                hint = self._get_hint_for_path(*new_path)
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
                widget_dict[key] = widget
        box.append(preferences_group)
        return box

    def create_widget_for_value(self, value: Any):
        if isinstance(value, str):
            entry = Gtk.Entry()
            entry.add_css_class("control-center-text-input")
            entry.set_text(value)
            entry.set_width_chars(30)
            entry.set_max_width_chars(50)
            return entry
        elif isinstance(value, int) or isinstance(value, float):
            entry = Gtk.SpinButton()
            entry.add_css_class("control-center-numeric-input")
            adjustment = Gtk.Adjustment(
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
            switch = Gtk.Switch()
            switch.add_css_class("control-center-toggle-switch")
            switch.set_active(value)
            return switch
        elif isinstance(value, list):
            entry = Gtk.Entry()
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
            value_label = Gtk.Label(label=str(value), xalign=0)
            value_label.add_css_class("control-center-value-display")
            return value_label

    def display_notify(self, title: str, icon_name: str):
        """Displays an in-app Adw.Toast using the internal ToastOverlay."""
        if not self.toast_overlay:
            print("ERROR: Cannot show toast. Adw.ToastOverlay not initialized.")
            return
        toast = Adw.Toast.new(title)
        if icon_name:
            pass
        self.toast_overlay.add_toast(toast)

    def do_activate(self):
        self.win = self.props.active_window
        if not self.win:
            self.win = Adw.ApplicationWindow(application=self)
            self.win.set_title("Waypanel Control Center")
            self.win.set_default_size(800, 600)
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.win.set_content(vbox)
            header_bar = Adw.HeaderBar()
            header_bar.add_css_class("control-center-header")
            vbox.append(header_bar)
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
            self.toast_overlay = Adw.ToastOverlay.new()
            vbox.append(self.toast_overlay)
            main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.toast_overlay.set_child(main_box)
            left_panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            left_panel_box.set_size_request(300, -1)
            left_panel_box.set_hexpand(False)
            left_listbox = Gtk.ListBox()
            left_listbox.add_css_class("control-center-category-list")
            left_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_child(left_listbox)
            scrolled_window.set_vexpand(True)
            scrolled_window.set_hexpand(False)
            scrolled_window.set_size_request(300, -1)
            left_panel_box.append(scrolled_window)
            main_box.append(left_panel_box)
            right_wrapper = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            right_wrapper.set_hexpand(True)
            right_wrapper.set_vexpand(True)
            main_box.append(right_wrapper)
            self.content_stack = Gtk.Stack()
            self.content_stack.set_size_request(500, -1)
            self.content_stack.set_hexpand(False)
            self.content_stack.set_vexpand(True)
            right_wrapper.append(self.content_stack)
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            right_wrapper.append(spacer)
            self.load_config()
            self.setup_categories(left_listbox, self.content_stack)
            left_listbox.connect("row-activated", self.on_category_activated)
            if left_listbox.get_row_at_index(0):
                left_listbox.select_row(left_listbox.get_row_at_index(0))
        self.win.present()

    def get_icon_for_category(self, category_name: str) -> str:
        norm_name = category_name.replace("_", " ").split()[0].lower()
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())  # pyright: ignore
        icon_patterns = [
            norm_name,
            f"{norm_name}-symbolic",
            f"preferences-{norm_name}-symbolic",
            f"utilities-{norm_name}-symbolic",
        ]
        for icon_name in icon_patterns:
            if icon_theme.has_icon(icon_name):
                return icon_name
        norm_name_patterns = [
            norm_name,
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

    def on_category_activated(self, listbox, row):
        category_name = row.get_property("name")
        self.content_stack.set_visible_child_name(category_name)
        self.save_button_stack.set_visible_child_name("save_button")

    def on_save_clicked(self, button):
        current_category = self.content_stack.get_visible_child_name()
        if current_category:
            self.save_category(current_category)

    def save_category(self, category_name):
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

        if category_name in self.widget_map:
            if category_name in self.config:
                update_config_from_widgets(
                    self.config[category_name], self.widget_map[category_name]
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

    def setup_categories(self, listbox, stack):
        self.widget_map = {}
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
            stack.add_named(label_box, "no_config")
            stack.set_visible_child_name("no_config")
            return
        sorted_category_names = sorted(self.config.keys())
        for category_name in sorted_category_names:
            category_data = self.config[category_name]
            row = Gtk.ListBoxRow()
            row.add_css_class("control-center-category-item")
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_start(10)
            box.set_margin_end(10)
            icon_name = self.get_icon_for_category(category_name)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(48)
            box.append(icon)
            display_name = category_name.replace("_", " ").capitalize()
            label = Gtk.Label(
                label=f'<b><span size="12288">{display_name}</span></b>', xalign=0
            )
            label.set_use_markup(True)
            box.append(label)
            row.set_child(box)
            listbox.append(row)
            row.set_property("name", category_name)
            content_page = self.create_content_page(category_name, category_data)
            stack.add_named(content_page, category_name)
