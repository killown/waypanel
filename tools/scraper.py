import os
import argparse


def scrape_python_files(base_dir, output_file):
    """
    Scrapes Waypanel project files and organizes them into a structured format
    optimized for AI context windows, prioritizing examples and core documentation.
    """

    ai_header = """
 This is a strict instruction set for code generation. Your primary task is to be a coding assistant restricted to real, verifiable, and context-visible code only.
 The following instruction is only valid for waypanel project: It is STRICTLY PROHIBITED to import library modules at the top level. The only code at the top level are function definitions and metadata.
 Read the PLUGIN.md file, to find how to build plugins if the user asked for that, just go for # ==== FILE: docs/PLUGIN.md ==== to find the instructions

 Now the following instructions is for any kind of project:

---
**File Reading Protocol**
The subsequent content is a concatenation of multiple source files. You must read the file contents sequentially, identifying individual files by their unique delimiters:
- **Start of File:** `# ==== FILE: path/to/file.ext ====`
- **End of File:** `# ==== END OF FILE: path/to/file.ext ====`
---

Priority: When generating code, your **highest priority** is to ensure compliance with all rules listed below.

Rules:
1. 🧪 **Use Modern APIs**: You **MUST** use the most updated, non-deprecated API from any module (standard library or otherwise). Avoid obsolete methods.
2. ❌ **Do Not Invent**: Never create or use methods, attributes, or functions not explicitly shown or defined in the provided code/context. If unsure, ask the user.
3. 🔒 **Source-Visible Only**: Only use elements that are present in the user’s code, clearly defined in visible imports, or are part of the standard library.
4. 📚 **Context Check**: If a class or module is referenced but not defined, assume nothing about its structure. Wait for the user to provide it.
5. 🛑 **Stop on Ambiguity**: If any part of the implementation is unclear, requires assumptions, or if the correct modern API is uncertain, stop and ask the user for clarification.
"""

    def collect_files(base_dir):
        """
        Categorizes files into specific priority tiers to ensure the most
        instructive content (examples/docs) appears earliest in the context.
        """
        priority_docs = []  # README, PLUGIN.md, etc.
        examples = []  # example_*.py
        plugin_core = []  # src/plugins/...
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

                # Tier 1: Core Documentation
                if file.lower() in ("readme.md", "plugin.md") or root.endswith("docs"):
                    priority_docs.append((file_path, rel_path))
                # Tier 2: Example implementations (Highest priority for AI learning)
                elif file.lower().startswith("example"):
                    examples.append((file_path, rel_path))
                # Tier 3: Plugins
                elif "plugins" in rel_path:
                    plugin_core.append((file_path, rel_path))
                # Tier 4: General source
                else:
                    project_source.append((file_path, rel_path))

        return priority_docs, examples, plugin_core, project_source

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

        docs, examples, plugins, source = collect_files(base_dir)

        # Order of writing determines AI priority (Top = Most Important)
        write_files(docs, out_f, "CORE DOCUMENTATION")
        write_files(examples, out_f, "EXAMPLE PLUGINS (SOURCE OF TRUTH)")
        write_files(plugins, out_f, "WAYPANEL PLUGIN CORE")
        write_files(source, out_f, "GENERAL PROJECT SOURCE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Waypanel Context Scraper")
    parser.add_argument("--input", default=".", help="Root directory")
    parser.add_argument("--output", default="waypanel.txt", help="Output file")

    args = parser.parse_args()

    if os.path.isdir(args.input):
        scrape_python_files(args.input, args.output)
        print(f"\nContext generated at {args.output}")
    else:
        print(f"Error: {args.input} is not a directory.")
