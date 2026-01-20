def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.css_generator",
        "name": "Css Generator",
        "version": "1.1.0",
        "enabled": True,
        "deps": ["event_manager"],
    }


def get_plugin_class():
    import inspect
    import re
    from pathlib import Path
    from src.plugins.core._base import BasePlugin

    DEFAULT_THEME = "os-dark"
    OUTPUT_CSS_FILE_NAME = "styles.css"

    class CSSGeneratorPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.config_dir = self.path_handler.get_config_dir()
            self.output_css_path = self.config_dir / OUTPUT_CSS_FILE_NAME
            self.manual_css_registry = {}
            self._debounce_id = 0
            self._import_regex = re.compile(r'@import\s+url\("([^"]+)"\);')
            self._load_existing_registry()

        def on_start(self):
            self.generate_styles_css()

        def _load_existing_registry(self):
            if not self.output_css_path.exists():
                return
            try:
                content = self.output_css_path.read_text(encoding="utf-8")
                if not content:
                    return
                for match in self._import_regex.finditer(content):
                    imp_path = match.group(1)
                    if "main.css" in imp_path:
                        abs_path = (self.config_dir / imp_path).resolve()
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
                caller_dir = Path(module.__file__).parent
                css_path = (caller_dir / css_filename).resolve()
                css_key = str(css_path)
                if css_key in self.manual_css_registry:
                    return
                if css_path.exists():
                    self.manual_css_registry[css_key] = css_path
                    self._schedule_generation()
                else:
                    self.logger.error(f"Target missing: {css_path}")
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
            theme = self._config_handler.get_root_setting(
                ["org.waypanel.panel", "theme", "default"], DEFAULT_THEME
            )
            theme_file = f"{theme}.css"
            theme_path = Path(
                self.path_handler.get_data_path("resources/themes/css", theme_file)
            )
            if theme_path.exists():
                yield theme_path
            base_path = Path(
                self.path_handler.get_data_path("resources/plugins/css", "base.css")
            )
            if base_path.exists():
                yield base_path
            plugin_dir = Path(self.path_handler.get_data_path("resources/plugins/css"))
            if plugin_dir.exists():
                for fpath in sorted(plugin_dir.glob("*.css")):
                    if fpath.name not in ("base.css", theme_file):
                        yield fpath
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

        def generate_styles_css(self):
            content = self.build_imports()
            try:
                if self.output_css_path.exists():
                    if self.output_css_path.read_text(encoding="utf-8") == content:
                        return
                self.output_css_path.write_text(content, encoding="utf-8")
            except Exception as e:
                self.logger.error(f"CSS Write Error: {e}")

    return CSSGeneratorPlugin
