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

from gi.repository import Gtk, GLib
import random
from waypanel.src.plugins.core._base import BasePlugin

# Enable or disable the plugin
ENABLE_PLUGIN = True

# Define where the plugin should appear
def get_plugin_placement(panel_instance):
    position = "top-panel-right"
    order = 10
    return position, order

def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return RandomNumberPlugin(panel_instance)

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

killall waypanel
waypanel

## 🎯 Understanding the Code

### Let's break down the structure so you can modify it later.
🔹 ENABLE_PLUGIN = True

    Enables/disables the plugin globally.

🔹 get_plugin_placement()

    Determines where the plugin appears (top-panel-left, top-panel-right, etc.)

    order sets its priority within that area.

🔹 initialize_plugin()

    Instantiates the plugin class if enabled.

🔹 RandomNumberPlugin Class

    Inherits from BasePlugin

    Contains logic for creating the UI and handling interactions

🔹 create_widget()

    Returns the main widget (in this case, a button with an icon)

🔹 on_button_clicked()

    Creates a popover with a random number and a refresh button

🔹 refresh_random_number()

    Updates the label with a new random number

🔹 set_widget()

    Tells waypanel how to place the widget (append adds it at the end)

## 🛠️ Tips & Troubleshooting


### ❗ Common Issues
Problem	Solution
Plugin doesn't show up	Make sure ENABLE_PLUGIN = True
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

from gi.repository import Gtk
from waypanel.src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True

def get_plugin_placement(panel_instance):
    return "top-panel-right", 10

def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return MyPlugin(panel_instance)

class MyPlugin(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.button = None

    def create_widget(self):
        self.button = Gtk.Button(label="Click Me!")
        self.button.connect("clicked", self.on_click)
        return self.button

    def on_click(self, _):
        print("Button clicked!")

    def set_widget(self):
        return self.create_widget(), "append"
```


Happy coding! 🚀
