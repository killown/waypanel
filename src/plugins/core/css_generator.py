ENABLE_PLUGIN = True
DEPS = []


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        css_generator = call_plugin_class()
        return css_generator(panel_instance)


def call_plugin_class():
    import os
    from pathlib import Path
    from src.plugins.core._base import BasePlugin

    RESOURCES_DIR = Path.home() / ".local/share/waypanel/resources"
    CONFIG_DIR = Path.home() / ".config/waypanel"
    OUTPUT_CSS_FILE_NAME = "styles.css"
    OUTPUT_CSS_PATH = CONFIG_DIR / OUTPUT_CSS_FILE_NAME
    DEFAULT_THEME = "macos-dark"

    class CSSGeneratorPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)

        def on_start(self):
            self.generate_styles_css()
            self.theme = None

        def _get_current_theme(self):
            theme = self.get_config(["panel", "theme", "default"], DEFAULT_THEME)
            return theme

        def _get_css_files_to_import(self):
            theme_dir = RESOURCES_DIR / "themes/css"
            plugin_dir = RESOURCES_DIR / "plugins/css"
            files_to_import = []
            self.theme = self._get_current_theme()
            theme_file = f"{self.theme}.css"
            theme_path = theme_dir / theme_file
            files_to_import.append((theme_path, "1"))
            base_path = plugin_dir / "base.css"
            if base_path.exists():
                files_to_import.append((base_path, "2"))
            all_plugin_files = sorted(plugin_dir.glob("*.css"))
            for fpath in all_plugin_files:
                if fpath.name not in ["base.css", theme_file]:
                    files_to_import.append((fpath, "3"))
            return files_to_import

        def build_imports(self):
            lines = []
            for fullpath, _ in self._get_css_files_to_import():
                if not fullpath.exists():
                    self.logger.warning(
                        f"CSS Generator: Missing required CSS file: {fullpath}"
                    )
                    continue
                relative_to_config = os.path.relpath(fullpath, CONFIG_DIR)
                import_path = str(relative_to_config)
                lines.append(f'@import url("{import_path}");')
            return "\n".join(lines)

        def generate_styles_css(self):
            self.logger.debug("Forcing unconditional regeneration of styles.css...")
            css_content = self.build_imports()
            try:
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                OUTPUT_CSS_PATH.write_text(css_content, encoding="utf-8")
                self.logger.debug(
                    f"styles.css generated successfully for theme '{self.theme}'."
                )
            except Exception as e:
                self.logger.error(f"CSS Generator: Failed to write styles.css: {e}")

        def about(self):
            return "CSS Generator Plugin for Waypanel • Automatically generates and **unconditionally overwrites** the main styles.css file in ~/.config/waypanel/ on every panel start."

        def code_explanation(self):
            return "The core logic is implemented in the `generate_styles_css` method. It is called every time the panel starts, and the line `OUTPUT_CSS_PATH.write_text(css_content, encoding='utf-8')` ensures the existing `styles.css` file is truncated and **overwritten** with the new `@import` statements, regardless of its previous content."

    return CSSGeneratorPlugin
