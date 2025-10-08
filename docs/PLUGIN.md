# ✅ Creating Your First Waypanel Plugin (Complete Guide)

This guide explains the \*\*mandatory structure\*\* for a modern Waypanel plugin, strictly adhering to the rule of importing modules inside `get_plugin_class()` and using the modern \*\*asynchronous API\*\* (`on_start`).

---

## 1\. The Core Plugin Structure & Deferred Imports

A Waypanel plugin relies on three mandatory top-level components. The most critical rule is that ALL imports MUST be deferred.

### 1.1. Mandatory Top-Level Components

- **`def get_plugin_metadata(_):`:** Plugin Configuration. Must be the first function. Defines placement, dependencies, and load order. Returns a `dict`.
- **`def get_plugin_class():`:** Class Definition & Imports. The module loader's entry point. \*\*ALL necessary standard and internal imports MUST happen inside this function.\*\*
- **The Plugin Class (Inheriting `BasePlugin`):** Contains the logic and lifecycle methods.

### 1.2. Minimal Working Plugin Code

Save this code as `~/.local/share/waypanel/plugins/minimal_random_plugin.py`:

    # NOTE: No top-level imports are allowed here.

    def get_plugin_metadata(_):
        """
        MANDATORY: Defines the plugin's properties and placement.
        We place a simple button on the right side of the top panel.
        """
        return {
            "id": "com.waypanel.plugin.example",
            "name": "Example Background Plugin",
            "version": "1.0.0",
            "enabled": True,
            "container": "top-panel-right",
            "index": 1,
            "deps": ["top_panel"], # Requires the top panel to exist
        }


    def get_plugin_class():
        """
        MANDATORY: Returns the main plugin class.
        ALL necessary standard and internal imports are deferred here.
        """
        import random
        import asyncio # Needed for BasePlugin's async methods
        import gi
        gi.require_version("Gtk", "4.0") # Ensure correct GTK version

        # Core Waypanel and GTK imports
        from gi.repository import Gtk, GLib
        from src.plugins.core._base import BasePlugin # This path is required

        class MinimalButtonPlugin(BasePlugin):
            def __init__(self, panel_instance):
                """Initializes the plugin by calling the BasePlugin constructor."""
                super().__init__(panel_instance)
                self.button = None

            async def on_start(self):
                """
                Activation Lifecycle: Creates the UI and sets it as the main widget.
                """
                # Create a simple button widget
                self.button = Gtk.Button(label="Get Random")

                # Connect the click signal to a method in the class
                self.button.connect("clicked", self.on_button_clicked)

                # Set the main widget for the panel to append.
                # self.main_widget is the required property: (widget, instruction)
                self.main_widget = (self.button, "append")

                self.logger.info("MinimalButtonPlugin started successfully.")

            def on_button_clicked(self, widget):
                """Handles the button click event (synchronous context)."""
                # Use self.logger (provided by BasePlugin) instead of print()
                rand_num = random.randint(100, 999)
                self.button.set_label(f"Random: {rand_num}")

                self.logger.info(f"Button clicked. New random number: {rand_num}")

            async def on_stop(self):
                """Deactivation Point: Performs cleanup."""
                # self.remove_main_widget() is provided by BasePlugin for safety
                self.logger.info("MinimalButtonPlugin stopping.")

        return MinimalButtonPlugin

---

## 2\. BasePlugin and Asynchronous Lifecycle

By inheriting from `BasePlugin`, your class gains essential resources and lifecycle methods:

- **`self.logger`:** The structured logger. Use `self.logger.info()`, `.error()`, etc.
- **`self.ipc_server`:** The object for subscribing to Wayfire events and handling inter-plugin communication.
- **`self.run_in_async_task(coro)`:** Crucial helper. Use this to call asynchronous methods (which contain `await`) from a synchronous GTK callback (like `on_button_clicked`).
- **`async def on_start()`:** The required activation method.
- **`async def on_stop()`:** The required deactivation/cleanup method.

---

## 3\. Valid Widget Positions (The `container` Key)

This table lists all valid values for the `"container"` key in your plugin's metadata, defining where the widget will be rendered.

Panel Type

Position Key

Description

**Top Panel**

`"top-panel-left"`

Far left of the top panel.

`"top-panel-center"`

Center section.

`"top-panel-right"`

Far right section.

`"top-panel-systray"`

Reserved for the System Tray area.

`"top-panel-after-systray"`

Immediately following the System Tray.

**Bottom Panel**

`"bottom-panel-left"`

Far left of the bottom panel.

`"bottom-panel-center"`

Center section.

`"bottom-panel-right"`

Far right section.

**Left Panel (Vertical)**

`"left-panel-top"`

Top section.

`"left-panel-center"`

Center section.

`"left-panel-bottom"`

Bottom section.

**Right Panel (Vertical)**

`"right-panel-top"`

Top section.

`"right-panel-center"`

Center section.

`"right-panel-bottom"`

Bottom section.

**Background**

`"background"`

For plugins that run logic/services only (no visible UI).

---

## 4\. Wayfire IPC Events (Compositor State Monitoring)

Plugins subscribe to these events via `self.ipc_server` to monitor changes in the Wayfire compositor state (windows, workspaces, monitors).

### 4.1. View-Related Events (Window Management)

    "view-focused"          # A window gained input focus.
    "view-unmapped"         # A window was hidden or closed.
    "view-mapped"           # A window became visible.
    "view-title-changed"    # The window's title was updated.
    "view-app-id-changed"   # The window's application ID changed.
    "view-set-output"       # The window was moved to a different monitor.
    "view-workspace-changed"# The window moved to a different workspace.
    "view-geometry-changed" # The position or size changed.
    "view-tiled"            # The window was snapped to a side.
    "view-minimized"        # The window was minimized.
    "view-fullscreen"       # The window entered/exited fullscreen mode.
    "view-sticky"           # The window became visible on all workspaces.
    "view-wset-changed"     # The view's assigned workspace set changed.

### 4.2. Output and Workspace Events (Desktop Management)

    "wset-workspace-changed"        # The active workspace set of an output changed.
    "workspace-activated"           # User switched to a new workspace.
    "output-wset-changed"           # An output's workspace set (wset) changed.
    "plugin-activation-state-changed" # A Wayfire plugin was activated/deactivated.
    "output-gain-focus"             # An output (monitor) gained input focus.
    "output-layout-changed"         # Monitor configuration changed.
    "output-removed"                # A monitor was disconnected.
