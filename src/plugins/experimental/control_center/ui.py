# ==== FILE: ui.py ====


def get_ui_class():
    from gi.repository import Gtk, Adw, Gdk

    class ControlCenterUI:
        def __init__(self, plugin_instance):
            self.p = plugin_instance
            self.gtk = Gtk
            self.adw = Adw

        def create_window(self):
            """Initializes the main application window and its base layout."""
            win = self.adw.ApplicationWindow()
            win.add_css_class("control-center-window")
            win.set_title("Waypanel Control Center")
            win.set_default_size(800, 600)

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

            # Stacks
            self.p.category_flowbox = self.gtk.FlowBox()
            self.p.category_flowbox.set_homogeneous(True)  # Makes grid uniform
            self.p.category_flowbox.set_sort_func(None)  # Resets custom sorting
            self.p.category_flowbox.set_filter_func(self._flowbox_filter_func)
            self.p.category_flowbox.set_selection_mode(self.gtk.SelectionMode.NONE)
            self.p.category_flowbox.set_row_spacing(20)
            self.p.category_flowbox.set_column_spacing(20)
            self.p.category_flowbox.set_halign(self.gtk.Align.CENTER)
            self.p.category_flowbox.add_css_class("control-center-category-grid")

            flowbox_scrolled = self.gtk.ScrolledWindow(vexpand=True, hexpand=True)
            flowbox_scrolled.set_child(self.p.category_flowbox)
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
