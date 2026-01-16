import os
import argparse


def scrape_python_files(base_dir, output_file):
    ai_header = """

 This is a strict instruction set for code generation. Your primary task is to be a coding assistant restricted to real, verifiable, and context-visible code only.
 The following instruction is only valid for waypanel project: It is STRICTLY PROHIBITED to import library modules at the top level. The only code at the top level are function definitions and metadata.
 Read the PLUGIN.md file, to find how to build plugins if the user asked for that, just go for # ==== FILE: docs/PLUGIN.md ==== to find the instructions

 Now the following instructions is for any kind of project:


---
**File Reading Protocol**
The subsequent content is a concatenation of multiple source files. You must read the file contents sequentially, identifying individual files by their unique delimiters:
- **Start of File:** `# ==== FILE: path/to/file.ext ====
- **End of File:** `# ==== END OF FILE: path/to/file.ext ====
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
        """Collects all valid files, separating example* ones first."""
        example_files = []
        other_files = []
        for root, dirs, files in os.walk(base_dir):
            # Exclude build, .venv, and egg-info directories
            dirs[:] = [
                d for d in dirs if d not in ("build", ".venv", "waypanel.egg-info")
            ]

            for file in files:
                if file.endswith((".py", ".md", ".txt")):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_dir)
                    if file.lower().startswith("example"):
                        example_files.append((file_path, rel_path))
                    else:
                        other_files.append((file_path, rel_path))
        return example_files, other_files

    def write_files(file_list, out_f):
        for file_path, rel_path in file_list:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                out_f.write(f"\n\n# ==== FILE: {rel_path} ====\n\n")
                out_f.write(content)
                out_f.write(f"\n\n# ==== END OF FILE: {rel_path} ====\n")
                print(f"Processed: {rel_path}")
            except UnicodeDecodeError:
                print(f"Skipped (encoding issue): {rel_path}")
            except Exception as e:
                print(f"Error processing {rel_path}: {e}")

    with open(output_file, "w", encoding="utf-8") as out_f:
        out_f.write(ai_header)

        example_files, other_files = collect_files(base_dir)

        # Write example* files first
        if example_files:
            out_f.write("\n\n# ==== SECTION: example* files ====\n")
            write_files(example_files, out_f)

        # Then write the remaining files
        if other_files:
            out_f.write("\n\n# ==== SECTION: remaining files ====\n")
            write_files(other_files, out_f)


if __name__ == "__main__":
    # USAGE: scraper.py --input path/to/waypanel --output waypanel.txt
    parser = argparse.ArgumentParser(
        description="Scrape Python/Markdown/Text files into a single file, prioritizing files starting with 'example'."
    )
    parser.add_argument("--input", default=".", help="Root directory to search")
    parser.add_argument("--output", default="python_code.txt", help="Output file path")

    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"Error: Input directory '{args.input}' does not exist.")
        exit(2)

    print(f"Scraping Python files from: {args.input}")
    print(f"Output will be saved to: {args.output}")

    scrape_python_files(args.input, args.output)

    print("\nDone! All Python files have been combined.")
