import os
import re
import toml
from gi.repository import Gtk, Pango, GLib, Gio, Gdk
from xml.etree import ElementTree as ET
from src.plugins.core._base import BasePlugin

# === CONFIG ===
METADATA_DIR = "/usr/share/wayfire/metadata"
WAYFIRE_TOML_PATH = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
ENABLE_PLUGIN = True
DEPS = ["event_manager"]  # Ensure IPC is ready


def get_plugin_placement(panel_instance):
    return "background"  # No UI of its own


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return PluginDetailsHandler(panel_instance)
    return None


class PluginDetailsHandler(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.windows = {}  # Track open windows per plugin

    def open_plugin_config_window(self, plugin_name):
        """Open config window NON-BLOCKING using GLib.idle_add."""
        if plugin_name in self.windows:
            win = self.windows[plugin_name]
            if win.get_visible():
                win.present()
                return
            else:
                del self.windows[plugin_name]

        # Schedule window creation in idle loop
        GLib.idle_add(self._create_window_async, plugin_name)

    def _create_window_async(self, plugin_name):
        """Create and populate window in non-blocking way."""
        try:
            # 1. Load metadata
            plugin_data = self.load_plugin_metadata(plugin_name)
            if not plugin_data:
                self.logger.error(f"Plugin not found or invalid: {plugin_name}")
                return False

            # 2. Build window shell
            window = self._build_window_skeleton(plugin_data)
            self.windows[plugin_name] = window

            # 3. Schedule content loading
            GLib.idle_add(self._populate_window_content, window, plugin_data)

            # 4. Show window
            window.present()

        except Exception as e:
            self.logger.error(f"Failed to create config window: {e}")
        return False  # Run once

    def _build_window_skeleton(self, plugin_data):
        """Build window structure without heavy content."""
        window = Gtk.Window(
            title=f"Configure: {plugin_data['short']}",
            default_width=500,
            default_height=600,
        )
        window.set_modal(False)  # ⚠️ NOT modal → prevents blocking
        window.set_destroy_with_parent(True)

        # Header
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label=plugin_data["short"]))
        window.set_titlebar(header)

        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_btn.connect("clicked", lambda _: window.destroy())
        header.pack_end(close_btn)

        # Scrolled container
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        window.set_child(scroll)

        # Content box (empty for now)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        scroll.set_child(content_box)

        # Store references
        setattr(window, "content_box", content_box)
        setattr(window, "widgets", {})  # For runtime updates

        return window

    def _populate_window_content(self, window, plugin_data):
        """Populate window content in chunks to avoid blocking."""
        try:
            content_box = window.content_box

            # Description
            if plugin_data["long"]:
                desc_label = Gtk.Label()
                desc_label.set_markup(f"<i>{plugin_data['long']}</i>")
                desc_label.set_wrap(True)
                desc_label.set_max_width_chars(60)
                desc_label.set_halign(Gtk.Align.START)
                content_box.append(desc_label)

            # Divider
            if plugin_data["options"]:
                sep = Gtk.Separator(margin_top=12, margin_bottom=12)
                content_box.append(sep)

            # Search bar
            search_entry = Gtk.SearchEntry()
            search_entry.set_placeholder_text("Search options...")
            search_entry.connect(
                "search-changed", self._on_search_changed, window, plugin_data
            )
            content_box.append(search_entry)

            # Options container
            options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            content_box.append(options_box)

            # Store for filtering
            setattr(window, "options_box", options_box)
            setattr(window, "all_rows", [])
            setattr(window, "plugin_data", plugin_data)

            # === NEW: Load TOML config ===
            toml_config = self._load_toml_config()
            prefix = f"{plugin_data['name']}/"

            # Start adding rows in idle chunks with merged values
            self._add_options_in_idle_with_toml(
                window, plugin_data, options_box, 0, toml_config, prefix
            )

        except Exception as e:
            self.logger.error(f"Failed to populate window: {e}")
        return False

    def _add_options_in_idle_with_toml(
        self, window, plugin_data, container, index, toml_config, prefix
    ):
        """Add options one by one, using value from TOML if exists."""
        if index >= len(plugin_data["options"]):
            return False  # Done

        opt = plugin_data["options"][index]
        full_key = prefix + opt["name"]

        # Get value from TOML, fallback to default
        current_value = toml_config.get(full_key, opt["default"])

        # Create row with current value
        row = self._create_option_row_with_toml(prefix, opt, current_value)
        if row:
            container.append(row)
            # Store for filtering
            window.all_rows.append((row, full_key, opt["short"], str(opt["default"])))

        # Schedule next
        if index < len(plugin_data["options"]) - 1:
            GLib.timeout_add(
                1,
                self._add_options_in_idle_with_toml,
                window,
                plugin_data,
                container,
                index + 1,
                toml_config,
                prefix,
            )
        return False

    def _save_value_to_toml(self, full_key, value):
        """Save updated value back to wayfire.toml"""
        toml_path = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
        try:
            with open(toml_path, "r") as f:
                data = toml.load(f)

            # Navigate and set key
            parts = full_key.split("/")
            d = data
            for p in parts[:-1]:
                if p not in d:
                    d[p] = {}
                d = d[p]
            d[parts[-1]] = value

            # Write back
            with open(toml_path, "w") as f:
                toml.dump(data, f)

        except Exception as e:
            self.logger.error(f"Failed to save to wayfire.toml: {e}")

    def _format_key_display(self, key_str):
        """Convert internal key string (e.g. '<super> KEY_T') into readable form."""
        parts = key_str.strip().split()
        modifiers = []
        key = None

        for part in parts:
            part = part.strip("<>")
            if part.startswith("KEY_"):
                key = part[4:].upper()
            elif part == "ctrl":
                modifiers.append("Ctrl")
            elif part == "shift":
                modifiers.append("Shift")
            elif part == "alt":
                modifiers.append("Alt")
            elif part == "super":
                modifiers.append("Super")

        if not key:
            return "[Unset]"

        return " + ".join(modifiers + [key])

    def _create_file_chooser_row(self, prefix, opt, current_value):
        """
        Create a row with a label, entry, and file chooser button.
        For options expecting a file path.
        """
        full_key = prefix + opt["name"]

        label = Gtk.Label(
            label=opt["short"],
            halign=Gtk.Align.START,
            tooltip_text=opt["long"],
            width_chars=20,
            ellipsize=Pango.EllipsizeMode.END,
        )

        # Entry (shows current path)
        entry = Gtk.Entry()
        entry.set_text(str(current_value))
        entry.set_sensitive(False)  # Read-only; use button to change
        entry.set_hexpand(True)

        # Button: 📂 Browse
        button = Gtk.Button.new_from_icon_name("document-open-symbolic")
        button.set_tooltip_text("Select a file")
        button.set_margin_start(6)

        # Row container
        row = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
        row.append(label)
        row.append(entry)
        row.append(button)

        # File chooser dialog
        def on_button_clicked(_btn):
            dialog = Gtk.FileChooserDialog(
                title=f"Select file for {opt['short']}",
                action=Gtk.FileChooserAction.OPEN,
            )
            dialog.add_buttons(
                "_Cancel", Gtk.ResponseType.CANCEL, "_Open", Gtk.ResponseType.ACCEPT
            )

            if current_value and os.path.exists(os.path.dirname(current_value)):
                dialog.set_current_folder(
                    Gio.File.new_for_path(os.path.dirname(current_value))
                )
            if current_value and os.path.exists(current_value):
                dialog.set_file(Gio.File.new_for_path(current_value))

            def on_response(dlg, response):
                if response == Gtk.ResponseType.ACCEPT:
                    selected_file = dlg.get_file().get_path()
                    entry.set_text(selected_file)
                    self.ipc.set_option_values({full_key: selected_file})
                    self._save_value_to_toml(full_key, selected_file)
                dlg.destroy()

            dialog.connect("response", on_response)
            dialog.present()

        button.connect("clicked", on_button_clicked)
        return row

    def _parse_wayfire_color(self, color_str):
        """
        Parse Wayfire color string (e.g. '0.5 0.5 1 0.5') into Gdk.RGBA.
        """
        try:
            parts = color_str.strip().split()
            if len(parts) < 3:
                raise ValueError("Not enough values")

            r = float(parts[0])
            g = float(parts[1])
            b = float(parts[2])
            a = float(parts[3]) if len(parts) > 3 else 1.0

            # Clamp to 0.0–1.0
            r = max(0.0, min(1.0, r))
            g = max(0.0, min(1.0, g))
            b = max(0.0, min(1.0, b))
            a = max(0.0, min(1.0, a))

            rgba = Gdk.RGBA()
            rgba.red = r
            rgba.green = g
            rgba.blue = b
            rgba.alpha = a
            return rgba

        except Exception as e:
            self.logger.warning(f"Invalid color format: {color_str} → {e}")
            # Return default (blue-ish)
            rgba = Gdk.RGBA()
            rgba.parse("rgba(0.5, 0.5, 1.0, 0.5)")
            return rgba

    def _create_option_row_with_toml(self, prefix, opt, current_value):
        """Create row using current_value (from TOML or default), with correct widget per type."""
        full_key = prefix + opt["name"]

        label = Gtk.Label(label=opt["short"])
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.CENTER)
        label.set_tooltip_text(opt["long"]) if opt["long"] else None
        label.set_width_chars(30)
        label.set_ellipsize(Pango.EllipsizeMode.END)

        widget = None

        # === BOOLEAN ===
        if opt["type"] == "bool":
            widget = Gtk.Switch(valign=Gtk.Align.CENTER)
            widget.set_active(self.to_bool(current_value))
            widget.connect("notify::active", self.on_bool_change, full_key)
            GLib.idle_add(self._load_bool_value, widget, full_key)

        # === INTEGER / DOUBLE ===
        elif opt["type"] in ("int", "double"):
            try:
                value = float(current_value)
            except (ValueError, TypeError):
                value = float(opt["default"])

            step = float(opt["precision"]) if opt["precision"] else 1.0
            if step <= 0:
                step = 1.0

            adj = Gtk.Adjustment(
                lower=float(opt["min"]) if opt["min"] is not None else 0.0,
                upper=float(opt["max"]) if opt["max"] is not None else 100.0,
                step_increment=step,
                page_increment=step * 10.0,
                value=value,
            )
            widget = Gtk.SpinButton()
            widget.set_adjustment(adj)
            widget.set_digits(3 if opt["type"] == "double" else 0)

            def on_spin_changed(spin_btn, option_key, option_type):
                val = spin_btn.get_value()
                if option_type == "int":
                    val = int(round(val))
                self.ipc.set_option_values({option_key: str(val)})
                self._save_value_to_toml(option_key, val)

            widget.connect("value-changed", on_spin_changed, full_key, opt["type"])
            GLib.idle_add(self._load_numeric_value, widget, full_key)

        elif opt["type"] == "color":
            rgba = self._parse_wayfire_color(current_value)

            # Create a color dialog
            dialog = Gtk.ColorDialog()
            dialog.set_with_alpha(True)  # Wayfire uses alpha

            # Create the button
            button = Gtk.ColorDialogButton(dialog=dialog)
            button.set_rgba(rgba)
            button.set_tooltip_text(f"Click to change: {opt['short']}")
            button.set_halign(Gtk.Align.START)
            button.set_valign(Gtk.Align.CENTER)

            def on_color_changed(btn, _pspec):
                rgba = btn.get_rgba()
                r, g, b, a = rgba.red, rgba.green, rgba.blue, rgba.alpha
                wayfire_color = f"{r:.3f} {g:.3f} {b:.3f} {a:.3f}"

                full_key = prefix + opt["name"]
                self.ipc.set_option_values({full_key: wayfire_color})
                self._save_value_to_toml(full_key, wayfire_color)

            button.connect("notify::rgba", on_color_changed)

            # Row layout
            row = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
            row.append(Gtk.Label(label=opt["short"], width_chars=20))
            row.append(button)
            return row

        elif opt["type"] in ("key", "activator", "button"):
            widget = Gtk.Entry()
            widget.set_text(str(current_value))
            widget.set_placeholder_text("<super> KEY_T")  # Show expected format
            widget.set_tooltip_text(
                "Enter keybind in format: <modifier> KEY_X\n"
                "Modifiers: <ctrl>, <shift>, <alt>, <super>\n"
                "Example: <ctrl> <alt> KEY_T"
            )
            widget.connect("changed", self.on_string_change, full_key)
            GLib.idle_add(self._load_string_value, widget, full_key)

        # === ENUM: string with <desc> choices ===
        elif opt["type"] == "string" and opt["choices"]:
            widget = Gtk.ComboBoxText()
            for val, lbl in opt["choices"]:
                widget.append(val, lbl)

            # Set active ID (must match one of the 'val' strings)
            widget.set_active_id(str(current_value))

            # Connect change handler
            widget.connect("changed", self.on_enum_change, full_key)

        # === STRING with HINT (file/directory) OR NAME-BASED GUESS ===
        elif opt["type"] == "string":
            PATH_KEYWORDS = {
                "file",
                "path",
                "image",
                "icon",
                "theme",
                "wallpaper",
                "background",
                "cursor",
                "font",
                "shader",
                "texture",
                "config",
                "script",
                "exec",
                "dir",
            }

            hint = opt.get("hint", "").strip().lower()
            key_name = opt["name"].lower()

            is_file = False
            is_directory = False

            if hint == "file":
                is_file = True
            elif hint == "directory":
                is_directory = True
            elif not hint:
                if any(k in key_name for k in PATH_KEYWORDS):
                    is_directory = any(
                        k in key_name for k in {"dir", "folder", "directory"}
                    )
                    is_file = not is_directory

            if is_file:
                return self._create_file_chooser_row(prefix, opt, current_value)
            elif is_directory:
                return self._create_file_chooser_row(
                    prefix,
                    opt,
                    current_value,
                )

            # Normal string
            widget = Gtk.Entry()
            widget.set_text(str(current_value))
            widget.connect("changed", self.on_string_change, full_key)
            GLib.idle_add(self._load_string_value, widget, full_key)

        # === ANIMATION ===
        elif opt["type"] == "animation":
            return self._create_animation_row(full_key, opt, current_value)

        # === DYNAMIC-LIST ===
        elif opt["type"] == "dynamic-list":
            widget = Gtk.Button(label="Edit List...")
            widget.connect("clicked", self.on_edit_list, full_key, current_value)
            row = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
            row.append(label)
            row.append(widget)
            return row

        # === UNSUPPORTED ===
        else:
            fallback = Gtk.Label(label=f"[{opt['type']}] Unsupported")
            row = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
            row.append(label)
            row.append(fallback)
            return row

        # Default row layout
        row = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
        row.append(label)
        row.append(widget)
        return row

    def _on_search_changed(self, entry, window, plugin_data):
        """Filter options by search query without removing widgets."""
        query = entry.get_text().strip().lower()

        # If no query, show all
        if not query:
            for row, _, _, _ in window.all_rows:
                row.set_visible(True)
            return

        # Otherwise, filter
        for row, key, short, default in window.all_rows:
            matches = (
                query in key.lower()
                or query in short.lower()
                or query in str(default).lower()
            )
            row.set_visible(matches)

    def _create_animation_row(self, full_key, opt, default):
        parts = str(default).strip().split(maxsplit=1)
        duration_ms = re.sub(r"\D", "", parts[0]) or "300"
        easing = parts[1] if len(parts) > 1 else "linear"

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        adj = Gtk.Adjustment(
            lower=0, upper=10000, step_increment=50, value=int(duration_ms)
        )
        spin = Gtk.SpinButton()
        spin.set_adjustment(adj)
        unit = Gtk.Label(label="ms")
        unit.add_css_class("dim-label")
        hbox.append(spin)
        hbox.append(unit)

        combo = Gtk.ComboBoxText()
        for e in ["linear", "ease", "ease-in", "ease-out", "ease-in-out"]:
            combo.append(e, e.title())
        combo.set_active_id(easing)
        hbox.append(combo)

        def save_anim(*_):
            ms = spin.get_value_as_int()
            ease = combo.get_active_id() or "linear"
            self.ipc.set_option_values({full_key: f"{ms}ms {ease}"})

        spin.connect("value-changed", save_anim)
        combo.connect("changed", save_anim)

        row = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
        row.append(Gtk.Label(label=opt["short"], halign=Gtk.Align.START))
        row.append(hbox)
        return row

    # === IPC Value Loader
    def _load_bool_value(self, switch, key):
        try:
            result = self.ipc.get_option_value(key)
            current = result.get("value", "false")
            GLib.idle_add(switch.set_active, self.to_bool(current))
        except:
            pass

    def _load_numeric_value(self, spin, key):
        try:
            result = self.ipc.get_option_value(key)
            current = result.get("value", "0")
            GLib.idle_add(spin.set_value, float(current))
        except:
            pass

    def _load_string_value(self, entry, key):
        try:
            result = self.ipc.get_option_value(key)
            current = result.get("value", "")
            GLib.idle_add(entry.set_text, str(current))
        except:
            pass

    def _load_enum_value(self, combo, key):
        try:
            result = self.ipc.get_option_value(key)
            current = result.get("value", "")
            GLib.idle_add(combo.set_active_id, str(current))
        except:
            pass

    # === IPC Save Handlers ===
    def on_bool_change(self, switch, _pspec, key):
        val = "true" if switch.get_active() else "false"
        self.ipc.set_option_values({key: val})
        self._save_value_to_toml(key, self.to_bool(val))  # Add this line

    def on_numeric_change(self, spin, key):
        val = str(round(spin.get_value()))
        self.ipc.set_option_values({key: val})
        self._save_value_to_toml(key, float(val))  # Add this line

    def on_string_change(self, entry, key):
        val = entry.get_text()
        self.ipc.set_option_values({key: val})
        self._save_value_to_toml(key, val)  # Add this line

    def on_enum_change(self, combo, key):
        val = combo.get_active_id()
        if val is not None:
            self.ipc.set_option_values({key: val})
            self._save_value_to_toml(key, val)  # Add this line

    def on_edit_list(self, button, key, current_value):
        dialog = Gtk.Dialog(title=f"Edit: {key}")
        dialog.set_default_size(500, 400)
        textview = Gtk.TextView()
        buffer = textview.get_buffer()
        buffer.set_text(str(current_value))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(textview)
        dialog.get_content_area().append(scroll)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK).get_style_context().add_class(
            "suggested-action"
        )
        dialog.connect("response", self._on_list_response, key, buffer)
        dialog.present()

    def _on_list_response(self, dialog, response, key, buffer):
        if response == Gtk.ResponseType.OK:
            text = buffer.get_text(
                buffer.get_start_iter(), buffer.get_end_iter(), False
            )
            self.ipc.set_option_values({key: text.strip()})
        dialog.destroy()

    def to_bool(self, val):
        return str(val).lower() in ("true", "1", "yes", "on")

    def load_plugin_metadata(self, plugin_name):
        xml_path = os.path.join(METADATA_DIR, f"{plugin_name}.xml")
        xml_options = []

        # Try to load from XML first
        if os.path.exists(xml_path):
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                plugin_elem = root.find(f'plugin[@name="{plugin_name}"]')
                if plugin_elem is not None:
                    for opt in plugin_elem.findall("option"):
                        parsed = self._parse_option(opt)
                        if parsed:
                            xml_options.append(parsed)
            except Exception as e:
                self.logger.warning(f"Failed to parse {xml_path}: {e}")

        # If XML has no options, fall back to wayfire.toml
        if len(xml_options) == 0:
            self.logger.info(
                f"No options in XML for '{plugin_name}', falling back to wayfire.toml"
            )
            toml_path = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")
            try:
                with open(toml_path, "r") as f:
                    data = toml.load(f)
                if plugin_name in data:
                    toml_options = data[plugin_name]
                    for key, value in toml_options.items():
                        # Infer type
                        if isinstance(value, bool):
                            opt_type = "bool"
                        elif isinstance(value, int):
                            opt_type = "int"
                        elif isinstance(value, float):
                            opt_type = "double"
                        else:
                            opt_type = "string"

                        # Heuristic: if key suggests it's a file/path, use special widget
                        is_path = any(
                            k in key.lower()
                            for k in {
                                "file",
                                "path",
                                "image",
                                "wallpaper",
                                "exec",
                                "script",
                            }
                        )

                        xml_options.append(
                            {
                                "name": key,
                                "type": opt_type,
                                "default": str(value),
                                "short": key.replace("_", " ").title(),
                                "long": f"Auto-loaded from wayfire.toml",
                                "choices": None,
                                "min": None,
                                "max": None,
                                "precision": 1,
                                "is_path": is_path,  # Mark for file chooser
                            }
                        )
            except Exception as e:
                self.logger.error(
                    f"Failed to load TOML fallback for {plugin_name}: {e}"
                )

        # Still no options?
        if not xml_options:
            self.logger.warning(f"No options found for plugin: {plugin_name}")
            return None

        # Get plugin info from XML if possible
        short = plugin_name.title()
        long_desc = f"Plugin '{plugin_name}' loaded from wayfire.toml"
        category = "Uncategorized"

        if os.path.exists(xml_path):
            try:
                tree = ET.parse(xml_path)
                plugin_elem = tree.getroot().find(f'plugin[@name="{plugin_name}"]')
                if plugin_elem is not None:
                    short = plugin_elem.findtext("short", short)
                    long_desc = plugin_elem.findtext("long", long_desc)
                    category = plugin_elem.findtext("category", category)
            except:
                pass

        return {
            "name": plugin_name,
            "short": short,
            "long": long_desc,
            "category": category,
            "options": xml_options,
        }

    def _parse_option(self, elem):
        name = elem.get("name")
        opt_type = elem.get("type", "string")
        default = elem.findtext("default", "")
        min_val = elem.findtext("min")
        max_val = elem.findtext("max")
        precision = float(elem.findtext("precision", "1"))
        short = elem.findtext("short", elem.findtext("_short", name))
        long_desc = elem.findtext("long", elem.findtext("_long", ""))
        choices = None

        if opt_type == "string":
            choices = []
            for desc in elem.findall("desc"):
                value = desc.findtext("value")
                label = desc.findtext("_name", value)
                if value:
                    choices.append((value, label))

        return {
            "name": name,
            "type": opt_type,
            "default": default,
            "min": min_val,
            "max": max_val,
            "precision": precision,
            "short": short,
            "long": long_desc,
            "choices": choices,
        }

    # === NEW: Load wayfire.toml into flat dict ===
    def _load_toml_config(self):
        """Load and flatten wayfire.toml into key/value dict."""
        if not os.path.exists(WAYFIRE_TOML_PATH):
            self.logger.warning(f"wayfire.toml not found: {WAYFIRE_TOML_PATH}")
            return {}

        try:
            with open(WAYFIRE_TOML_PATH, "r") as f:
                data = toml.load(f)
        except Exception as e:
            self.logger.error(f"Failed to parse wayfire.toml: {e}")
            return {}

        flat = {}

        def _flatten(prefix, table):
            for k, v in table.items():
                key = f"{prefix}{k}"
                if isinstance(v, dict):
                    _flatten(f"{key}/", v)
                else:
                    flat[key] = v

        _flatten("", data)
        return flat

    def about(self):
        """
        This plugin provides a graphical interface for configuring individual
        Wayfire plugins. It dynamically creates a separate, non-blocking
        GTK window for each plugin, populating it with a user-friendly UI
        based on the plugin's metadata. Users can view and modify
        various settings, including booleans, numbers, strings, and more complex
        types like colors and keybindings.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        This plugin is designed to offer a dynamic, real-time configuration
        interface by orchestrating **metadata parsing, asynchronous UI
        building, and persistent state management**.

        Its core functions are as follows:

        1.  **Dynamic UI Generation**: Unlike hardcoded interfaces, this plugin
            constructs its UI on the fly. When a user requests a plugin's
            configuration window, it first parses the plugin's metadata from
            an `.xml` file (if available). It then uses this data, including
            option types (`bool`, `int`, `string`, `color`), to programmatically
            create the appropriate GTK widgets—like switches, spin buttons,
            or color pickers—for each setting.

        2.  **Asynchronous Window Population**: To prevent the main application
            from freezing, the plugin uses a non-blocking approach. The
            `GLib.idle_add` function schedules the window's creation and content
            population to happen during the GTK event loop's idle time. This
            ensures the UI remains responsive even when loading a large number
            of configuration options.

        3.  **Unified State Management**: The plugin maintains a single source of
            truth for a plugin's state by merging data from three sources: the
            **plugin's XML metadata**, Wayfire's **real-time IPC state**, and the
            user's local **`wayfire.toml` configuration file**. When the
            window is opened, it first checks the `wayfire.toml` file to get the
            last saved value, which is then used to initialize the widget. When a
            user changes a setting, the plugin immediately updates the value
            via IPC and then persists the change to the `wayfire.toml` file,
            ensuring the settings are saved for future sessions.
        """
        return self.code_explanation.__doc__
