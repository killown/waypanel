### Building plugins with AI

This document explains how to use the [scraper.py](https://github.com/killown/waypanel/blob/main/tools/scraper.py) tool to generate a context file that allows an AI to build Waypanel plugins while adhering to strict architectural rules.
1. Generate the Context File

Run the script from your terminal at the project root. python3 tools/scraper.py --input . --output waypanel_context.txt

Parameters:

    --input: Directory to scan (default: .)
    --output: Resulting filename (default: python_code.txt)

### 2. Upload to AI Interface

    Open your AI assistant (Gemini, Claude, or ChatGPT).
    Upload the generated waypanel_context.txt.
    The file contains a Strict Instruction Set header ensuring the AI respects Waypanel’s "no top-level imports" architecture.

### 3. Prompting for New Plugins

Use a specific prompt to trigger the logic contained in the file:

"I have uploaded the Waypanel source code. Using the provided rules and the BasePlugin structure found in the context, create a new plugin that displays system RAM usage."

### 4. Verification & Installation

The AI will return a code block formatted within the project's delimiters.

    Copy the code into a new file.

    Ensure the metadata ID is unique.

    Follow the installation steps below.

### 5. Plugin Installation

The plugin architecture is simple; it usually consists of a single file. To install:

    Copy the plugin file to ~/.local/share/waypanel/plugins/.

    Restart the panel.

    If the code is correct, the plugin will be active immediately.



### 6. Structural Protocol

The AI identifies files using these unique delimiters provided by the scraper:

    Start: # ==== FILE: path/to/file.ext ====
    End: # ==== END OF FILE: path/to/file.ext ====
