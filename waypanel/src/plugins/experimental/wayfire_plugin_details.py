import os
import re
from gi.repository import Gtk, Adw, Pango, Gio
from xml.etree import ElementTree as ET
from src.plugins.core._base import BasePlugin

# === CONFIG ===
METADATA_DIR = "/usr/share/wayfire/metadata"
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
        """Open a configuration window for the given plugin."""
        if plugin_name in self.windows and self.windows[plugin_name].get_mapped():
            self.windows[plugin_name].present()
            return

        # Parse XML
        plugin_data = self.load_plugin_metadata(plugin_name)
        if not plugin_data:
            self.logger.error(f"Plugin not found or invalid: {plugin_name}")
            return

        window = self.build_window(plugin_data)
        self.windows[plugin_name] = window
        window.present()

    def load_plugin_metadata(self, plugin_name):
        xml_path = os.path.join(METADATA_DIR, f"{plugin_name}.xml")
        if not os.path.exists(xml_path):
            self.logger.warning(f"Metadata file not found: {xml_path}")
            return None

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            # ✅ Find the <plugin name="..."> element
            plugin_elem = root.find(f'plugin[@name="{plugin_name}"]')
            if plugin_elem is None:
                self.logger.warning(
                    f"No <plugin> element found with name='{plugin_name}' in {xml_path}"
                )
                return None

            short = plugin_elem.findtext(
                "_short", plugin_elem.findtext("short", plugin_name)
            )
            long_desc = plugin_elem.findtext("_long", plugin_elem.findtext("long", ""))
            category = plugin_elem.findtext("category", "Uncategorized")

            options = []
            for opt in plugin_elem.findall("option"):
                option = self.parse_option(opt)
                if option:
                    options.append(option)

            return {
                "name": plugin_name,
                "short": short,
                "long": long_desc,
                "category": category,
                "options": options,
            }
        except Exception as e:
            self.logger.error(f"Failed to parse {xml_path}: {e}")
            return None

    def parse_option(self, elem):
        name = elem.get("name")
        opt_type = elem.get("type", "string")
        default = elem.findtext("default", "")
        min_val = elem.findtext("min")
        max_val = elem.findtext("max")
        precision = float(elem.findtext("precision", "1"))

        short_desc = elem.findtext("short", elem.findtext("_short", name))
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
            "short": short_desc,
            "long": long_desc,
            "choices": choices,
        }

    def build_window(self, plugin_data):
        """Build GTK window with dynamic widgets from plugin data."""
        name = plugin_data["name"]
        window = Gtk.Window(
            title=f"Configure: {plugin_data['short']}",
            default_width=500,
            default_height=600,
        )
        window.set_modal(True)
        window.set_transient_for(self.obj.top_panel.get_root())

        # Header
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label=plugin_data["short"]))
        window.set_titlebar(header)

        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_btn.connect("clicked", lambda _: window.destroy())
        header.pack_end(close_btn)

        # Scrolled content
        scroll = Gtk.ScrolledWindow()
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        scroll.set_child(content_box)
        window.set_child(scroll)

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

        # Full key prefix
        prefix = f"{name}/"

        for opt in plugin_data["options"]:
            row = self.create_option_row(prefix, opt)
            if row:
                content_box.append(row)

        return window

    def create_option_row(self, prefix, opt):
        """Create a labeled widget row for one option."""
        full_key = prefix + opt["name"]

        label = Gtk.Label(label=opt["short"])
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.CENTER)
        label.set_tooltip_text(opt["long"]) if opt["long"] else None
        label.set_width_chars(20)
        label.set_max_width_chars(20)
        label.set_ellipsize(Pango.EllipsizeMode.END)

        # Get current value via IPC
        try:
            result = self.ipc.get_option_value(full_key)
            current = result.get("value", opt["default"])
        except Exception as e:
            self.logger.warning(f"Failed to get {full_key}: {e}")
            current = opt["default"]

        widget = None

        # === BOOLEAN ===
        if opt["type"] == "bool":
            widget = Gtk.Switch(valign=Gtk.Align.CENTER)
            widget.set_active(self.to_bool(current))
            widget.connect("notify::active", self.on_bool_change, full_key)

        # === INTEGER / DOUBLE ===
        elif opt["type"] in ("int", "double"):
            adj = Gtk.Adjustment(
                lower=float(opt["min"] or 0),
                upper=float(opt["max"] or 100),
                step_increment=opt["precision"],
                value=float(current),
            )
            widget = Gtk.SpinButton()
            widget.set_adjustment(adj)
            widget.connect("value-changed", self.on_numeric_change, full_key)

        # === STRING / COLOR / ACTIVATOR ===
        elif opt["type"] in (
            "string",
            "color",
            "activator",
            "output::mode",
            "output::position",
        ):
            widget = Gtk.Entry()
            widget.set_text(str(current))
            widget.connect("changed", self.on_string_change, full_key)

        # === ENUM (via <desc>) ===
        elif opt["type"] == "string" and opt["choices"]:
            widget = Gtk.ComboBoxText()
            for val, lbl in opt["choices"]:
                widget.append(val, lbl)
            widget.set_active_id(str(current))
            widget.connect("changed", self.on_enum_change, full_key)

        # === ANIMATION (e.g., "300ms linear") ===
        elif opt["type"] == "animation":
            parts = current.strip().split(maxsplit=1)
            duration = re.sub(r"\D", "", parts[0]) or "300"
            easing = parts[1] if len(parts) > 1 else "linear"

            hbox = Gtk.Box(spacing=6)
            adj = Gtk.Adjustment(
                lower=0, upper=10000, step_increment=50, value=int(duration)
            )
            spin = Gtk.SpinButton()
            spin.set_adjustment(adj)
            spin.set_suffix("ms")

            combo = Gtk.ComboBoxText()
            for e in ["linear", "ease", "ease-in", "ease-out", "ease-in-out"]:
                combo.append(e, e.title())
            combo.set_active_id(easing)

            hbox.append(spin)
            hbox.append(combo)

            def save_anim(*_):
                ms = spin.get_value_as_int()
                ease = combo.get_active_id() or "linear"
                self.ipc.set_option_values({full_key: f"{ms}ms {ease}"})

            spin.connect("value-changed", save_anim)
            combo.connect("changed", save_anim)

            row = Gtk.Box(spacing=12)
            row.append(label)
            row.append(hbox)
            return row

        # === DYNAMIC-LIST ===
        elif opt["type"] == "dynamic-list":
            widget = Gtk.Button(label="Edit List...")
            widget.connect("clicked", self.on_edit_list, full_key, current)
            row = Gtk.Box(spacing=12)
            row.append(label)
            row.append(widget)
            return row

        else:
            widget = Gtk.Label(label=f"[{opt['type']}] Unsupported")
            widget.set_halign(Gtk.Align.START)
            row = Gtk.Box(spacing=12)
            row.append(label)
            row.append(widget)
            return row

        # Default layout
        row = Gtk.Box(spacing=12)
        row.set_margin_top(4)
        row.set_margin_bottom(4)
        row.append(label)
        row.append(widget)
        return row

    # === IPC Update Handlers ===
    def on_bool_change(self, switch, _pspec, key):
        val = "true" if switch.get_active() else "false"
        self.ipc.set_option_values({key: val})

    def on_numeric_change(self, spin, key):
        val = str(spin.get_value())
        self.ipc.set_option_values({key: val})

    def on_string_change(self, entry, key):
        val = entry.get_text()
        self.ipc.set_option_values({key: val})

    def on_enum_change(self, combo, key):
        val = combo.get_active_id()
        if val is not None:
            self.ipc.set_option_values({key: val})

    def on_edit_list(self, button, key, current_value):
        dialog = Gtk.Dialog(
            title=f"Edit: {key}", transient_for=self.obj.top_panel.get_root()
        )
        dialog.set_default_size(500, 400)

        textview = Gtk.TextView()
        buffer = textview.get_buffer()
        buffer.set_text(current_value)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(textview)
        scroll.set_vexpand(True)

        content = dialog.get_content_area()
        content.append(scroll)

        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        save_btn = dialog.add_button("Save", Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")

        dialog.present()

        def on_response(_dlg, response):
            if response == Gtk.ResponseType.OK:
                new_text = buffer.get_text(
                    buffer.get_start_iter(), buffer.get_end_iter(), False
                )
                self.ipc.set_option_values({key: new_text.strip()})
            _dlg.destroy()

        dialog.connect("response", on_response)

    def to_bool(self, val):
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes", "on")
