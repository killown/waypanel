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
    from pathlib import Path
    from src.plugins.core._base import BasePlugin

    DEFAULT_THEME = "os-dark"
    OUTPUT_CSS_FILE_NAME = "styles.css"

    class CSSGeneratorPlugin(BasePlugin):
        """
        Plugin to automatically generate and update styles.css based on the current theme.
        """

        def __init__(self, panel_instance):
            """
            Initializes the plugin using PathHandler for environment-aware paths.
            """
            super().__init__(panel_instance)
            self.config_dir = self.path_handler.get_config_dir()
            self.output_css_path = self.config_dir / OUTPUT_CSS_FILE_NAME
            self.theme = None

        def on_start(self):
            """
            Triggers CSS generation on plugin activation.
            """
            self.generate_styles_css()

        def _get_current_theme(self):
            """
            Retrieves the current theme from the configuration handler.
            """
            theme = self._config_handler.get_root_setting(
                ["org.waypanel.panel", "theme", "default"], DEFAULT_THEME
            )
            return theme

        def _get_css_files_to_import(self):
            """
            Resolves paths for the theme and plugin CSS files using PathHandler.
            """
            files_to_import = []
            self.theme = self._get_current_theme()
            theme_file = f"{self.theme}.css"

            # Resolve theme path
            theme_path_str = self.path_handler.get_data_path(
                "resources/themes/css", theme_file
            )
            theme_path = Path(theme_path_str)
            files_to_import.append((theme_path, "1"))

            # Resolve base plugin CSS
            base_path_str = self.path_handler.get_data_path(
                "resources/plugins/css", "base.css"
            )
            base_path = Path(base_path_str)
            if base_path.exists():
                files_to_import.append((base_path, "2"))

            # Resolve additional plugin CSS files
            plugin_dir_str = self.path_handler.get_data_path("resources/plugins/css")
            plugin_dir = Path(plugin_dir_str)

            if plugin_dir.exists():
                all_plugin_files = sorted(plugin_dir.glob("*.css"))
                for fpath in all_plugin_files:
                    if fpath.name not in ["base.css", theme_file]:
                        files_to_import.append((fpath, "3"))

            return files_to_import

        def build_imports(self):
            """
            Constructs the @import statements for the output CSS file.
            """
            lines = []
            for fullpath, _ in self._get_css_files_to_import():
                if not fullpath.exists():
                    self.logger.warning(
                        f"CSS Generator: Missing required CSS file: {fullpath}"
                    )
                    continue

                # Calculate relative path from ~/.config/waypanel/ to the resource
                relative_to_config = os.path.relpath(fullpath, self.config_dir)
                import_path = str(relative_to_config)
                lines.append(f'@import url("{import_path}");')
            return "\n".join(lines)

        def generate_styles_css(self):
            """
            Writes the generated @import statements to the styles.css file.
            """
            self.logger.debug("Regenerating styles.css via PathHandler...")
            css_content = self.build_imports()
            try:
                self.output_css_path.write_text(css_content, encoding="utf-8")
                self.logger.debug(
                    f"styles.css generated successfully for theme '{self.theme}'."
                )
            except Exception as e:
                self.logger.error(f"CSS Generator: Failed to write styles.css: {e}")

        def code_explanation(self):
            return "CSS Generator Plugin for Waypanel • Automatically generates and overwrites styles.css using system-aware paths."

    return CSSGeneratorPlugin
