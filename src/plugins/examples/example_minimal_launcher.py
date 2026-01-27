def get_plugin_metadata(panel):
    """
    Define the plugin's properties and resolve container placement.
    """
    id = "org.waypanel.plugin.minimal_launcher"
    default_container = "top-panel-systray"

    container, id = panel.config_handler.get_plugin_container(default_container, id)

    return {
        "id": id,
        "name": "Minimal Launcher",
        "version": "1.1.0",
        "enabled": True,
        "container": container,
        # CRITICAL: Always define dependencies if the current plugin requires certain plugin to be loaded first
        # WARNING: Missing dependencies can cause plugins to fail loading.
        "deps": [],
        "description": "Minimal app_launcher replication with search and 3-column icon grid.",
    }


def get_plugin_class():
    """
    Returns the MinimalLauncher class with deferred imports.
    """
    from src.plugins.core._base import BasePlugin

    class MinimalLauncher(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.button = None
            self.popover = None
            self.flowbox = None
            self.search_bar = None

        def on_start(self):
            """Initializes the UI components."""
            self._setup_ui()

        def _setup_ui(self):
            """Sets up the layout with a search bar and a FlowBox grid."""
            # Main Toggle Button
            self.button = self.gtk.Button.new()

            # Popover using helper for ScrolledWindow
            # We use use_listbox=False because we will use a FlowBox for the 3-column grid
            self.popover, self.scrolled, _ = self.gtk_helper.create_popover(  # pyright: ignore
                parent_widget=self.button,
                css_class="app-launcher-popover",
                use_scrolled=True,
                use_listbox=False,
            )

            # Layout Container
            vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)
            vbox.set_margin_end(12)
            vbox.set_size_request(420, 500)

            # Search Bar
            self.search_bar = self.gtk.SearchEntry.new()
            self.search_bar.set_placeholder_text("Search apps...")
            self.search_bar.connect("search-changed", self._on_search_changed)
            vbox.append(self.search_bar)

            # FlowBox for 3-column Grid
            self.flowbox = self.gtk.FlowBox.new()
            self.flowbox.set_valign(self.gtk.Align.START)
            self.flowbox.set_max_children_per_line(3)
            self.flowbox.set_min_children_per_line(3)
            self.flowbox.set_selection_mode(self.gtk.SelectionMode.NONE)
            self.flowbox.set_homogeneous(True)
            self.flowbox.set_row_spacing(10)
            self.flowbox.set_column_spacing(10)

            # Integrate FlowBox into Scrolled Window
            self.scrolled.set_child(self.flowbox)
            self.scrolled.set_vexpand(True)
            vbox.append(self.scrolled)

            self.popover.set_child(vbox)

            # Finalize Button and Icon
            self.gtk_helper.create_popover_button(
                icon_name="launcher-program-symbolic",
                popover_widget=self.popover,
                css_class="panel-button",
                button_instance=self.button,
            )

            # Initial population
            self._populate_grid()

            self.main_widget = (self.button, "append")

        def _populate_grid(self, filter_text=""):
            """Fills the FlowBox with items in a 3-column grid layout."""
            # Clear existing children from FlowBox
            while child := self.flowbox.get_first_child():  # pyright: ignore
                self.flowbox.remove(child)  # pyright: ignore

            # Simulated app data
            apps = [
                ("Terminal", "utilities-terminal"),
                ("Files", "system-file-manager"),
                ("Browser", "internet-web-browser"),
                ("Editor", "accessories-text-editor"),
                ("Settings", "preferences-system"),
                ("Photos", "camera-photo"),
                ("Calc", "accessories-calculator"),
                ("Music", "multimedia-audio-player"),
                ("Video", "multimedia-video-player"),
            ]

            for name, icon in apps:
                if filter_text and filter_text not in name.lower():
                    continue

                # Create Item Layout (Icon + Label)
                item_vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 6)
                item_vbox.set_margin_end(8)
                item_vbox.set_halign(self.gtk.Align.CENTER)

                img = self.gtk.Image.new_from_icon_name(
                    self.gtk_helper.icon_exist(icon)
                )
                img.set_pixel_size(48)

                lbl = self.gtk.Label.new(name)
                lbl.add_css_class("caption")
                lbl.set_ellipsize(self.pango.EllipsizeMode.END)
                lbl.set_max_width_chars(10)

                item_vbox.append(img)
                item_vbox.append(lbl)

                # Wrap in a button for interaction
                app_btn = self.gtk.Button.new()
                app_btn.set_child(item_vbox)
                app_btn.set_has_frame(False)
                app_btn.add_css_class("app-launcher-item-btn")

                # Apply hover effects from helpers
                self.gtk_helper.add_cursor_effect(app_btn)

                self.flowbox.append(app_btn)  # pyright: ignore

        def _on_search_changed(self, entry):
            """Handles filtering when the search bar text changes."""
            query = entry.get_text().lower()
            self._populate_grid(query)

        def on_enable(self):
            self.logger.info("Minimal Grid Launcher enabled.")

        def on_disable(self):
            if self.button:
                self.gtk_helper.remove_widget(self.button)

    return MinimalLauncher
