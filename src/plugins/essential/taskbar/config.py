class TaskbarConfig:
    """Handles all plugin settings registration and central retrieval."""

    def __init__(self, plugin_instance):
        """Initializes the config handler with the plugin instance.

        Args:
            plugin_instance: The TaskbarPlugin instance.
        """
        self.plugin = plugin_instance
        self.h = self.plugin.get_plugin_setting_add_hint

    def register_settings(self):
        """Registers all settings with hints for the Control Center."""
        self.icon_size = self.h(["layout", "icon_size"], 42, "Icon size.")
        self.spacing = self.h(["layout", "spacing"], 5, "Spacing between items.")
        self.show_label = self.h(
            ["layout", "show_label"], True, "Globally show labels."
        )
        self.max_title_length = self.h(
            ["layout", "max_title_length"], 33, "Title character limit."
        )
        self.group_apps = self.h(
            ["layout", "group_apps"], True, "Group windows of same app."
        )
        self.hide_ungrouped_titles = self.h(
            ["layout", "hide_ungrouped_titles"],
            True,
            "Hide title if app is not grouped.",
        )
        self.show_focused_group_title = self.h(
            ["layout", "show_focused_group_title"],
            True,
            "Show focused window title in group.",
        )
        self.show_group_count = self.h(
            ["layout", "show_group_count"],
            True,
            "Show number of windows in group label.",
        )
        self.exclusive_zone = self.h(
            ["panel", "exclusive_zone"], True, "Reserve space on screen."
        )
        self.panel_position = self.h(
            ["panel", "position"], "bottom", "Placement on screen."
        )
        self.vertical_layout_width = self.h(
            ["panel", "vertical_layout_width"], 150, "Width when vertical."
        )
        self.layer_always_exclusive = self.h(
            ["panel", "layer_always_exclusive"], False, "Always stay exclusive."
        )
