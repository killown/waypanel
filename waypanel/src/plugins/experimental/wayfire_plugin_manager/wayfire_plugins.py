import os
import toml
from gi.repository import Gio, Gtk, Pango
from src.plugins.core._base import BasePlugin
import xml.etree.ElementTree as ET

WAYFIRE_METADATA_DIR = "/usr/share/wayfire/metadata"
WAYFIRE_TOML_PATH = os.path.expanduser("~/.config/waypanel/wayfire/wayfire.toml")

ENABLE_PLUGIN = True
DEPS = ["top_panel"]


def get_plugin_placement(panel_instance):
    return "top-panel-box-widgets-left", 4


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        plugin = WayfireRealtimePluginsPlugin(panel_instance)
        plugin.load_plugins_from_ipc()
        return plugin
    return None


class WayfireRealtimePluginsPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.popover = None
        self.flowbox = None
        self.plugin_icons = {
            "alpha": "plugin-alpha",
            "core": "plugin-core",
            "focus-steal-prevent": "plugin-wm-actions",
            "input-device": "plugin-input",
            "obs": "plugin-obs",
            "scale": "plugin-scale",
            "view-shot": "plugin-view-shot",
            "workspace-names": "plugin-workspace-names",
            "ammen99-bench": "plugin-bench",
            "crosshair": "plugin-crosshair",
            "follow-cursor-bindings": "plugin-wm-actions",
            "input-method-v1": "plugin-input",
            "oswitch": "plugin-oswitch",
            "session-lock": "plugin-wm-actions",
            "vswipe": "plugin-vswipe",
            "wrot": "plugin-wrot",
            "animate": "plugin-animate",
            "cube": "plugin-cube",
            "follow-focus": "plugin-follow-focus",
            "input": "plugin-input",
            "output": "plugin-wm-actions",
            "shortcuts-inhibit": "plugin-wm-actions",
            "vswitch": "plugin-vswitch",
            "wsets": "plugin-workspace-names",
            "annotate": "plugin-annotate",
            "decoration": "plugin-decoration",
            "force-fullscreen": "plugin-force-fullscreen",
            "invert": "plugin-invert",
            "pin-view": "plugin-move",
            "show-cursor": "plugin-wm-actions",
            "water": "plugin-water",
            "xdg-activation": "plugin-dbus_interface",
            "autorotate-iio": "plugin-autorotate-iio",
            "expo": "plugin-expo",
            "foreign-toplevel": "plugin-dbus_interface",
            "ipc-rules": "plugin-dbus_interface",
            "pixdecor": "plugin-decoration",
            "showrepaint": "plugin-showrepaint",
            "wayfire-shell": "plugin-lxqt-shell",
            "zoom": "plugin-zoom",
            "autostart": "plugin-autostart",
            "extra-animations": "plugin-animate",
            "ghost": "plugin-blur",
            "ipc": "plugin-dbus_interface",
            "place": "plugin-place",
            "showtouch": "plugin-wm-actions",
            "window-rules": "plugin-window-rules",
            "bench": "plugin-bench",
            "extra-gestures": "plugin-extra-gestures",
            "grid": "plugin-grid",
            "join-views": "plugin-join-views",
            "preserve-output": "plugin-preserve-output",
            "simple-tile": "plugin-simple-tile",
            "blur-to-background": "plugin-blur",
            "fast-switcher": "plugin-fast-switcher",
            "hide-cursor": "plugin-wm-actions",
            "mag": "plugin-mag",
            "resize": "plugin-resize",
            "scale-title-filter": "plugin-scale-title-filter",
            "tablet-mode": "plugin-hinge",
            "workarounds": "plugin-workarounds",
            "blur": "plugin-blur",
            "fisheye": "plugin-fisheye",
            "idle": "plugin-idle",
            "move": "plugin-move",
            "switcher": "plugin-switcher",
            "wm-actions": "plugin-wm-actions",
            "command": "plugin-command",
            "focus-change": "plugin-wm-actions",
            "switch-kb-layouts": "plugin-keycolor",
            "wobbly": "plugin-wobbly",
        }
        self.searchbar = None
        self.wf_plugins = []  # {name, desc, icon, enabled}
        self.active_plugin_names = set()

        # Main button
        self.button = Gtk.Button()
        self.main_widget = (self.button, "append")
        self._setup_button()

    def _setup_button(self):
        self.button.set_icon_name("plugin")
        self.button.add_css_class("app-launcher-menu-button")
        self.utils.add_cursor_effect(self.button)
        self.button.connect("clicked", self.open_popover)

    def parse_icon_name(self, name):
        if name in self.plugin_icons:
            return self.plugin_icons[name]
        else:
            return "preferences-plugin-symbolic"

    def load_plugins_from_ipc(self):
        """Load all plugins and query Wayfire IPC for which are currently active."""
        self.wf_plugins = []
        self.active_plugin_names = self._get_active_plugin_names()

        if not os.path.exists(WAYFIRE_METADATA_DIR):
            self.logger.error(f"Metadata dir not found: {WAYFIRE_METADATA_DIR}")
            return

        for filename in os.listdir(WAYFIRE_METADATA_DIR):
            if not filename.endswith(".xml"):
                continue
            path = os.path.join(WAYFIRE_METADATA_DIR, filename)
            try:
                tree = ET.parse(path)
                root = tree.getroot()
                name = root.get("name", filename.replace(".xml", ""))
                desc = root.findtext("description", "No description")
                icon_name = self.parse_icon_name(name)
                icon = root.findtext("icon", icon_name)

                self.wf_plugins.append(
                    {
                        "name": name,
                        "description": desc,
                        "icon": icon,
                        "enabled": name in self.active_plugin_names,
                    }
                )
            except Exception as e:
                self.logger.error(f"Failed to parse {filename}: {e}")

        # Sort: enabled first, then alphabetically
        self.wf_plugins.sort(key=lambda x: (-x["enabled"], x["name"]))

    def _get_active_plugin_names(self):
        """Query Wayfire IPC for currently loaded plugins."""
        try:
            result = self.ipc.get_option_value("core/plugins")
            value = result.get("value", "")
            return set(p.strip() for p in value.split() if p.strip())
        except Exception as e:
            self.logger.error(f"Failed to get active plugins from IPC: {e}")
            return set()

    def save_to_toml(self):
        """Save current state to wayfire.toml for persistence across restarts."""
        try:
            with open(WAYFIRE_TOML_PATH, "r") as f:
                config = toml.load(f)
        except FileNotFoundError:
            config = {}
        except Exception as e:
            self.logger.error(f"Failed to read wayfire.toml: {e}")
            return

        if "core" not in config:
            config["core"] = {}

        enabled = [p["name"] for p in self.wf_plugins if p["enabled"]]
        config["core"]["plugins"] = enabled  # TOML list

        try:
            with open(WAYFIRE_TOML_PATH, "w") as f:
                toml.dump(config, f)
            self.logger.info(f"Persisted plugin list to wayfire.toml: {enabled}")
        except Exception as e:
            self.logger.error(f"Failed to write wayfire.toml: {e}")

    def update_plugin_state(self, plugin_name, enable=True):
        """Enable or disable a plugin via IPC."""
        try:
            current = self.ipc.get_option_value("core/plugins")["value"]
            plugin_list = [p.strip() for p in current.split() if p.strip()]

            if enable:
                if plugin_name not in plugin_list:
                    plugin_list.append(plugin_name)
                    self.logger.info(f"Enabling plugin: {plugin_name}")
            else:
                if plugin_name in plugin_list:
                    plugin_list.remove(plugin_name)
                    self.logger.info(f"Disabling plugin: {plugin_name}")

            new_value = " ".join(plugin_list)
            self.ipc.set_option_values({"core/plugins": new_value})

            for p in self.wf_plugins:
                if p["name"] == plugin_name:
                    p["enabled"] = enable
                    break

            self.save_to_toml()

            if self.popover and self.popover.is_visible():
                self._refresh_popover()

        except Exception as e:
            self.logger.error(f"Failed to update plugin '{plugin_name}' via IPC: {e}")

    def create_popover(self):
        self.popover = Gtk.Popover()
        self.popover.add_css_class("app-launcher-popover")
        self.popover.set_has_arrow(True)
        self.popover.connect("closed", self.on_popover_closed)
        self.popover.connect("notify::visible", self.on_popover_opened)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.add_css_class("app-launcher-main-box")

        self.searchbar = Gtk.SearchEntry(placeholder_text="Search plugins...")
        self.searchbar.connect(
            "search_changed", lambda _: self.flowbox.invalidate_filter()
        )
        main_box.append(self.searchbar)

        scrolled = Gtk.ScrolledWindow(min_content_height=500, width_request=720)
        self.flowbox = Gtk.FlowBox(
            valign=Gtk.Align.START,
            halign=Gtk.Align.FILL,
            max_children_per_line=5,
            selection_mode=Gtk.SelectionMode.NONE,
            activate_on_single_click=True,
        )
        self.flowbox.add_css_class("app-launcher-flowbox")
        self.flowbox.set_filter_func(self.filter_func)
        self.flowbox.connect("child-activated", self.on_plugin_clicked)
        scrolled.set_child(self.flowbox)
        main_box.append(scrolled)

        self.popover.set_child(main_box)
        self._populate_flowbox()
        return self.popover

    def _populate_flowbox(self):
        self.flowbox.remove_all()
        for plugin in self.wf_plugins:
            self._add_plugin_row(plugin)

    def _add_plugin_row(self, plugin):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_margin_top(4)
        vbox.set_margin_bottom(4)
        vbox.add_css_class("app-launcher-vbox")
        vbox.MYTEXT = plugin["name"]

        # Build icon path
        icon_name = f"plugin-{plugin['name']}.svg"
        icon_path = f"/usr/share/wcm/icons/{icon_name}"

        # Create image from file if exists, else fallback to generic icon
        if os.path.exists(icon_path):
            image = Gtk.Image.new_from_file(icon_path)
        else:
            # Fallback: use a default icon from the system theme
            image = Gtk.Image.new_from_icon_name("application-x-executable")

        image.set_pixel_size(48)
        image.add_css_class("app-launcher-icon-from-popover")
        self.utils.add_cursor_effect(image)

        label = Gtk.Label(label=plugin["name"])
        label.set_max_width_chars(12)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.add_css_class("app-launcher-label-from-popover")

        status = Gtk.Label()
        status.set_markup(
            '<span size="small" foreground="green">● Enabled</span>'
            if plugin["enabled"]
            else '<span size="small" foreground="gray">● Disabled</span>'
        )
        status.set_halign(Gtk.Align.CENTER)

        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        switch.set_active(plugin["enabled"])
        switch.connect("notify::active", self.on_toggle, plugin["name"])

        vbox.append(image)
        vbox.append(label)
        vbox.append(status)
        vbox.append(switch)

        self.flowbox.append(vbox)

    def on_plugin_clicked(self, flowbox, child):
        plugin_name = child.get_child().MYTEXT
        self.plugins["wayfire_plugin_details"].open_plugin_config_window(plugin_name)

    def on_toggle(self, switch, _pspec, name):
        active = switch.get_active()
        self.update_plugin_state(name, enable=active)

    def _refresh_popover(self):
        self.flowbox.remove_all()
        for plugin in self.wf_plugins:
            self._add_plugin_row(plugin)
        self.flowbox.invalidate_filter()

    def filter_func(self, child):
        text = self.searchbar.get_text().lower()
        if not text:
            return True
        label = (
            child.get_child().get_first_child().get_next_sibling()
        )  # label after image
        return text in label.get_label().lower()

    def open_popover(self, *_):
        # Always refresh state from IPC when opening
        self.load_plugins_from_ipc()

        if self.popover and self.popover.is_visible():
            self.popover.popdown()
        else:
            if not self.popover:
                self.create_popover()
            else:
                self._refresh_popover()
            self.popover.set_parent(self.button)
            self.popover.popup()

    def on_popover_opened(self, *_):
        pass

    def on_popover_closed(self, *_):
        pass
