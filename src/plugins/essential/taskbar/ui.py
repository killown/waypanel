class TaskbarUI:
    """Handles Gtk widget creation and structural layout for the Taskbar."""

    def __init__(self, plugin_instance):
        """Initializes the UI handler with the plugin instance."""
        self.plugin = plugin_instance
        self.config = plugin_instance.config

    def create_main_layout(self):
        """Builds the main container and flowbox structure without altering logic."""
        from gi.repository import Gtk

        pos = self.plugin.get_plugin_setting(["panel", "position"], "bottom")
        valid_panels = {
            "left": "left-panel-center",
            "right": "right-panel-center",
            "top": "top-panel-center",
            "bottom": "bottom-panel-center",
        }
        container = valid_panels.get(pos, "bottom-panel-center")
        vertical_layout_width = self.plugin.get_plugin_setting(
            ["panel", "vertical_layout_width"], 150
        )

        orientation = Gtk.Orientation.VERTICAL
        if "left-panel" in container or "right-panel" in container:
            orientation = Gtk.Orientation.HORIZONTAL

        self.plugin.taskbar = Gtk.FlowBox()
        self.plugin.taskbar.set_column_spacing(self.plugin.spacing)
        self.plugin.taskbar.set_row_spacing(self.plugin.spacing)
        self.plugin.taskbar.set_selection_mode(Gtk.SelectionMode.NONE)
        self.plugin.taskbar.set_orientation(orientation)
        self.plugin.taskbar.set_max_children_per_line(1)

        self.plugin.flowbox_container = Gtk.Box(orientation=orientation)
        self.plugin.flowbox_container.set_hexpand(True)
        self.plugin.flowbox_container.set_halign(Gtk.Align.FILL)
        self.plugin.taskbar.set_halign(Gtk.Align.CENTER)
        self.plugin.taskbar.set_valign(Gtk.Align.CENTER)
        self.plugin.flowbox_container.append(self.plugin.taskbar)

        if orientation is Gtk.Orientation.HORIZONTAL:
            self.plugin.scrolled_window.set_hexpand(True)
            top_h = self.plugin._panel_instance.top_panel.get_height()
            bottom_h = self.plugin._panel_instance.top_panel.get_height()
            space = top_h + bottom_h + 100
            self.plugin.scrolled_window.set_size_request(
                vertical_layout_width,
                self.plugin._panel_instance.monitor_height - space,
            )
            self.plugin.scrolled_window.set_vexpand(True)
        else:
            self.plugin.scrolled_window.set_size_request(
                self.plugin._panel_instance.monitor_width, 0
            )
            self.plugin.scrolled_window.set_vexpand(True)

        self.plugin.scrolled_window.set_halign(Gtk.Align.FILL)
        self.plugin.scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER
        )
        self.plugin.scrolled_window.set_child(self.plugin.flowbox_container)
        self.plugin.taskbar.add_css_class("taskbar")
        # Trigger initial sync
        self.plugin.Taskbar()

    def create_button(self):
        """Constructs a standard taskbar button widget with existing structure."""
        from gi.repository import Gtk

        button = Gtk.Button()
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=self.plugin.spacing
        )
        button.icon = Gtk.Image()
        button.label = Gtk.Label()
        button.icon.set_pixel_size(self.plugin.icon_size)
        box.append(button.icon)
        if self.plugin.show_label:
            box.append(button.label)
        button.set_child(box)
        button.add_css_class("taskbar-button")
        return button
