import os
import argparse


def scrape_python_files(base_dir, output_file):
    """
    Scrapes Waypanel project files and organizes them into a structured format
    optimized for AI context windows.

    PRIORITY #1: plugins/examples/ is placed at the absolute top of the
    file to ensure the AI anchors to correct patterns immediately.
    """

    ai_header = """
# WAYPANEL SYSTEM PROTOCOL
Your primary task is to act as a Senior Python Developer for the Waypanel project. 

## MANDATORY CODING RULES
1. 🧪 **Deferred Imports**: You are STRICTLY PROHIBITED from importing library modules (Gtk, Gdk, GLib, etc.) or project modules (BasePlugin) at the top level. 
2. 🛠️ **Plugin Entry**: All imports MUST be placed inside the `get_plugin_class()` function.
3. 🔄 **Lifecycle Hooks**: Always use `on_enable(self)` for startup and `on_disable(self)` for cleanup. Do not override `enable()` or `disable()` directly as they contain core safety logic.
4. ❌ **No Inventions**: Only use methods and properties explicitly defined in the provided context (e.g., in BasePlugin or documented helpers).

## FILE READING PROTOCOL
The following content is organized by PRIORITY.
- **Start of File:** `# ==== FILE: path/to/file.ext ====`
- **End of File:** `# ==== END OF FILE: path/to/file.ext ====`

Read files sequentially. Example implementations are at the ABSOLUTE TOP to serve as the primary source of truth.
"""

    def collect_files(base_dir):
        """
        Categorizes files into specific priority tiers.
        Tier 1 is now strictly the plugins/examples/ folder.
        """
        examples = []  # plugins/examples/* (PRIORITY #1)
        priority_docs = []  # README, PLUGIN.md, base_plugin.py
        plugin_core = []  # src/plugins/... (excluding examples)
        project_source = []  # All other .py files

        for root, dirs, files in os.walk(base_dir):
            # Exclude build artifacts and environments
            dirs[:] = [
                d
                for d in dirs
                if d
                not in ("build", ".venv", "waypanel.egg-info", "__pycache__", ".git")
            ]

            for file in files:
                if not file.endswith((".py", ".md", ".txt", ".yaml", ".json")):
                    continue

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, base_dir)

                # Tier 1: Absolute Priority - The Examples Folder
                if "plugins/examples" in rel_path or file.lower().startswith("example"):
                    examples.append((file_path, rel_path))
                # Tier 2: Core Protocol & Base Logic
                elif (
                    file.lower() in ("readme.md", "plugin.md", "base_plugin.py")
                    or "src/core" in rel_path
                ):
                    priority_docs.append((file_path, rel_path))
                # Tier 3: Internal Plugin Logic
                elif "plugins" in rel_path:
                    plugin_core.append((file_path, rel_path))
                # Tier 4: General project source
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

        # MANDATORY ORDER: Examples first, then documentation, then core, then source.
        write_files(examples, out_f, "PRIORITY #1: IMPLEMENTATION EXAMPLES")
        write_files(docs, out_f, "CORE PROTOCOL & BASE CLASSES")
        write_files(plugins, out_f, "WAYPANEL PLUGIN CORE")
        write_files(source, out_f, "GENERAL SOURCE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Waypanel Context Scraper (Examples-First)"
    )
    parser.add_argument("--input", default=".", help="Root directory")
    parser.add_argument("--output", default="waypanel.txt", help="Output file")

    args = parser.parse_args()

    if os.path.isdir(args.input):
        scrape_python_files(args.input, args.output)
        print(f"\nContext generated at {args.output} with Priority #1 on Examples.")
    else:
        print(f"Error: {args.input} is not a directory.")
