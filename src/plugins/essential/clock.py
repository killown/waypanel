def get_plugin_metadata(_):
    about = """
            • Displays current date and time in the top panel.
            """
    return {
        "id": "org.waypanel.plugin.clock",
        "name": "Clock",
        "version": "1.0.0",
        "enabled": True,
        "container": "top-panel-center",
        "index": 5,
        "deps": ["top_panel"],
        "description": about,
    }


def get_plugin_class():
    from src.plugins.core._base import BasePlugin

    class ClockPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.clock_button = None
            self.clock_box = None
            self.clock_label = None
            self.update_timeout_id = None
            self.add_hint(
                "Configuration for the Clock plugin, defining time and date display formats."
            )
            self.add_hint("Format %A, %B %d, %Y", "format")

        def on_start(self):
            self.create_clock_widget()

        def create_clock_widget(self):
            """
            Creates and configures the GTK widgets for the clock.
            """
            self.clock_box = self.gtk.Box(orientation=self.gtk.Orientation.HORIZONTAL)
            self.main_widget = (self.clock_box, "append")
            self.clock_box.set_halign(self.gtk.Align.CENTER)
            self.clock_box.set_baseline_position(self.gtk.BaselinePosition.CENTER)
            self.clock_box.add_css_class("clock-box")
            self.clock_button = self.gtk.Button()
            self.clock_button.add_css_class("clock-button")
            self.clock_label = self.gtk.Label()
            self.clock_label.add_css_class("clock-label")
            self.clock_button.set_child(self.clock_label)
            self.gtk_helper.add_cursor_effect(self.clock_button)
            self.update_widget_safely(self.clock_box.append, self.clock_button)
            self.update_clock()
            self.schedule_updates()

        def update_clock(self):
            """
            Updates the clock label with the current time.

            Returns:
                bool: Always returns True to continue the self.glib timeout.
            """
            try:
                format = self.get_plugin_setting(["format"], "%d %b %H:%M")
                current_time = self.datetime.datetime.now().strftime(format)
                self.clock_label.set_label(current_time)  # pyright: ignore
            except Exception as e:
                self.logger.error(f"Error updating clock: {e}")
            return True

        def schedule_updates(self):
            """
            Schedules a self.glib timeout to update the clock at the start of the next minute.
            """

            def schedule_next_update():
                now = self.datetime.datetime.now()
                seconds_until_next_minute = 60 - now.second
                self.glib.timeout_add_seconds(
                    seconds_until_next_minute, update_and_reschedule
                )

            def update_and_reschedule():
                self.update_clock()
                schedule_next_update()

            schedule_next_update()

        def stop_updates(self):
            """
            Stops the scheduled clock updates by removing the self.glib timeout source.
            """
            if self.update_timeout_id:
                self.glib.source_remove(self.update_timeout_id)
                self.update_timeout_id = None

        def code_explanation(self):
            """
            The core logic of this plugin is to display a real-time clock. It
            efficiently schedules UI updates to align with the start of each new
            minute, which maximizes accuracy while minimizing resource usage. The plugin
            also includes graceful error handling to prevent any display or formatting
            errors from crashing the application.
            """
            return self.code_explanation.__doc__

    return ClockPlugin
