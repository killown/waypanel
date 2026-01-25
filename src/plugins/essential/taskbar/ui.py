class TaskbarUI:
    """Handles Gtk widget creation and structural layout for the Taskbar."""

    def __init__(self, plugin_instance):
        """Initializes the UI handler.

        Args:
            plugin_instance: The TaskbarPlugin instance.
        """
        self.plugin = plugin_instance
        self.config = plugin_instance.config

    def create_main_layout(self):
        """Builds the main container using CenterBox for absolute centering."""
        from gi.repository import Gtk

        pos = self.config.panel_position
        valid_panels = {
            "left": "left-panel-center",
            "right": "right-panel-center",
            "top": "top-panel-center",
            "bottom": "bottom-panel-center",
        }
        container = valid_panels.get(pos, "bottom-panel-center")

        orientation = Gtk.Orientation.VERTICAL
        if "left-panel" in container or "right-panel" in container:
            orientation = Gtk.Orientation.HORIZONTAL

        # The FlowBox holds the actual application buttons
        self.plugin.taskbar = Gtk.FlowBox()
        self.plugin.taskbar.set_column_spacing(self.config.spacing)
        self.plugin.taskbar.set_row_spacing(self.config.spacing)
        self.plugin.taskbar.set_selection_mode(Gtk.SelectionMode.NONE)
        self.plugin.taskbar.set_orientation(orientation)
        self.plugin.taskbar.set_max_children_per_line(1)

        # Force the FlowBox to be centered and not stretch its children
        self.plugin.taskbar.set_halign(Gtk.Align.CENTER)
        self.plugin.taskbar.set_valign(Gtk.Align.CENTER)

        self.plugin.center_box = Gtk.CenterBox(orientation=orientation)
        self.plugin.center_box.set_center_widget(self.plugin.taskbar)

        # Add CSS classes
        self.plugin.center_box.add_css_class("taskbar-container")
        self.plugin.taskbar.add_css_class("taskbar")

        # Initial data sync
        self.plugin.Taskbar()

    def create_button(self):
        """Constructs a taskbar button widget with proper alignment."""
        from gi.repository import Gtk

        button = Gtk.Button()
        # Ensure buttons don't expand to fill the entire CenterBox slot
        button.set_halign(Gtk.Align.CENTER)
        button.set_valign(Gtk.Align.CENTER)
        button.set_hexpand(False)
        button.set_vexpand(False)

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=self.config.spacing
        )
        button.icon = Gtk.Image()  # pyright: ignore
        button.label = Gtk.Label()  # pyright: ignore
        button.icon.set_pixel_size(self.config.icon_size)  # pyright: ignore

        box.append(button.icon)  # pyright: ignore
        if self.config.show_label:
            box.append(button.label)  # pyright: ignore

        button.set_child(box)
        button.add_css_class("taskbar-button")
        return button
