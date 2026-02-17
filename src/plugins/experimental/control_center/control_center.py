def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.control_center",
        "name": "ControlCenter",
        "version": "1.0.0",
        "enabled": True,
        "priority": 99,
        "deps": ["css_generator"],
        "description": "Plugin Control Center for Waypanel",
    }


def get_plugin_class():
    import gi
    from typing import Dict, Any

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gtk, Adw, Gdk  # pyright: ignore
    from src.plugins.core._base import BasePlugin
    from ._helpers import ControlCenterHelpers
    from ._ui import get_ui_class
    from ._logic import get_logic_class

    class ControlCenter(BasePlugin):
        """
        The main Control Center window bridge.
        Delegates UI construction to ui.py and business logic to logic.py.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)

        def delay_on_start(self):
            self.config = {}
            self.widget_map = {}
            self.ui_key_to_plugin_id_map: Dict[str, str] = {}

            # Module instances
            self.helper = ControlCenterHelpers(self)
            self.ui = get_ui_class()(self)
            self.logic = get_logic_class()(self)

            # Attributes populated by UI class
            self.win = None
            self.toast_overlay: Adw.ToastOverlay = None  # pyright: ignore
            self.back_button = None
            self.back_button_stack = None
            self.save_button = None
            self.save_button_stack = None
            self.search_entry = None
            self.category_flowbox = None
            self.content_stack = None
            self.main_stack = None

            # CSS Provider stored here for UI access
            self.current_wp_css_provider = None

            self.gtk = Gtk
            self.adw = Adw
            self.plugins["css_generator"].install_css("control-center.css")
            return False

        def on_start(self):
            self.glib.timeout_add_seconds(3, self.delay_on_start)

        def load_config(self):
            """Syncs configuration state."""
            self.config = self.config_handler.config_data

        def do_activate(self):
            """Initializes and presents the Control Center window."""
            if not self.win:
                self.win = self.ui.create_window()
                self.win.connect("close-request", self.on_close_request)

                self.load_config()
                # Delegated to logic.py
                self.logic.setup_categories_grid()

                self.main_stack.set_visible_child_name("category_grid")  # pyright: ignore
                self.save_button_stack.set_visible_child_name("empty")  # pyright: ignore
                self.back_button_stack.set_visible_child_name("empty")  # pyright: ignore

            self.win.present()

        def create_category_widget(self, category_name: str) -> Gtk.Widget:
            """Bridge to UI widget construction."""
            return self.ui.create_category_widget(category_name)

        def create_content_page(
            self, category_name: str, data: Dict[str, Any]
        ) -> Gtk.ScrolledWindow:
            """Bridge to Logic content generation."""
            return self.logic.create_content_page(category_name, data)

        def on_category_widget_clicked(self, gesture, n_press, x, y, category_name):
            """Handles navigation to settings pages."""
            self.content_stack.set_visible_child_name(category_name)  # pyright: ignore
            self.main_stack.set_visible_child_name("settings_pages")  # pyright: ignore

            if category_name != "theme":
                self.save_button_stack.set_visible_child_name("save_button")  # pyright: ignore
            else:
                self.save_button_stack.set_visible_child_name("empty")  # pyright: ignore

            self.back_button_stack.set_visible_child_name("back_button")  # pyright: ignore

        def on_back_clicked(self, button):
            """Returns to the primary grid view."""
            self.main_stack.set_visible_child_name("category_grid")  # pyright: ignore
            self.save_button_stack.set_visible_child_name("empty")  # pyright: ignore
            self.back_button_stack.set_visible_child_name("empty")  # pyright: ignore
            self.search_entry.set_text("")  # pyright: ignore

        def on_search_changed(self, search_entry):
            """Bridge to search filtering logic."""
            self.logic.on_search_changed(search_entry)

        def on_save_clicked(self, button):
            """Delegates save operation to helper."""
            current_category = self.content_stack.get_visible_child_name()  # pyright: ignore
            if current_category:
                self.helper.save_category(current_category)

        def _on_add_field_clicked(self, button, group, category_name):
            """Bridge to dynamic field logic."""
            self.helper._on_add_field_clicked(button, group, category_name)  # pyright: ignore

        def _on_plugin_enable_toggled(self, switch, gparam, category_name):
            """Bridge to plugin runtime management logic."""
            self.logic._on_plugin_enable_toggled(switch, gparam, category_name)

        def on_close_request(self, window):
            """Cleans up window reference on close."""
            window.destroy()
            self.win = None
            return True

        def get_icon_for_category(self, category_name: str) -> str:
            """Logic for icon resolution."""
            norm_name = category_name.replace("_", " ").split()[0].lower()
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())  # pyright: ignore

            icon_name = self._gtk_helper.icon_exist(norm_name)
            if icon_name:
                return icon_name

            tmp_cat_name = category_name.split(".")[-1]
            for name in [
                tmp_cat_name,
                f"{norm_name}-symbolic",
                f"preferences-{norm_name}-symbolic",
            ]:
                if icon_theme.has_icon(name):
                    return name
            return "preferences-system-symbolic"

    return ControlCenter
