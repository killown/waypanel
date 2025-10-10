def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.system_monitor",
        "name": "system Monitor",
        "version": "1.0.0",
        "enabled": True,
        "index": 9,
        "container": "top-panel-systray",
        "deps": ["top_panel", "gestures_setup"],
    }


def get_plugin_class():
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GObject  # pyright: ignore

    class ProperMetricItem(GObject.Object):
        def __init__(self, name, value, tooltip=""):
            super().__init__()
            self._name = name
            self._value = value
            self._tooltip = tooltip

        @GObject.Property(type=str)
        def name(self):  # pyright: ignore
            return self._name

        @name.setter
        def name(self, value):
            self._name = value
            self.notify("name")

        @GObject.Property(type=str)
        def value(self):  # pyright: ignore
            return self._value

        @value.setter
        def value(self, new_value):
            if self._value != new_value:
                self._value = new_value
                self.notify("value")

        @GObject.Property(type=str)
        def tooltip(self):  # pyright: ignore
            return self._tooltip

        @tooltip.setter
        def tooltip(self, value):
            self._tooltip = value
            self.notify("tooltip")

    from ._system_monitor_helper import SystemMonitorHelpers
    from src.plugins.core._base import BasePlugin

    class SystemMonitorPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover_system = None
            self.update_timeout_id = None
            self.helper = SystemMonitorHelpers(panel_instance)
            self.list_view = None
            self.list_store = Gio.ListStore.new(ProperMetricItem)
            self.metric_items = {}
            self.create_gesture = self.plugins["gestures_setup"].create_gesture
            self.create_menu_popover_system()

        def create_menu_popover_system(self):
            self.menubutton_system = self.gtk.Button()
            self.menubutton_system.add_css_class("system-monitor-menubutton")
            icon_name = self.gtk_helper.icon_exist(
                "system-monitor-app-symbolic",
                [
                    "utilities-system-monitor-symbolic",
                    "com.github.stsdc.monitor-symbolic",
                ],
            )
            self.menubutton_system.set_icon_name(icon_name)
            self.menubutton_system.connect("clicked", self.open_popover_system)
            self.gtk_helper.add_cursor_effect(self.menubutton_system)
            self.main_widget = (self.menubutton_system, "append")

        def start_system_updates(self):
            """Start periodic updates for system data."""
            self.glib.timeout_add(1000, self.fetch_and_update_system_data)
            self.update_timeout_id = self.glib.timeout_add_seconds(
                self.helper.update_interval, self.fetch_and_update_system_data
            )

        def stop_system_updates(self):
            """Stop periodic updates for system data."""
            if self.update_timeout_id:
                self.glib.source_remove(self.update_timeout_id)
                self.update_timeout_id = None

        def update_metric(self, name, value, tooltip_text=None, is_visible=True):
            if self.list_view is None:
                return
            if name in self.metric_items:
                item = self.metric_items[name]
                if is_visible:
                    item.value = str(value)
                    if tooltip_text is not None:
                        item.tooltip = tooltip_text
                else:
                    self.remove_metric(name)
            elif is_visible:
                self.add_metric(name, value, tooltip_text)

        def remove_metric(self, name):
            if name in self.metric_items:
                item_to_remove = self.metric_items.pop(name)
                found_index = -1
                for i in range(self.list_store.get_n_items()):
                    item = self.list_store.get_item(i)
                    if item is item_to_remove:
                        found_index = i
                        break
                if found_index != -1:
                    self.list_store.remove(found_index)

        def add_metric(self, name, value, tooltip_text=None):
            if self.list_view is None or name in self.metric_items:
                return None
            tooltip = tooltip_text if tooltip_text is not None else ""
            item = ProperMetricItem(name, str(value), tooltip)
            self.list_store.append(item)
            self.metric_items[name] = item
            return item

        def add_initial_rows(self):
            """Add static rows on popover creation."""
            self.list_store.remove_all()
            self.metric_items.clear()

            def _add(name, value="..."):
                item = ProperMetricItem(name, value)
                self.list_store.append(item)
                self.metric_items[name] = item

            _add("CPU Usage")
            _add("RAM Usage")
            _add("Network")
            _add("Battery")
            _add("GPU")
            _add("VRAM")
            _add("GPU Load")
            _add("Watch events", "all")
            _add("Exec")
            _add("APP ID")
            _add("APP PID")
            _add("APP Memory Usage")
            _add("APP Disk Read")
            _add("APP Disk Write")
            _add("APP Disk Read Count")
            _add("APP Disk Write Count")

        def add_gpu(self):
            """Add/Update GPU information."""
            gpu_rows = ["GPU", "VRAM", "GPU Load"]
            try:
                import pyamdgpuinfo

                if pyamdgpuinfo.detect_gpus():
                    gpu = pyamdgpuinfo.get_gpu(0)
                    total_vram_gb = gpu.memory_info["vram_size"] / (1024**3)
                    used_vram_bytes = gpu.query_vram_usage()
                    used_vram_gb = used_vram_bytes / (1024**3)
                    usage_percent = (
                        used_vram_bytes / gpu.memory_info["vram_size"]
                    ) * 100
                    gpu_load = gpu.query_load()
                    self.update_metric("GPU", gpu.name)
                    self.update_metric(
                        "VRAM",
                        f"({usage_percent:.1f}%) {used_vram_gb:.1f} / {total_vram_gb:.1f} GB",
                    )
                    self.update_metric("GPU Load", f"{gpu_load:.1f}%")
                else:
                    for key in gpu_rows:
                        self.remove_metric(key)
            except (ImportError, Exception):
                for key in gpu_rows:
                    self.remove_metric(key)
            return False

        def fetch_and_update_system_data(self):
            """Fetch system data and update the list store's existing items."""
            cpu_usage = self.helper.get_cpu_usage()
            memory_usage = self.helper.get_ram_info()
            disk_usages = self.helper.get_disk_usages()
            network_usage = self.helper.get_network_usage()
            battery_status = self.helper.get_battery_status()
            focused_view_id = self._wf_helper.get_the_last_focused_view_id()
            focused_view = self.ipc.get_view(focused_view_id)
            self.update_metric("CPU Usage", f"{cpu_usage}%")
            self.update_metric("RAM Usage", f"{memory_usage}")
            self.glib.idle_add(self.add_gpu)
            current_mountpoints = {usage["mountpoint"] for usage in disk_usages}
            for usage in disk_usages:
                mountpoint = usage["mountpoint"]
                used = usage["used"]
                total = usage["total"]
                name = f"Disk ({mountpoint})"
                self.update_metric(name, f"{used:.1f} / {total:.0f}GB")
            all_known_keys = list(self.metric_items.keys())
            for key in all_known_keys:
                if key.startswith("Disk ("):
                    mountpoint = key[6:-1]
                    if mountpoint not in current_mountpoints:
                        self.remove_metric(key)
            self.update_metric("Network", network_usage)
            self.update_metric(
                "Battery", battery_status, is_visible=(battery_status is not None)
            )
            focused_view_keys = [
                "Exec",
                "APP ID",
                "APP PID",
                "APP Memory Usage",
                "APP Disk Read",
                "APP Disk Write",
                "APP Disk Read Count",
                "APP Disk Write Count",
            ]
            if focused_view:
                pid = focused_view["pid"]
                process_usage = self.helper.get_process_usage(pid)
                process_disk_usage = self.helper.get_process_disk_usage(pid)
                self.update_metric("Exec", self.helper.get_process_executable(pid))
                self.update_metric(
                    "APP ID", f"({focused_view['app-id']}): {focused_view['id']}"
                )
                self.update_metric(
                    "APP PID", pid, tooltip_text="Right click to kill process"
                )
                proc_usage_visible = process_usage is not None
                self.update_metric(
                    "APP Memory Usage",
                    process_usage["memory_usage"] if proc_usage_visible else "...",
                    is_visible=proc_usage_visible,
                )
                disk_read_visible = process_disk_usage is not None
                self.update_metric(
                    "APP Disk Read",
                    process_disk_usage["read_bytes"] if disk_read_visible else "...",
                    is_visible=disk_read_visible,
                )
                self.update_metric(
                    "APP Disk Write",
                    process_disk_usage["write_bytes"] if disk_read_visible else "...",
                    is_visible=disk_read_visible,
                )
                self.update_metric(
                    "APP Disk Read Count",
                    str(process_disk_usage["read_count"])
                    if disk_read_visible
                    else "...",
                    is_visible=disk_read_visible,
                )
                self.update_metric(
                    "APP Disk Write Count",
                    str(process_disk_usage["write_count"])
                    if disk_read_visible
                    else "...",
                    is_visible=disk_read_visible,
                )
            else:
                for key in focused_view_keys:
                    self.update_metric(key, "", is_visible=False)
            self.update_metric("Watch events", "all")
            return self.popover_system and self.popover_system.is_visible()

        def open_popover_system(self, *_):
            if self.popover_system and self.popover_system.is_visible():
                self.popover_system.popdown()
                self.stop_system_updates()
            elif self.popover_system and not self.popover_system.is_visible():
                self.popover_system.popup()
                self.start_system_updates()
            else:
                self.create_popover_system()
                self.popover_system.popup()
                self.start_system_updates()

        def create_popover_system(self):
            """
            Create the system monitor popover and populate it with a GtkListView.
            Height is now dynamic, up to POPOVER_MAX_HEIGHT, with a fixed minimum.
            """
            POPOVER_WIDTH = 380
            POPOVER_HEIGHT_ROWS_TIMES_PIXELS = 19 * 26
            POPOVER_MIN_HEIGHT = 200
            self.popover_system = self.gtk.Popover.new()
            self.popover_system.add_css_class("system-monitor-popover")
            self.popover_system.connect("closed", self.popover_is_closed)
            vbox = self.gtk.Box.new(self.gtk.Orientation.VERTICAL, spacing=10)
            vbox.add_css_class("system-monitor-vbox")
            vbox.set_margin_top(10)
            vbox.set_margin_bottom(10)
            vbox.set_margin_start(10)
            vbox.set_margin_end(10)
            vbox.set_size_request(POPOVER_WIDTH, -1)
            selection_model = self.gtk.SingleSelection.new(self.list_store)
            row_factory = self.gtk.SignalListItemFactory()
            row_factory.connect("setup", self._row_factory_setup)
            row_factory.connect("bind", self._row_factory_bind)
            self.list_view = self.gtk.ListView.new(selection_model, row_factory)
            self.list_view.add_css_class("system-monitor-listview")
            self.list_view.set_single_click_activate(False)
            self.list_view.set_size_request(-1, POPOVER_MIN_HEIGHT)
            scrolled_window = self.gtk.ScrolledWindow()
            scrolled_window.add_css_class("system-monitor-scrolledwindow")
            scrolled_window.set_child(self.list_view)
            scrolled_window.set_policy(
                self.gtk.PolicyType.NEVER, self.gtk.PolicyType.AUTOMATIC
            )
            scrolled_window.set_size_request(
                POPOVER_WIDTH, POPOVER_HEIGHT_ROWS_TIMES_PIXELS
            )
            vbox.append(scrolled_window)
            self.popover_system.set_child(vbox)
            self.popover_system.set_parent(self.menubutton_system)
            self.add_initial_rows()
            self.list_view.show()

        def _row_factory_setup(self, factory, list_item):
            """Setup the row (ListItem) container and its children (the widgets inside)."""
            hbox = self.gtk.Box.new(self.gtk.Orientation.HORIZONTAL, spacing=20)
            hbox.add_css_class("system-monitor-hbox")
            hbox.set_halign(self.gtk.Align.FILL)
            hbox.set_margin_top(3)
            hbox.set_margin_bottom(3)
            name_label = self.gtk.Label(label="Initializing...")
            name_label.add_css_class("system-monitor-name-label")
            name_label.set_halign(self.gtk.Align.START)
            name_label.set_hexpand(True)
            name_label.set_xalign(0.0)
            name_label.set_justify(self.gtk.Justification.LEFT)
            name_label.set_width_chars(15)
            value_label = self.gtk.Label(label="...")
            value_label.add_css_class("system-monitor-value-label")
            value_label.set_halign(self.gtk.Align.END)
            value_label.set_xalign(1.0)
            hbox.append(name_label)
            hbox.append(value_label)
            list_item.set_child(hbox)
            list_item._name_label = name_label
            list_item._value_label = value_label
            list_item._bindings = []

        def _row_factory_bind(self, factory, list_item):
            """Bind the MetricItem data to the row widgets and attach gestures."""
            metric_item = list_item.get_item()
            hbox = list_item.get_child()
            for binding in list_item._bindings:
                binding.unbind()
            list_item._bindings.clear()
            list_item._name_label.set_label(metric_item.name)
            binding_value = metric_item.bind_property(
                "value", list_item._value_label, "label", GObject.BindingFlags.DEFAULT
            )
            list_item._bindings.append(binding_value)
            binding_tooltip = metric_item.bind_property(
                "tooltip", hbox, "tooltip-text", GObject.BindingFlags.DEFAULT
            )
            list_item._bindings.append(binding_tooltip)
            name = metric_item.name
            if name == "APP ID":
                self.create_gesture_for_focused_view_id(hbox)
            if name == "APP PID":
                self.create_gesture_for_focused_view_pid(hbox)
            elif name == "CPU Usage":
                self.create_gesture_for_cpu_usage(hbox)
            elif "Disk (" in name or "Disk Read" in name or "Disk Write" in name:
                self.create_iotop_gesture_for_focused_view_pid(hbox)
            elif name in ["GPU", "VRAM", "GPU Load"]:
                self.create_gesture_for_amdgpu_top(hbox)
            elif name == "Watch events":
                self.create_watch_events_gesture(hbox)

        def last_toplevel_focused_view(self):
            if "taskbar" in self.plugins:
                return self.plugins["taskbar"].last_toplevel_focused_view
            return None

        def create_gesture_for_amdgpu_top(self, hbox):
            self.create_gesture(hbox, 1, self.helper.open_terminal_with_amdgpu_top)

        def open_gnome_system_monitor(self, _):
            self.run_cmd("gnome-system-monitor")

        def create_gesture_for_cpu_usage(self, hbox):
            self.create_gesture(hbox, 1, self.open_gnome_system_monitor)

        def create_gesture_for_focused_view_id(self, hbox):
            def view_callback(_):
                view_id = self.wf_helper.get_the_last_focused_view_id()
                view = self.ipc.get_view(view_id)
                self.helper.open_kitty_with_ipython_view(view)

            self.create_gesture(hbox, 1, view_callback)

        def create_gesture_for_focused_view_pid(self, hbox):
            """
            Create gestures for the APP PID row.
            The PID is fetched dynamically on click (via the lambda) to ensure it's current.
            """

            def htop_callback(_):
                focused_view = self.last_toplevel_focused_view()
                if focused_view is not None:
                    pid = focused_view["pid"]
                    self.helper.open_terminal_with_htop(pid)

            self.create_gesture(hbox, 1, htop_callback)
            self.create_gesture(hbox, 2, lambda _: self.helper.open_system_monitor())

            def kill_callback(_):
                focused_view = self.last_toplevel_focused_view()
                if focused_view is not None:
                    pid = focused_view["pid"]
                    self.helper.kill_process(pid)

            self.create_gesture(hbox, 3, kill_callback)

        def create_iotop_gesture_for_focused_view_pid(self, hbox):
            """
            Create gestures for disk rows.
            The PID is fetched dynamically on click (via the lambda) to ensure it's current.
            """

            def iotop_callback(_):
                focused_view = self.last_toplevel_focused_view()
                if focused_view is not None:
                    pid = focused_view["pid"]
                    disk_read_metric = self.metric_items.get("APP Disk Read")
                    if disk_read_metric and disk_read_metric.value != "...":
                        self.helper.open_terminal_with_iotop(pid)
                    else:
                        pass

            self.create_gesture(hbox, 1, iotop_callback)

        def create_watch_events_gesture(self, hbox):
            self.create_gesture(hbox, 1, self.helper.open_kitty_with_rich_events_view)
            self.create_gesture(
                hbox, 3, self.helper.open_kitty_with_prompt_and_watch_selected_event
            )

        def popover_is_closed(self, *_):
            self.stop_system_updates()

        def about(self):
            return "System Monitor Plugin for Waypanel."

        def code_explanation(self):
            return "Uses GtkListView, Gio.ListStore, and GObject bindings for efficient, flicker-free system monitoring."

    return SystemMonitorPlugin
