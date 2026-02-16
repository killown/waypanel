def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.css_generator",
        "name": "Css Generator",
        "version": "1.5.5",
        "enabled": True,
        "priority": 11111,
        "deps": ["event_manager"],
    }


def get_plugin_class():
    import inspect
    import re
    import hashlib
    from pathlib import Path
    from gi.repository import Gio
    from src.plugins.core._base import BasePlugin

    DEFAULT_THEME = "adwaita"
    OUTPUT_CSS_FILE_NAME = "styles.css"
    MY_ID = "org.waypanel.plugin.css_generator"
    # Identify themes by the standard resource path pattern
    THEME_INDICATOR = "resources/themes/css/"

    class CSSGeneratorPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.config_dir = self.path_handler.get_config_dir()
            self.output_css_path = self.config_dir / OUTPUT_CSS_FILE_NAME
            self.custom_css_path = self.config_dir / "custom.css"
            self.manual_css_registry = {}
            self.monitors = {}
            self._debounce_id = 0
            self._last_content_hash = None
            self._import_regex = re.compile(r'@import\s+url\("([^"]+)"\);')

        def on_start(self):
            # 1. First, sync the registry to remove only non-matching themes
            self._sync_registry_on_start()

            # 2. Watch custom.css if it exists
            if self.custom_css_path.exists():
                self._register_and_monitor(self.custom_css_path)

            # 3. Register font settings
            self.get_plugin_setting_add_hint(
                "font_family",
                [
                    "Oxanium",
                    "Tektur",
                    "Geist Mono",
                    "Google Sans Code",
                    "Orbitron",
                    "MesloLGS Nerd Font Mono",
                    "Motiva Sans",
                    "Inter",
                    "Segoe UI",
                    "monospace",
                ],
                "The primary font stack for the panel",
            )
            self.generate_styles_css(is_startup=True)
            self.log_monitored_files()

        def on_disable(self):
            for monitor in self.monitors.values():
                monitor.cancel()
            self.monitors.clear()

        def _sync_registry_on_start(self):
            """Removes themes that don't match config from registry before generation."""
            if not self.output_css_path.exists():
                return

            current_theme = self._config_handler.get_root_setting(
                ["org.waypanel.panel", "theme", "default"], DEFAULT_THEME
            )

            try:
                content = self.output_css_path.read_text(encoding="utf-8")
                # Clear existing logic-state to rebuild correctly
                self.manual_css_registry.clear()

                for match in self._import_regex.finditer(content):
                    rel_path_str = match.group(1)

                    # If the path is a theme resource
                    if THEME_INDICATOR in rel_path_str:
                        # Extract the theme name (e.g., tokyo-night from path/tokyo-night.css)
                        theme_name = rel_path_str.split("/")[-1].replace(".css", "")

                        # Only re-register if it matches current config
                        if theme_name != current_theme:
                            self.logger.info(
                                f"Filtering out anterior theme: {theme_name}"
                            )
                            continue

                    abs_path = (self.config_dir / rel_path_str).resolve()
                    if abs_path.exists():
                        # Add back to registry but don't schedule generation yet
                        self._register_and_monitor(abs_path, schedule=False)
            except Exception as e:
                self.logger.error(f"Registry Sync Error: {e}")

        def log_monitored_files(self):
            if not self.monitors:
                self.logger.info("CSS Watcher: No files active.")
                return
            self.logger.info(f"CSS Watcher: Active on {len(self.monitors)} files.")
            for path_str in sorted(self.monitors.keys()):
                self.logger.info(f"  [WATCHING] {path_str}")

        def _register_and_monitor(self, path: Path, schedule=True):
            path_str = str(path)
            if path_str in self.monitors:
                return

            self.manual_css_registry[path_str] = path
            try:
                gio_file = Gio.File.new_for_path(path_str)
                monitor = gio_file.monitor_file(
                    Gio.FileMonitorFlags.WATCH_HARD_LINKS, None
                )
                monitor.connect("changed", self._on_source_css_changed)
                self.monitors[path_str] = monitor

                if schedule:
                    self._schedule_generation()
            except Exception as e:
                self.logger.error(f"Failed to watch {path_str}: {e}")

        def _on_source_css_changed(self, monitor, file, other_file, event_type):
            valid_events = [
                Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                Gio.FileMonitorEvent.CREATED,
            ]
            if event_type in valid_events:
                self.logger.info(f"Detected change in source: {file.get_path()}")
                self._last_content_hash = None
                self._schedule_generation()

        def install_css(self, css_filename: str):
            try:
                frame = inspect.stack()[1]
                module = inspect.getmodule(frame[0])
                if not module or not hasattr(module, "__file__"):
                    return
                caller_dir = Path(module.__file__).parent
                css_path = (caller_dir / css_filename).resolve()
                if css_path.exists():
                    self._register_and_monitor(css_path)
            except Exception as e:
                self.logger.error(f"install_css failed: {e}")

        def _schedule_generation(self):
            if self._debounce_id:
                self.glib.source_remove(self._debounce_id)
            self._debounce_id = self.glib.timeout_add(100, self._debounced_write)

        def _debounced_write(self):
            self.generate_styles_css()
            self._debounce_id = 0
            return False

        def _get_css_files_to_import(self):
            theme = self._config_handler.get_root_setting(
                ["org.waypanel.panel", "theme", "default"], DEFAULT_THEME
            )
            theme_path = Path(
                self.path_handler.get_data_path("resources/themes/css", f"{theme}.css")
            )
            if theme_path.exists():
                yield theme_path

            for p_id, p_obj in self.plugin_loader.plugins.items():
                if p_id == MY_ID:
                    continue
                try:
                    p_dir = Path(inspect.getfile(p_obj.__class__)).parent
                    short_id = p_id.split(".")[-1]
                    for name in [
                        f"{short_id}-{theme}.css",
                        f"{short_id}.css",
                        "style.css",
                    ]:
                        local_css = p_dir / name
                        if local_css.exists():
                            yield local_css
                            break
                except Exception as e:
                    self.logger.error(f"{e}")
                    continue

            for path in list(self.manual_css_registry.values()):
                if path != self.custom_css_path:
                    yield path

        def build_imports(self):
            lines = []
            seen = set()
            new_watch = False
            for fullpath in self._get_css_files_to_import():
                if fullpath in seen:
                    continue
                if str(fullpath) not in self.monitors:
                    self.glib.idle_add(self._register_and_monitor, fullpath, False)
                    new_watch = True

                rel = self.os.path.relpath(fullpath, self.config_dir)
                lines.append(f'@import url("{rel}");')
                seen.add(fullpath)

            if new_watch:
                self.glib.timeout_add(500, self.log_monitored_files)
            return "\n".join(lines)

        def _get_injected_base_css(self):
            font_list = self.get_plugin_setting(
                "font_family",
                [
                    "Oxanium",
                    "Tektur",
                    "Geist Mono",
                    "Google Sans Code",
                    "Orbitron",
                    "MesloLGS Nerd Font Mono",
                    "Motiva Sans",
                    "Inter",
                    "Segoe UI",
                    "monospace",
                ],
            )
            font_stack = ", ".join([f"'{f}'" if " " in f else f for f in font_list])

            return f"""/* INJECTED BASE CONFIGURATION */
:root {{
  --font-family-default: {font_stack};
}}

* {{
  font-family: var(--font-family-default);
  color: var(--main-text);
}}

popover.background {{
  background-color: transparent;
  border: none;
}}

popover.background > contents {{
  background-color: var(--primary-bg);
}}

popover.background > arrow {{
  background-color: var(--primary-bg);
}}

.box-widgets {{
  margin: -2px;
}}

.image-button {{
  -gtk-icon-size: 16px;
  color: var(--main-text);
  background-color: transparent;
}}

menubutton > button.toggle {{
  -gtk-icon-size: 16px;
}}

"""

        def generate_styles_css(self, is_startup=False):
            base_block = self._get_injected_base_css()
            import_block = self.build_imports()

            custom_import = ""
            if self.custom_css_path.exists():
                custom_import = f'\n@import url("custom.css");'

            content = base_block + import_block + custom_import
            new_hash = hashlib.md5(content.encode()).hexdigest()

            if new_hash == self._last_content_hash:
                return

            try:
                self.output_css_path.write_text(content, encoding="utf-8")
                self._last_content_hash = new_hash
                self.logger.info(
                    f"Styles.css regenerated using theme: {self._config_handler.get_root_setting(['org.waypanel.panel', 'theme', 'default'], DEFAULT_THEME)}"
                )
            except Exception as e:
                self.logger.error(f"CSS Write Error: {e}")

    return CSSGeneratorPlugin
