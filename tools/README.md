# Waypanel Scraper Guide

This tool aggregates the Waypanel project source code into a single, formatted text file to provide high-fidelity context for AI coding assistants.

## 1\. Generate the Context File

Run the script from your terminal at the project root. It automatically excludes `.venv`, `build`, and egg-info directories.

    # Navigate to project root
    cd ~/G/w

    # Run the scraper
    python3 tools/scraper.py --input . --output waypanel_context.txt

**Parameters:**

- `--input`: Directory to scan (default: `.`)
- `--output`: Resulting filename (default: `python_code.txt`)

## 2\. Upload to AI Interface

1.  Open your AI assistant (Gemini, Claude, or ChatGPT).
2.  Upload the generated `waypanel_context.txt`.
3.  The file contains a **Strict Instruction Set** header ensuring the AI respects Waypanel’s "no top-level imports" architecture.

## 3\. Prompting for New Plugins

Use a specific prompt to trigger the logic contained in the file:

    "I have uploaded the Waypanel source code. Using the provided rules and the BasePlugin structure found in the context, create a new plugin that displays system RAM usage."

## 4\. Structural Protocol

The AI identifies files using these unique delimiters provided by the scraper:

- **Start:** `# ==== FILE: path/to/file.ext ====`
- **End:** `# ==== END OF FILE: path/to/file.ext ====`
