def get_plugin_metadata(_):
    """
    Returns the metadata for the CSS Generator plugin.
    """
    return {
        "id": "org.waypanel.plugin.css_generator",
        "name": "Css Generator",
        "version": "1.0.0",
        "enabled": True,
        "deps": ["event_manager"],
    }


def get_plugin_class():
    """
    Returns the CSSGeneratorPlugin class with deferred imports.
    """
    import os
    import sys
    import inspect
    import re
    from pathlib import Path
    from src.plugins.core._base import BasePlugin

    DEFAULT_THEME = "os-dark"
    OUTPUT_CSS_FILE_NAME = "styles.css"

    class CSSGeneratorPlugin(BasePlugin):
        """
        Plugin to automatically generate and update styles.css.
        Parses existing styles.css to maintain registry state across restarts
        and prevent icon/UI flickering.
        """

        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.config_dir = self.path_handler.get_config_dir()
            self.output_css_path = self.config_dir / OUTPUT_CSS_FILE_NAME
            self.theme = None
            self.manual_css_registry = {}
            self._load_existing_registry()

        def on_start(self):
            self.generate_styles_css()

        def _load_existing_registry(self):
            """
            Parses styles.css on init to populate manual_css_registry with external paths.
            Prevents unnecessary regenerations if plugins call install_css on startup.
            """
            if not self.output_css_path.exists():
                return

            try:
                content = self.output_css_path.read_text(encoding="utf-8")
                # Pattern to extract paths from @import url("path");
                imports = re.findall(r'@import\s+url\("([^"]+)"\);', content)

                for imp_path in imports:
                    # Convert relative import path back to absolute path
                    abs_path = (self.config_dir / imp_path).resolve()

                    # We only care about paths that look like external plugin 'main.css'
                    if abs_path.name == "main.css" and abs_path.exists():
                        self.manual_css_registry[str(abs_path)] = abs_path

                self.logger.info(
                    f"CSS Generator: Loaded {len(self.manual_css_registry)} external paths from styles.css"
                )
            except Exception as e:
                self.logger.error(
                    f"CSS Generator: Failed to parse existing styles.css: {e}"
                )

        def install_css(self, css_filename: str):
            """
            API for external plugins to register a CSS file.
            Validation logic ensures no redundant writes if the path is already known.
            """
            try:
                frame = inspect.stack()[1]
                caller_module = inspect.getmodule(frame[0])

                if not caller_module or not hasattr(caller_module, "__file__"):
                    return

                caller_dir = Path(caller_module.__file__).parent
                css_path = (caller_dir / css_filename).resolve()
                css_key = str(css_path)

                if css_key in self.manual_css_registry:
                    return

                if css_path.exists():
                    self.logger.info(
                        f"CSS Generator: Installing new CSS from {css_path}"
                    )
                    self.manual_css_registry[css_key] = css_path
                    self.generate_styles_css()
                else:
                    self.logger.error(f"CSS Generator: File not found: {css_path}")
            except Exception as e:
                self.logger.error(f"CSS Generator: install_css failed: {e}")

        def _get_current_theme(self):
            return self._config_handler.get_root_setting(
                ["org.waypanel.panel", "theme", "default"], DEFAULT_THEME
            )

        def _get_css_files_to_import(self):
            files_to_import = []
            self.theme = self._get_current_theme()
            theme_file = f"{self.theme}.css"

            theme_path_str = self.path_handler.get_data_path(
                "resources/themes/css", theme_file
            )
            files_to_import.append(Path(theme_path_str))

            base_path_str = self.path_handler.get_data_path(
                "resources/plugins/css", "base.css"
            )
            base_path = Path(base_path_str)
            if base_path.exists():
                files_to_import.append(base_path)

            plugin_dir_str = self.path_handler.get_data_path("resources/plugins/css")
            plugin_dir = Path(plugin_dir_str)
            if plugin_dir.exists():
                for fpath in sorted(plugin_dir.glob("*.css")):
                    if fpath.name not in ["base.css", theme_file]:
                        files_to_import.append(fpath)

            for css_path in self.manual_css_registry.values():
                files_to_import.append(css_path)

            return files_to_import

        def build_imports(self):
            lines = []
            seen_paths = set()
            for fullpath in self._get_css_files_to_import():
                if not fullpath.exists() or fullpath in seen_paths:
                    continue

                relative_to_config = os.path.relpath(fullpath, self.config_dir)
                lines.append(f'@import url("{relative_to_config}");')
                seen_paths.add(fullpath)
            return "\n".join(lines)

        def generate_styles_css(self):
            css_content = self.build_imports()
            try:
                if self.output_css_path.exists():
                    if self.output_css_path.read_text(encoding="utf-8") == css_content:
                        return

                self.output_css_path.write_text(css_content, encoding="utf-8")
                self.logger.info("CSS Generator: styles.css updated.")
            except Exception as e:
                self.logger.error(f"CSS Generator: Write failed: {e}")

        def code_explanation(self):
            return "CSS Generator Plugin for Waypanel • Parses styles.css to maintain state and minimize reloads."

    return CSSGeneratorPlugin
