# Creating Your First Waypanel Plugin (Complete Guide)

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
            "description": "some description for the plugin"
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

            def on_start(self):
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

            def on_stop(self):
                """Deactivation Point: Performs cleanup."""
                # self.remove_main_widget() is provided by BasePlugin for safety
                self.logger.info("MinimalButtonPlugin stopping.")

        return MinimalButtonPlugin

---

## 2. BasePlugin API Reference

By inheriting from `BasePlugin`, your class gains access to a comprehensive suite of properties and methods designed to handle concurrency, configuration, UI manipulation, and system interaction without blocking the main thread.

### Lifecycle Hooks

- **`def on_enable(self)`**: The primary activation hook. Initialize UI components, register signals, and start background logic here.
- **`def on_disable(self)`**: The deactivation hook. Use this for custom cleanup (closing sockets or file handles). `BasePlugin` handles task cancellation automatically.

### Concurrency & Async Helpers

- **`self.run_in_thread(func, *args)`**: Executes a function in the global `ThreadPoolExecutor`.
- **`self.run_in_async_task(coro)`**: Schedules an `asyncio` coroutine in the global event loop.
- **`self.schedule_in_gtk_thread(func, *args)`**: Safely pushes a function call to the main GTK thread. **Required** for any UI updates originating from a thread or async task.
- **`self.run_cmd(cmd)`**: Runs a shell command non-blockingly via the thread pool.

### Configuration & State

- **`self.get_plugin_setting(key, default)`**: Retrieves a value from `config.toml` specific to your plugin ID.
- **`self.set_plugin_setting(key, value)`**: Persists a value to the configuration file.
- **`self.get_plugin_setting_add_hint(key, default, hint)`**: Retrieves a setting and registers a documentation hint for the Control Center UI.
- **`self.update_config(key_path, value)`**: Updates and reloads configuration dynamically.

### UI & GTK Utilities (`self.gtk_helper`)

- **`self.set_widget()`**: Validates and prepares `self.main_widget` for the panel.
- **`self.create_popover(relative_to, content)`**: Creates a standardized GTK popover.
- **`self.get_icon(icon_name, size)`**: Fetches a themed icon as a `Gtk.Image` or `Gdk.Texture`.
- **`self.add_cursor_effect(widget, cursor_name)`**: Changes the mouse cursor on hover (e.g., `"pointer"`).
- **`self.create_async_button(label, callback)`**: Returns a button that executes a callback in a background thread.
- **`self.update_widget_safely(widget, update_func)`**: Validates widget existence before applying updates.

### System & Compositor Helpers

- **`self.notify_send(title, message, icon)`**: Dispatches a system notification.
- **`self.get_data_path(filename)`**: Returns a persistent path in `~/.local/share/waypanel/` for plugin data.
- **`self.get_cache_path(filename)`**: Returns a path in the system cache directory.
- **`self.set_keyboard_on_demand(mode=True)`**: Toggles whether the panel intercepts keyboard focus (essential for search inputs).
- **`self.wf_helper.is_view_valid(view_id)`**: Checks if a Wayfire window/view is still active.

### Data Validation (`self.data_helper`)

- **`self.validate_widget(widget)`**: Ensures an object is a valid `Gtk.Widget`.
- **`self.validate_string(obj, name)`**: Checks for non-empty strings and logs errors on failure.
- **`self.validate_method(method)`**: Verifies if a callback is actually callable.

### Module & Environment

- **`self.lazy_load_module(module_name)`**: Imports a module only when called and caches it to keep startup performance high.
- **`self.module_exist(module_name)`**: Checks for the existence of a library and attempts to install it if missing.

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

## 4. Wayfire IPC Events (Compositor State Monitoring)

Plugins subscribe to these events via `self.ipc_server` to monitor and react to changes in the Wayfire compositor state. These events are essential for building taskbars, pagers, and window switchers.

### 4.1. View-Related Events (Window Management)

These events track the lifecycle and properties of individual windows (views).

- **`view-focused`**: Emitted when input focus changes. The `view` field may contain the toplevel view object or `None` (common during switcher/overview activation).
- **`view-pre-map`**: Emitted immediately before a view is mapped. Note: This is a restricted event and is only received if explicitly subscribed to.
- **`view-mapped`**: Emitted when a view becomes visible on the screen.
- **`view-unmapped`**: Emitted when a view is hidden or closed.
- **`view-title-changed`**: Emitted when the window title is updated.
- **`view-app-id-changed`**: Emitted when the application ID (class) changes.
- **`view-geometry-changed`**: Emitted when the view's position or size is modified.
- **`view-tiled`**: Emitted when a view is tiled, snapped, or floating state changes.
- **`view-minimized`**: Emitted when a view is minimized or restored.
- **`view-fullscreen`**: Emitted when a view enters or exits fullscreen mode.
- **`view-sticky`**: Emitted when a view becomes "sticky" (visible on all workspaces) or unsticky.
- **`view-set-output`**: Emitted when a view is moved to another physical output (monitor).
- **`view-workspace-changed`**: Emitted when a view is moved between workspaces.
- **`view-wset-changed`**: Emitted when a view's assigned workspace set changes.

### 4.2. Output and Workspace Events (Desktop Management)

These events track the state of monitors and the virtual desktop layout.

- **`workspace-activated`**: Emitted when the user switches to a different workspace.
- **`wset-workspace-changed`**: Emitted when the active workspace inside a specific workspace set changes.
- **`output-gain-focus`**: Emitted when a specific monitor (output) gains input focus.
- **`output-wset-changed`**: Emitted when an output changes its assigned workspace set.
- **`output-layout-changed`**: Emitted when the physical monitor configuration changes (resolution, position, or plugging/unplugging monitors).
- **`output-removed`**: Emitted when a monitor is disconnected.

### 4.3. Input and Plugin Events

- **`keyboard-modifier-state-changed`**: Emitted when modifier keys (Shift, Ctrl, Alt, Super) are pressed or released.
- **`plugin-activation-state-changed`**: Emitted when a Wayfire plugin (like `expo` or `grid`) is activated or deactivated. This is useful for hiding the panel during full-screen overviews.
