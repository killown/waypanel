def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.css_generator",
        "name": "Css Generator",
        "version": "1.4.0",
        "enabled": True,
        "priority": 11111,
        "deps": ["event_manager"],
    }


def get_plugin_class():
    import inspect
    import re
    import hashlib
    from pathlib import Path
    from src.plugins.core._base import BasePlugin

    DEFAULT_THEME = "os-dark"
    OUTPUT_CSS_FILE_NAME = "styles.css"
    MY_ID = "org.waypanel.plugin.css_generator"

    class CSSGeneratorPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.config_dir = self.path_handler.get_config_dir()
            self.output_css_path = self.config_dir / OUTPUT_CSS_FILE_NAME
            self.manual_css_registry = {}
            self._debounce_id = 0
            self._last_content_hash = None
            self._import_regex = re.compile(r'@import\s+url\("([^"]+)"\);')

            plugin_file = Path(inspect.getfile(self.__class__))
            self.internal_base_css = (plugin_file.parent / "base.css").resolve()

            self._load_existing_registry()

        def on_start(self):
            self.generate_styles_css(is_startup=True)

        def _load_existing_registry(self):
            if not self.output_css_path.exists():
                return
            try:
                content = self.output_css_path.read_text(encoding="utf-8")
                if not content:
                    return
                self._last_content_hash = hashlib.md5(content.encode()).hexdigest()
                for match in self._import_regex.finditer(content):
                    rel_path_str = match.group(1)
                    abs_path = (self.config_dir / rel_path_str).resolve()
                    if abs_path.exists():
                        self.manual_css_registry[str(abs_path)] = abs_path
            except Exception as e:
                self.logger.error(f"CSS Registry Load Error: {e}")

        def install_css(self, css_filename: str):
            try:
                frame = inspect.stack()[1]
                module = inspect.getmodule(frame[0])
                if not module or not hasattr(module, "__file__"):
                    return
                caller_dir = Path(module.__file__).parent  # pyright: ignore
                css_path = (caller_dir / css_filename).resolve()
                css_key = str(css_path)
                if css_key in self.manual_css_registry:
                    return
                if css_path.exists():
                    self.manual_css_registry[css_key] = css_path
                    self._schedule_generation()
            except Exception as e:
                self.logger.error(f"install_css failed: {e}")

        def _schedule_generation(self):
            if self._debounce_id:
                self.glib.source_remove(self._debounce_id)
            self._debounce_id = self.glib.timeout_add(50, self._debounced_write)

        def _debounced_write(self):
            self.generate_styles_css()
            self._debounce_id = 0
            return False

        def _get_css_files_to_import(self):
            """
            Aggregates CSS with theme-specific override support.
            Hierarchy: Theme -> Base -> Plugin Theme Override -> Plugin Default -> Manual
            """
            current_theme = self._config_handler.get_root_setting(
                ["org.waypanel.panel", "theme", "default"], DEFAULT_THEME
            )
            theme_file = f"{current_theme}.css"

            # System Theme (Variables/Colors)
            theme_path = Path(
                self.path_handler.get_data_path("resources/themes/css", theme_file)
            )
            if theme_path.exists():
                yield theme_path

            # Internal Base (Structural)
            if self.internal_base_css.exists():
                yield self.internal_base_css

            # Distributed Plugin Discovery with Theme Overrides
            for plugin_id, plugin_obj in self.plugin_loader.plugins.items():
                if plugin_id == MY_ID:
                    continue
                try:
                    plugin_dir = Path(inspect.getfile(plugin_obj.__class__)).parent
                    plugin_short_id = plugin_id.split(".")[-1]

                    # Search hierarchy for the plugin:
                    # 1. [plugin_id]-[theme].css (e.g., clock-os-light.css)
                    # 2. [plugin_id].css (e.g., clock.css)
                    # 3. style.css (generic fallback)
                    potential_names = [
                        f"{plugin_short_id}-{current_theme}.css",
                        f"{plugin_short_id}.css",
                        "style.css",
                    ]

                    for name in potential_names:
                        local_css = plugin_dir / name
                        if local_css.exists():
                            yield local_css
                            break
                except Exception:
                    continue

            # Manual Registry
            for path in self.manual_css_registry.values():
                yield path

        def build_imports(self):
            lines = []
            seen = set()
            for fullpath in self._get_css_files_to_import():
                if fullpath in seen:
                    continue
                rel = self.os.path.relpath(fullpath, self.config_dir)
                lines.append(f'@import url("{rel}");')
                seen.add(fullpath)
            return "\n".join(lines)

        def generate_styles_css(self, is_startup=False):
            content = self.build_imports()
            new_hash = hashlib.md5(content.encode()).hexdigest()

            if new_hash == self._last_content_hash:
                return

            try:
                self.output_css_path.write_text(content, encoding="utf-8")
                self._last_content_hash = new_hash
                self.logger.info(f"Styles.css updated with theme override support.")
            except Exception as e:
                self.logger.error(f"CSS Write Error: {e}")

    return CSSGeneratorPlugin
