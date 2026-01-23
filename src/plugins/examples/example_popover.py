def get_plugin_metadata(_):
    """
    Define the plugin's properties, dependencies, and panel placement.

    Args:
        _: The main Panel instance (unused).

    Returns:
        dict: Plugin metadata including ID, container, and dependencies.
    """
    return {
        "id": "org.waypanel.plugin.popover_helper_demo",
        "name": "Popover Helper Demo",
        "version": "1.0.0",
        "enabled": True,
        "container": "top-panel-systray",
        "deps": [
            "top_panel"
        ],  # WARNING: Missing dependencies can cause plugins to fail loading.
        "description": "Example using self.gtk_helper to create popovers and buttons",
    }


def get_plugin_class():
    """
    Deferred import and class definition for the PopoverHelperDemo plugin.

    Returns:
        type: The PopoverHelperDemo class inherited from BasePlugin.
    """
    from src.plugins.core._base import BasePlugin

    class PopoverHelperDemo(BasePlugin):
        """
        A reference implementation for Gtk.Popover integration using Waypanel helpers.

        This plugin demonstrates the correct initialization order for GTK 4 popovers:
        1. Create the parent widget first.
        2. Initialize the popover with that parent reference.
        3. Use gtk_helper to wire up automated toggle logic.
        """

        PLUGIN_ID = "popover_helper_demo"

        def __init__(self, panel_instance):
            """
            Initialize the plugin components and assemble the UI.

            Args:
                panel_instance: The main application panel instance.
            """
            super().__init__(panel_instance)

            # Create the trigger button first to act as the coordinate parent.
            # GTK 4 popovers require a non-None parent during certain helper operations.
            self.button = self.gtk.Button.new()

            # Create the Popover using the GtkHelper.
            # This establishes standardized state management (focus/active flags).
            self.popover = self.gtk_helper.create_popover(
                parent_widget=self.button, css_class="demo-popover", has_arrow=True
            )

            # Assemble internal popover layout.
            self.content_box = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, 10)

            title = self.gtk.Label.new("Helper-based Popover")
            title.add_css_class("title-4")

            close_btn = self.gtk.Button.new_with_label("Close")
            close_btn.connect("clicked", lambda _: self.popover.popdown())

            self.content_box.append(title)
            self.content_box.append(close_btn)
            self.popover.set_child(self.content_box)

            # Configure the button with the icon and popover logic.
            # This helper re-parents the popover and handles visibility toggling.
            self.gtk_helper.create_popover_button(
                icon_name="org.gnome.Settings-accessibility-pointing-symbolic",
                popover_widget=self.popover,
                css_class="panel-button",
                button_instance=self.button,
            )

            # Register dynamic settings for the Control Center.
            # NOTE: If 'main_icon' exists in the configuration, it will override
            # the 'icon_name' provided in create_popover_button above during
            # subsequent configuration loads.
            self.get_plugin_setting_add_hint(
                ["main_icon"],
                "org.gnome.Settings-about-symbolic",
                "main icon from popover helper demo, this will override the default icon from create_popover_button",
            )

            # Assign to main_widget for automatic panel placement by the loader.
            self.main_widget = (self.button, "append")

        def on_enable(self):
            """Lifecycle hook called when the plugin is activated."""
            self.logger.info("Popover Helper Demo enabled")

    return PopoverHelperDemo
