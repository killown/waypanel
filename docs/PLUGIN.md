# 🧩 Creating Your First Plugin in 5 Minutes (All-in-One Guide)

This guide walks you through everything you need to create a simple plugin for **waypanel**. By the end, you'll have a working plugin that shows a button and displays a random number when clicked.

---

## 📌 Table of Contents
1. [Prerequisites](#prerequisites)
2. [Step 1: Create the Plugin File](#step-1-create-the-plugin-file)
3. [Step 2: Reload or Restart waypanel](#step-2-reload-or-restart-waypanel)
4. [Understanding the Code](#understanding-the-code)
5. [Customization Ideas](#customization-ideas)
6. [Tips & Troubleshooting](#tips--troubleshooting)
7. [Next Steps](#next-steps)

---

## ✅ Prerequisites

Before starting:
- Ensure `waypanel` is installed and running
- You should be using a Wayland compositor like **Wayfire**, **Sway**, or similar
- Basic Python knowledge is helpful but not required

---

## 🛠️ Step 1: Create the Plugin File

Create a new file in your plugins directory:

```bash
mkdir -p ~/.config/waypanel/plugins
nano ~/.config/waypanel/plugins/random_plugin.py
```

## 🔧 Paste this complete plugin code:

```python

def get_plugin_metadata(_):
    return {
        "enabled": True,
        "container": "top-panel-center",
        "index": 10,
        "deps": ["top_panel"],
    }

def get_plugin_class()
    from gi.repository import Gtk, GLib
    import random
    from waypanel.src.plugins.core._base import BasePlugin
    class RandomNumberPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.popover = None
            self.button = None
    
        def create_widget(self):
            """Create the main widget for the plugin."""
            self.button = Gtk.Button()
            self.button.set_icon_name("dialog-information-symbolic")
            self.button.connect("clicked", self.on_button_clicked)
            self.button.set_tooltip_text("Show random number")
            return self.button
    
        def on_button_clicked(self, widget):
            """Handle button click to show a random number."""
            if not self.popover:
                self.popover = Gtk.Popover()
                self.popover.set_parent(self.button)
                self.popover.set_autohide(True)
    
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                box.set_margin_top(10)
                box.set_margin_bottom(10)
                box.set_margin_start(10)
                box.set_margin_end(10)
    
                label = Gtk.Label.new(f"🎲 Random Number: {random.randint(1, 100)}")
                box.append(label)
    
                refresh_btn = Gtk.Button(label="Generate Again")
                refresh_btn.connect("clicked", self.refresh_random_number, label)
                box.append(refresh_btn)
    
                self.popover.set_child(box)
    
            self.popover.popup()
    
        def refresh_random_number(self, button, label):
            """Refresh the random number in the popover."""
            label.set_text(f"🎲 Random Number: {random.randint(1, 100)}")
    
        def set_widget(self):
            """Return the widget and append mode."""
            return self.create_widget(), "append"
```

## 🔄 Step 2: Reload or Restart waypanel

After saving the file, reload or restart waypanel to load the plugin:
bash

pkill -f waypanel/main.py  
python run.py

## 🛠️ Tips & Troubleshooting


### ❗ Common Issues
Problem	Solution
Button appears but nothing happens	Ensure Gtk.Popover is properly initialized
No logs visible	Add self.logger.info("Debug message")
Import errors	Confirm path matches waypanel/src/plugins/core/_base.py
🚀 Next Steps

Once you've created your first plugin, try these advanced steps:

    🎯 Create a background service plugin (e.g., clock or battery monitor)

    🧬 Subscribe to events using event_manager.subscribe_to_event("view-focused", callback)

    🧪 Test different placements (bottom-panel, left-panel, etc.)

## 📘 Bonus: Minimal Template

Use this as a boilerplate for future plugins:
```python

def get_plugin_metadata(_):
    """
    Define the plugin's properties and placement using the modern dictionary format.

    Valid Positions:
        - Top Panel:
            "top-panel-left"
            "top-panel-center"
            "top-panel-right"
            "top-panel-systray"
            "top-panel-after-systray"

        - Bottom Panel:
            "bottom-panel-left"
            "bottom-panel-center"
            "bottom-panel-right"

        - Left Panel:
            "left-panel-top"
            "left-panel-center"
            "left-panel-bottom"

        - Right Panel:
            "right-panel-top"
            "right-panel-center"
            "right-panel-bottom"

        - Background:
            "background"  # For plugins that don't have a UI

    Returns:
        dict: Plugin configuration metadata.
    """
    return {
        "enabled": True,
        "container": "top-panel-right",
        "index": 5,
        "deps": ["event_manager"],
    }


def get_plugin_class():
    """
    Returns the main plugin class. All necessary imports are deferred here.
    """
    import asyncio
    from src.plugins.core._base import BasePlugin

    class ExampleBroadcastPlugin(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.button = None

        async def on_start(self):
            """
            Asynchronous entry point, replacing the deprecated initialize_plugin().
            """
            self.logger.info("Setting up ExampleBroadcastPlugin...")
            self._setup_plugin_ui()
            self.logger.info("ExampleBroadcastPlugin has started.")

        def _setup_plugin_ui(self):
            """
            Set up the plugin's UI and functionality.
            """
            self.button = self.create_broadcast_button()
            self.main_widget = (self.button, "append")

        def create_broadcast_button(self):
            """
            Create a button that triggers an IPC broadcast when clicked.
            """
            # Use self.gtk helper for widget creation
            button = self.gtk.Button()
            button.connect("clicked", self.on_button_clicked)
            button.set_tooltip_text("Click to broadcast a message!")
            return button

        def on_button_clicked(self, widget):
            """
            Handle button click event by correctly scheduling the async broadcast.
            """
            self.logger.info("ExampleBroadcastPlugin button clicked!")

            message = {
                "event": "custom_message",
                "data": "Hello from ExampleBroadcastPlugin!",
            }

            asyncio.create_task(self.broadcast_message(message))

        async def broadcast_message(self, message):
            """
            Broadcast a custom message to all connected clients via the IPC server.
            """
            try:
                self.logger.info(f"Broadcasting message: {message}")
                await self.ipc_server.broadcast_message(message)
            except Exception as e:
                self.logger.error(f"Failed to broadcast message: {e}")

        async def on_stop(self):
            """
            Called when the plugin is stopped or unloaded.
            """
            self.logger.info("ExampleBroadcastPlugin has stopped.")

        async def on_reload(self):
            """
            Called when the plugin is reloaded dynamically.
            """
            self.logger.info("ExampleBroadcastPlugin has been reloaded.")

        async def on_cleanup(self):
            """
            Called before the plugin is completely removed.
            """
            self.logger.info("ExampleBroadcastPlugin is cleaning up resources.")

        def about(self):
            """An example plugin that demonstrates how to create a UI widget and broadcast a message via the IPC server."""
            return self.about.__doc__

        def code_explanation(self):
            """
            This plugin is an example demonstrating how to create a simple user
            interface (UI) element and use the Inter-Process Communication (IPC)
            system to broadcast a message to other components.

            The core logic is centered on **event-driven UI and IPC broadcasting**:

            1.  **UI Creation**: It creates a Gtk.Button and sets it as the main
                widget, specifying its placement on the top-right of the panel.
            2.  **Event Handling**: It connects the button's "clicked" signal to the
                `on_button_clicked` method, which correctly schedules the
                asynchronous `broadcast_message` using `asyncio.create_task`.
            3.  **IPC Broadcasting**: The `broadcast_message` method then uses the
                `ipc_server` to send a predefined message to any other plugin or
                client that is listening for the "custom_message" event.
            """
            return self.code_explanation.__doc__

    return ExampleBroadcastPlugin
```

