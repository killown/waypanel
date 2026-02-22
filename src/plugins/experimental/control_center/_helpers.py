import os
from gi.repository import Gtk, Adw, Gdk  # pyright: ignore
from typing import Any, Dict


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
            cmd = f"{cmd_prefix}gsettings get {schema} {key}"
            result = os.popen(f"{cmd} 2>/dev/null").read().strip()

            theme = result
            if result and result.startswith("'") and result.endswith("'"):
                theme = result[1:-1]

            # Sync the environment variable so CommandRunner inherits it
            if theme:
                os.environ["GTK_THEME"] = theme

            return theme
        except Exception:
            return ""

    def on_delete_config_clicked(self, button, category_name):
        """Prompts the user to confirm wiping the plugin configuration."""
        from gi.repository import Adw

        dialog = Adw.MessageDialog(
            transient_for=getattr(self.parent, "main_window", None),
            heading=f"Wipe {category_name.replace('_', ' ').capitalize()} Config?",
            body=(
                f"This will permanently delete the configuration for '{category_name}' "
                "from config.toml. This action cannot be undone."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Wipe Config")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def handle_response(dialog, response):
            if response == "delete":
                self._execute_config_wipe(category_name)

        dialog.connect("response", handle_response)
        dialog.present()

    def _execute_config_wipe(self, category_name: str) -> None:
        """Removes a plugin configuration section and resets to main grid."""
        full_config_key = self.parent.ui_key_to_plugin_id_map.get(category_name)

        if not full_config_key:
            return

        try:
            # Authoritative removal via the ConfigHandler
            self.parent.config_handler.remove_root_setting(full_config_key)
            self.parent.config = self.parent.config_handler.config_data

            self.display_notify(
                f"Configuration for {category_name.replace('_', ' ').capitalize()} wiped.",
                "user-trash-full-symbolic",
            )

            # Rebuild UI state
            self.parent.logic.setup_categories_grid()

            # Navigate back to search grid
            # Logic: Using 'category_grid' to match the main_stack child name
            self.parent.main_stack.set_visible_child_name("category_grid")

            self.parent.config_handler.save_config()

        except Exception as e:
            self.logger.error(f"Failed to execute config wipe for {category_name}: {e}")
            self.display_notify(f"Error wiping configuration: {e}", "dialog-error")

    def display_notify(self, title: str, icon_name: str):
        if not self.parent.toast_overlay:
            print("ERROR: Cannot show toast. Adw.ToastOverlay not initialized.")
            return
        toast = Adw.Toast.new(title)
        if icon_name:
            pass
        self.parent.toast_overlay.add_toast(toast)

    def _on_add_field_clicked(self, button, group, category_name):
        """Adds a new row for a dynamic configuration field."""

        # Ensure the dynamic field tracking list exists for this category
        if "_dynamic_fields" not in self.parent.widget_map[category_name]:
            self.parent.widget_map[category_name]["_dynamic_fields"] = []

        # Create the UI components for the new field
        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        row_box.set_margin_top(10)

        path_entry = Gtk.Entry(placeholder_text="Path (e.g. settings.nested)")
        path_entry.add_css_class("control-center-text-input")

        key_entry = Gtk.Entry(placeholder_text="Key Name")
        key_entry.add_css_class("control-center-text-input")

        value_entry = Gtk.Entry(placeholder_text="Value")
        value_entry.add_css_class("control-center-text-input")

        # Layout for entries
        entries_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        entries_box.append(path_entry)
        entries_box.append(key_entry)
        entries_box.append(value_entry)

        # Remove button for this specific row
        remove_btn = Gtk.Button(icon_name="list-remove-symbolic")
        remove_btn.add_css_class("destructive-action")

        field_tuple = (path_entry, key_entry, value_entry)

        def on_remove_clicked(btn):
            group.remove(row_box)
            self.parent.widget_map[category_name]["_dynamic_fields"].remove(field_tuple)

        remove_btn.connect("clicked", on_remove_clicked)
        entries_box.append(remove_btn)

        row_box.append(entries_box)
        group.add(row_box)

        self.parent.widget_map[category_name]["_dynamic_fields"].append(field_tuple)

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
            if self.parent.current_wp_css_provider is None:
                self.parent.current_wp_css_provider = Gtk.CssProvider()
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
            if "css_generator" in self.parent.plugins:
                self.parent.plugins["css_generator"].remove_themes()
        except Exception as e:
            self.display_notify(
                f"Error saving theme setting: {e}", "dialog-error-symbolic"
            )

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
            elif isinstance(widget, Gtk.ComboBoxText):
                return widget.get_active_text()
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
