import os
import argparse


def scrape_python_files(base_dir, output_file):
    """
    Scrapes Waypanel project files and organizes them into a structured format
    optimized for AI context windows.
    """

    ai_header = """
# WAYPANEL SYSTEM PROTOCOL (v2.0 - STRICT ENFORCEMENT)
Your primary task is to act as a Senior Python Developer for the Waypanel project. You are in "Strict Grounding" mode.

## MANDATORY CODING RULES
1. 🧪 **Deferred Imports**: STRICTLY PROHIBITED at top level. Move all imports inside `get_plugin_class()`.
2. 🔄 **Lifecycle Hooks**: Use `on_enable(self)`/`on_start(self)` for setup and `on_disable(self)` for cleanup. Never override `enable()`/`disable()`.
3. ❌ **No Inventions/Hallucinations**: Do not use "standard" GTK/Python patterns if a project-specific method exists in the provided files. If `src/plugins/examples/` shows a specific way to do something (e.g., loading CSS via `css_generator`), that is the ONLY correct way.
4. 📂 **Path Handling**: Use `self.path_handler` or the methods shown in examples. Never hardcode strings or use `os.path` unless the example does.

## FILE READING & VERIFICATION PROTOCOL
1. **Search Before Answering**: You must perform a text search for the specific file path or keywords (e.g., `example_css.py`) before generating any code.
2. **Example Priority**: The code blocks between `# ==== FILE: src/plugins/examples/... ====` are the absolute Source of Truth. If my previous "internal knowledge" contradicts these examples, the examples win 100% of the time.
3. **Boundary Recognition**: Treat `# ==== FILE: ... ====` and `# ==== END OF FILE: ... ====` as absolute boundaries. Use these markers to locate the exact logic requested.

## CRITICAL NEGATIVE CONSTRAINTS
- NEVER suggest a generic helper (like `self.load_css_file`) if the uploaded examples use a dependency-based method (like `self.plugins["css_generator"]`).
- NEVER assume you know the API. Verify the method names against the provided `.txt` source every single time.
"""

    def collect_files(base_dir):
        """
        Categorizes files into specific priority tiers.
        """
        examples = []  # PRIORITY #1: plugins/examples/*
        priority_docs = []  # PRIORITY #2: Root README, PLUGIN.md, Core definitions
        plugin_core = []  # PRIORITY #3: src/plugins/essential (Core Logic)
        project_source = []  # PRIORITY #4: All other source code

        # 1. DIRECTORY BLACKLIST
        #    Added 'ipc' and specific plugin subfolders.
        ignored_dirs = {
            "build",
            ".venv",
            "waypanel.egg-info",
            "__pycache__",
            ".git",
            ".github",
            "stage",
            "tests",
            "assets",
            "locales",
            "resources",
            "docs",
            "man",
            "experimental",
            "fixes",
            "utils",
            "rules",
            "tools",
            "extra",
            "ipc",
            "sync_plugins",  # <-- NEW EXCLUSIONS
        }

        # 2. FILE BLACKLIST
        ignored_files = {
            "CONTRIBUTING.md",
            "requirements.txt",
            "LICENSE",
            "Makefile",
            "CODE_OF_CONDUCT.md",
            "flatpak.json",
            "manifest.yaml",
            "Dockerfile",
            "install_helpers.py",
            "run.py",  # <-- NEW EXCLUSIONS (Installation/Startup scripts)
        }

        for root, dirs, files in os.walk(base_dir):
            # Prune directories in-place
            dirs[:] = [d for d in dirs if d not in ignored_dirs]

            for file in files:
                # 3. EXTENSION FILTER
                if not file.endswith((".py", ".md", ".txt")):
                    continue

                if file in ignored_files:
                    continue

                # 4. EMPTY/INIT FILE FILTER
                file_path = os.path.join(root, file)
                if file == "__init__.py" and os.path.getsize(file_path) < 50:
                    continue

                rel_path = os.path.relpath(file_path, base_dir)

                # 5. NESTED README FILTER
                if file.lower() == "readme.md" and os.path.dirname(rel_path) != ".":
                    continue

                # 6. PRIVATE IMPLEMENTATION FILTER
                is_plugin_folder = (
                    "src/plugins" in rel_path and "src/plugins/core" not in rel_path
                )
                if is_plugin_folder and file.startswith("_") and file != "__init__.py":
                    continue

                # --- CLASSIFICATION LOGIC ---

                if "plugins/examples" in rel_path:
                    examples.append((file_path, rel_path))

                elif (
                    file.lower() in ("readme.md", "plugin.md", "base_plugin.py")
                    or "src/core" in rel_path
                    or "src/plugins/core/_base.py" in rel_path
                ):
                    priority_docs.append((file_path, rel_path))

                elif "plugins" in rel_path:
                    plugin_core.append((file_path, rel_path))

                else:
                    project_source.append((file_path, rel_path))

        return examples, priority_docs, plugin_core, project_source

    def write_files(file_list, out_f, section_label):
        if not file_list:
            return
        out_f.write(
            f"\n\n# =========================================================\n"
        )
        out_f.write(f"# ==== SECTION: {section_label} ====\n")
        out_f.write(f"# =========================================================\n")
        for file_path, rel_path in file_list:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                out_f.write(f"\n# ==== FILE: {rel_path} ====\n")
                out_f.write(content)
                out_f.write(f"\n# ==== END OF FILE: {rel_path} ====\n")
                print(f"Processed: {rel_path}")
            except Exception as e:
                print(f"Error processing {rel_path}: {e}")

    with open(output_file, "w", encoding="utf-8") as out_f:
        out_f.write(ai_header)

        examples, docs, plugins, source = collect_files(base_dir)

        write_files(examples, out_f, "PRIORITY #1: IMPLEMENTATION EXAMPLES")
        write_files(docs, out_f, "CORE PROTOCOL & BASE CLASSES")
        write_files(plugins, out_f, "WAYPANEL PLUGIN CORE")
        write_files(source, out_f, "GENERAL SOURCE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Waypanel Context Scraper (Diamond Cut AI Optimized)"
    )
    parser.add_argument("--input", default=".", help="Root directory")
    parser.add_argument("--output", default="waypanel.txt", help="Output file")

    args = parser.parse_args()

    if os.path.isdir(args.input):
        scrape_python_files(args.input, args.output)
        print(
            f"\nContext generated at {args.output} with MAXIMUM efficiency (No IPC/Sync/Helpers)."
        )
    else:
        print(f"Error: {args.input} is not a directory.")
