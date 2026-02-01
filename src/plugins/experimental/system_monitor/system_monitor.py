def get_plugin_metadata(_):
    """
    Returns metadata for the System Monitor plugin.

    Args:
        _: Reserved for future use by the plugin loader.

    Returns:
        dict: Plugin configuration and description metadata.
    """
    about = """
    Comprehensive system and application resource monitor.
    Features themed section-based layout with CPU, GPU, RAM, Network, Wayfire, and Storage.
    """
    return {
        "id": "org.waypanel.plugin.system_monitor",
        "name": "System Monitor",
        "version": "3.5.5",
        "enabled": True,
        "index": 9,
        "priority": 930,
        "container": "top-panel-systray",
        "deps": ["gestures_setup", "css_generator"],
        "description": about,
    }


def get_plugin_class():
    """
    Returns the SystemMonitorPlugin class with stable UI updates to prevent blinking.

    Returns:
        type: The SystemMonitorPlugin class.
    """
    import subprocess
    import psutil
    import gi

    gi.require_version("Gio", "2.0")
    gi.require_version("Gtk", "4.0")
    from gi.repository import GObject, Gtk, Gio
    from ._system_monitor_helper import SystemMonitorHelpers
    from src.plugins.core._base import BasePlugin

    class ProperMetricItem(GObject.Object):
        """
        GObject-based data model for system metrics with property notification.
        """

        def __init__(
            self, name: str, value: str, tooltip: str = "", visible: bool = True
        ):
            super().__init__()
            self._name = name
            self._value = value
            self._tooltip = tooltip
            self._visible = visible
            self._is_critical = False

        @GObject.Property(type=str)
        def name(self) -> str:
            return self._name

        @name.setter
        def name(self, value: str):
            self._name = value
            self.notify("name")

        @GObject.Property(type=str)
        def value(self) -> str:
            return self._value

        @value.setter
        def value(self, new_value: str):
            if self._value != new_value:
                self._value = new_value
                self.notify("value")

        @GObject.Property(type=str)
        def tooltip(self) -> str:
            return self._tooltip

        @tooltip.setter
        def tooltip(self, value: str):
            self._tooltip = value
            self.notify("tooltip")

        @GObject.Property(type=bool, default=True)
        def visible(self) -> bool:
            return self._visible

        @visible.setter
        def visible(self, value: bool):
            if self._visible != value:
                self._visible = value
                self.notify("visible")

        @GObject.Property(type=bool, default=False)
        def is_critical(self) -> bool:
            return self._is_critical

        @is_critical.setter
        def is_critical(self, value: bool):
            if self._is_critical != value:
                self._is_critical = value
                self.notify("is-critical")

    class SystemMonitorPlugin(BasePlugin):
        """
        Plugin class managing hardware stats and process tracking in a sectioned layout.
        Uses visibility bindings to prevent UI flicker during list updates.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover_system = None
            self.update_timeout_id = None
            self.helper = SystemMonitorHelpers(panel_instance)
            self.list_stores = {}
            self.metric_items = {}
            self.disk_labels = {}
            self.updated_keys = set()
            self.sections = {
                "CPU": "cpu-symbolic",
                "RAM": "memory-symbolic",
                "GPU": "video-display-symbolic",
                "Wayfire": "applications-system-symbolic",
                "Network": "network-workgroup-symbolic",
            }
            if psutil.sensors_battery():
                self.sections["Battery"] = "battery-full-symbolic"

            self.create_gesture = self.plugins["gestures_setup"].create_gesture

            # Define icons BEFORE creating the UI
            self.main_icon = self.get_plugin_setting_add_hint(
                ["main_icon"],
                "system-monitor-app-symbolic",
                "The default icon name for the system monitor plugin.",
            )

            self.fallback_main_icons = self.get_plugin_setting_add_hint(
                ["fallback_main_icons"],
                [
                    "utilities-system-monitor-symbolic",
                    "com.github.stsdc.monitor-symbolic",
                    "org.gnome.Settings-device-diagnostics-symbolic",
                ],
                "A prioritized list of fallback icons to use if the main icon is not found.",
            )

            # Now safe to create the UI
            self.create_menu_popover_system()
            self.plugins["css_generator"].install_css("system-monitor.css")

        def create_menu_popover_system(self):
            """
            Initializes the tray button and icon.
            """
            self.menubutton_system = Gtk.Button()
            self.menubutton_system.add_css_class("system-monitor-menubutton")

            # self.main_icon is now defined
            actual_icon = self.gtk_helper.icon_exist(
                self.main_icon, self.fallback_main_icons
            )
            self.menubutton_system.set_child(Gtk.Image.new_from_icon_name(actual_icon))

            self.menubutton_system.connect("clicked", self.open_popover_system)
            self.gtk_helper.add_cursor_effect(self.menubutton_system)
            self.main_widget = (self.menubutton_system, "append")

        def _set_margins(self, widget: Gtk.Widget, value: int):
            """
            Manual application of margins for GTK4.
            """
            widget.set_margin_top(value)
            widget.set_margin_bottom(value)
            widget.set_margin_start(value)
            widget.set_margin_end(value)

        def start_system_updates(self):
            """
            Starts polling GLib sources.
            """
            self.glib.timeout_add(1000, self.fetch_and_update_system_data)
            self.update_timeout_id = self.glib.timeout_add_seconds(
                self.helper.update_interval, self.fetch_and_update_system_data
            )

        def stop_system_updates(self):
            """
            Cleans up polling sources.
            """
            if self.update_timeout_id:
                try:
                    self.glib.source_remove(self.update_timeout_id)
                except Exception:
                    pass
                self.update_timeout_id = None

        def update_metric(
            self,
            section: str,
            name: str,
            value: str,
            tooltip: str | None = None,
            is_visible: bool = True,
            is_critical: bool = False,
        ):
            """
            Updates the specific section store and tracks the key for pruning.
            """
            if self.popover_system is None:
                return
            key = f"{section}:{name}"
            if is_visible:
                self.updated_keys.add(key)
                if key in self.metric_items:
                    item = self.metric_items[key]
                    item.value = str(value)
                    item.visible = True
                    item.is_critical = is_critical
                    if tooltip is not None:
                        item.tooltip = tooltip
                else:
                    item = self.add_metric(section, name, value, tooltip)
                    if item:
                        item.is_critical = is_critical
            else:
                self.remove_metric(section, name)

        def remove_metric(self, section: str, name: str):
            """
            Hides an item instead of removing it from the store to prevent layout blinking.
            """
            key = f"{section}:{name}"
            if key in self.metric_items:
                self.metric_items[key].visible = False

        def add_metric(
            self, section: str, name: str, value: str, tooltip: str | None = None
        ):
            """
            Appends a new metric item to the relevant section store.
            """
            if section not in self.list_stores:
                return None
            key = f"{section}:{name}"
            item = ProperMetricItem(name, str(value), tooltip or "")
            self.list_stores[section].append(item)
            self.metric_items[key] = item
            return item

        def _hw_prettifier(self, driver: str) -> str:
            """
            Maps sensor driver strings to hardware names dynamically.
            """
            mapping = {
                "k10temp": "AMD CPU",
                "coretemp": "Intel CPU",
                "amdgpu": "Radeon GPU",
                "nvme": "SSD Storage",
                "mt7921_phy0": "WiFi",
                "iwlwifi_1": "WiFi",
                "acpitz": "Thermal Zone",
                "pch_cannonlake": "PCH",
            }
            if driver in mapping:
                return mapping[driver]
            return driver.replace("_", " ").title()

        def add_gpu(self):
            """
            Handles multi-vendor GPU status polling synchronously.
            """
            try:
                nv = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                p = nv.stdout.strip().split(",")
                self.update_metric("GPU", "Vendor", f"NVIDIA {p[0].strip()}")
                self.update_metric("GPU", "Load", f"{p[1].strip()}%")
                self.update_metric("GPU", "VRAM", f"{p[2].strip()} / {p[3].strip()} MB")
            except Exception:
                pass
            try:
                import pyamdgpuinfo

                if pyamdgpuinfo.detect_gpus():
                    gpu = pyamdgpuinfo.get_gpu(0)
                    total = gpu.memory_info["vram_size"] / (1024**3)
                    used = gpu.query_vram_usage() / (1024**3)
                    self.update_metric("GPU", "Vendor", gpu.name)
                    self.update_metric("GPU", "Load", f"{gpu.query_load():.1f}%")
                    self.update_metric("GPU", "VRAM", f"{used:.1f} / {total:.1f} GB")
            except Exception:
                pass

        def _poll_sensors(self):
            """
            Polls thermals and routes them correctly based on hardware patterns.
            """
            try:
                temps = psutil.sensors_temperatures()
                if not temps:
                    return
                for driver, entries in temps.items():
                    if not entries:
                        continue
                    vendor = self._hw_prettifier(driver)
                    current_temp = entries[0].current
                    critical_temp = entries[0].critical or 85
                    val = f"{current_temp}°C"
                    is_danger = current_temp >= critical_temp
                    if "nvme" in driver or "Storage" in vendor:
                        self.update_metric(
                            "Storage", f"{vendor} Temp", val, is_critical=is_danger
                        )
                    elif any(x in driver for x in ["wifi", "mt7921", "iwl"]):
                        self.update_metric(
                            "Network", "WiFi Temp", val, is_critical=is_danger
                        )
                    elif "gpu" in driver.lower() or "radeon" in vendor.lower():
                        self.update_metric(
                            "GPU", f"{vendor} Temp", val, is_critical=is_danger
                        )
                    else:
                        self.update_metric(
                            "CPU", f"{vendor} Temp", val, is_critical=is_danger
                        )
            except Exception:
                pass

        def fetch_and_update_system_data(self):
            """
            Updates all monitor sections and prunes keys using visibility to avoid flickering.
            """
            self.updated_keys.clear()
            self.update_metric("CPU", "Usage", f"{self.helper.get_cpu_usage()}%")
            self.update_metric("RAM", "Usage", self.helper.get_ram_info())
            self.update_metric("Network", "Usage", self.helper.get_network_usage())
            if "Battery" in self.sections:
                batt = self.helper.get_battery_status()
                self.update_metric(
                    "Battery", "Status", batt or "N/A", is_visible=batt is not None
                )
            self.add_gpu()
            self._poll_sensors()
            disks = self.helper.get_disk_usages()
            for u in disks:
                self.update_metric(
                    "Storage", u["mountpoint"], f"{u['used']:.1f} / {u['total']:.0f}GB"
                )
            fid = self._wf_helper.get_the_last_focused_view_id()
            view = self.ipc.get_view(fid)
            if view:
                p = view["pid"]
                p_usage = self.helper.get_process_usage(p)
                p_disk = self.helper.get_process_disk_usage(p)
                self.update_metric(
                    "Wayfire", "APP ID", f"({view['app-id']}): {view['id']}"
                )
                self.update_metric(
                    "Wayfire", "Exec", self.helper.get_process_executable(p)
                )
                self.update_metric(
                    "Wayfire",
                    "APP PID",
                    p,
                    tooltip="Left: htop | Middle: Monitor | Right: Kill",
                )
                if p_usage:
                    self.update_metric("Wayfire", "APP Memory", p_usage["memory_usage"])
                if p_disk:
                    self.update_metric(
                        "Wayfire",
                        "Disk Usage",
                        f"<b>I/O:</b> R:{p_disk['read_bytes']} | W:{p_disk['write_bytes']}",
                    )
                self.update_metric(
                    "Wayfire", "Watch events", "L_CLICK all or R_CLICK selected"
                )
            for full_key, item in self.metric_items.items():
                if full_key not in self.updated_keys:
                    if "Wayfire" in full_key:
                        continue
                    item.visible = False
            return self.popover_system and self.popover_system.is_visible()

        def open_popover_system(self, *_):
            """
            Toggles popover visibility and starts updates.
            """
            if self.popover_system and self.popover_system.is_visible():
                self.popover_system.popdown()
            else:
                if not self.popover_system:
                    self.create_popover_system()
                self.popover_system.popup()
                self.start_system_updates()

        def create_popover_system(self):
            """
            Builds section-based layout with a default-hidden Storage expander.
            """
            self.popover_system = Gtk.Popover.new()
            self.popover_system.add_css_class("system-monitor-popover")
            self.popover_system.connect("closed", lambda *_: self.stop_system_updates())
            root_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, spacing=15)
            root_vbox.add_css_class("system-monitor-vbox")
            self._set_margins(root_vbox, 15)
            for name, icon in self.sections.items():
                self._build_section(name, icon, root_vbox)
            storage_exp = Gtk.Expander.new("Storage & Disks")
            storage_exp.set_expanded(False)
            storage_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, spacing=5)
            self._set_margins(storage_vbox, 10)
            store = Gio.ListStore.new(ProperMetricItem)
            self.list_stores["Storage"] = store
            lv = Gtk.ListView.new(Gtk.SingleSelection.new(store), self._get_factory())
            lv.add_css_class("system-monitor-listview")
            storage_vbox.append(lv)
            storage_exp.set_child(storage_vbox)
            root_vbox.append(storage_exp)
            self.popover_system.set_child(root_vbox)
            self.popover_system.set_parent(self.menubutton_system)

        def _build_section(self, name, icon, container):
            """
            Constructs a themed section frame with a stable ListView.
            """
            frame = Gtk.Frame()
            vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, spacing=5)
            self._set_margins(vbox, 10)
            icon = self.gtk_helper.icon_exist(icon)
            header = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=10)
            header.append(Gtk.Image.new_from_icon_name(icon))
            lbl = Gtk.Label()
            lbl.set_markup(f"<b>{name}</b>")
            header.append(lbl)
            vbox.append(header)
            vbox.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))
            store = Gio.ListStore.new(ProperMetricItem)
            self.list_stores[name] = store
            lv = Gtk.ListView.new(Gtk.SingleSelection.new(store), self._get_factory())
            lv.add_css_class("system-monitor-listview")
            vbox.append(lv)
            if name == "Wayfire":
                self.app_io_label = Gtk.Label(halign=Gtk.Align.START, xalign=0.0)
                vbox.append(self.app_io_label)
            frame.set_child(vbox)
            container.append(frame)

        def _get_factory(self):
            """
            Returns a configured SignalListItemFactory.
            """
            f = Gtk.SignalListItemFactory()
            f.connect("setup", self._factory_setup)
            f.connect("bind", self._factory_bind)
            return f

        def _factory_setup(self, f, li):
            """
            Row layout helper with visibility containers.
            """
            hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, spacing=20)
            hbox.add_css_class("system-monitor-listitem")
            n = Gtk.Label(halign=Gtk.Align.START, hexpand=True, xalign=0.0)
            n.add_css_class("system-monitor-name-label")
            v = Gtk.Label(halign=Gtk.Align.END, xalign=1.0)
            v.add_css_class("system-monitor-value-label")
            v.set_use_markup(True)
            hbox.append(n)
            hbox.append(v)
            li.set_child(hbox)
            li._n, li._v, li._h = n, v, hbox

        def _factory_bind(self, f, li):
            """
            Property binding and gesture assignment.
            """
            item = li.get_item()
            h = li._h
            li._n.set_markup(f"{item.name}:")
            item.bind_property(
                "value", li._v, "label", GObject.BindingFlags.SYNC_CREATE
            )
            item.bind_property(
                "tooltip", h, "tooltip-text", GObject.BindingFlags.SYNC_CREATE
            )
            item.bind_property(
                "visible", h, "visible", GObject.BindingFlags.SYNC_CREATE
            )

            def on_critical_notified(obj, pspec):
                if obj.is_critical:
                    li._v.add_css_class("critical-alert")
                else:
                    li._v.remove_css_class("critical-alert")

            item.connect("notify::is-critical", on_critical_notified)
            on_critical_notified(item, None)

            nm = item.name
            if nm == "APP PID":
                self.create_gesture(
                    h, 1, lambda _: self.helper.open_terminal_with_htop(item.value)
                )
                self.create_gesture(h, 2, lambda _: self.helper.open_system_monitor())
                self.create_gesture(
                    h, 3, lambda _: self.helper.kill_process(item.value)
                )
            elif nm == "Usage" and "CPU" in li._n.get_text():
                self.create_gesture(
                    h, 1, lambda _: self.run_cmd("gnome-system-monitor")
                )
            elif nm == "Watch events":
                self.create_gesture(h, 1, self.helper.open_kitty_with_rich_events_view)
                self.create_gesture(
                    h, 3, self.helper.open_kitty_with_prompt_and_watch_selected_event
                )
            elif nm == "APP ID":
                self.create_gesture(
                    h,
                    1,
                    lambda _: self.helper.open_kitty_with_ipython_view(
                        self.ipc.get_view(
                            self._wf_helper.get_the_last_focused_view_id()
                        )
                    ),
                )
            elif nm in ["Load", "VRAM", "Vendor"]:
                self.create_gesture(h, 1, self.helper.open_terminal_with_amdgpu_top)

    return SystemMonitorPlugin
