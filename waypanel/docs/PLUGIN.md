# Plugin Development Guide for Waypanel

Waypanel is designed to be highly extensible through plugins. This guide explains how plugins work, how they are loaded, and how you can create your own plugins to extend the functionality of the panel.

---

## Overview of Plugins

Plugins are the building blocks of Waypanel. They allow developers to add new widgets, handle events, or interact with the system. Each plugin is automatically loaded based on metadata and configuration. Plugins can be enabled or disabled via a flag or by removing the plugin file.

---

## How Plugins Work

1. **Automatic Loading**
   - Plugins are automatically loaded by scanning directories under `src/plugins`.
   - The system looks for specific metadata in each plugin file:
     - `get_plugin_placement()`: Defines the plugin's position (e.g., "left", "right", "center") and order.
     - `initialize_plugin(panel_instance)`: Initializes the plugin and returns its instance.

2. **Plugin Structure**
   - Each plugin must define:
     - A `get_plugin_placement()` function to specify where the plugin should appear in the panel.
     - An `initialize_plugin(panel_instance)` function to initialize the plugin.
     - A plugin class that encapsulates its functionality.

3. **Interacting with the Panel**
   - Plugins interact with the `Panel` instance to modify the UI dynamically.
   - Key methods provided by the `Panel` instance:
     - `append_widget()`: Adds a widget to the panel.
     - `panel_set_content(widget)`: Sets content directly into a specific panel (e.g., bottom, left).

4. **Event Handling**
   - Plugins can subscribe to IPC events from Wayfire using the `EventManagerPlugin`.
   - Events include "view-focused", "view-mapped", "output-gain-focus", etc.

5. **Gestures**
   - Plugins can define custom gestures (e.g., swipe, click) and associate them with callbacks.

---

## Creating a Simple Plugin

To create a plugin, follow these steps:

1. **Define Metadata**
   - Implement the `get_plugin_placement()` function to specify the plugin's position and order:
     ```python
     def get_plugin_placement():
         return "right", 10  # Position: right, Order: 10
     ```

2. **Initialize the Plugin**
   - Implement the `initialize_plugin(panel_instance)` function:
     ```python
     def initialize_plugin(panel_instance):
         if ENABLE_PLUGIN:
             return MySimplePlugin(panel_instance)
     ```

3. **Create the Plugin Class**
   - Define a class for your plugin:
     ```python
     class MySimplePlugin:
         def __init__(self, panel_instance):
             self.panel_instance = panel_instance
             self.widget = Gtk.Button(label="Click Me")
         
         def append_widget(self):
             return self.widget
     ```

4. **Append the Widget**
   - Use the `append_widget()` method to add the widget to the panel.

5. **Optional: Set Content for Other Panels**
   - If your plugin needs to set content in other panels (e.g., bottom, left), implement the `panel_set_content()` method:
     ```python
     def panel_set_content(self):
         return self.my_custom_widget
     ```

6. **Enable/Disable the Plugin**
   - Use the `ENABLE_PLUGIN` flag to enable or disable the plugin.

---

## Key Concepts

### Panel Instance
- The `Panel` instance is the central object that manages all panels and plugins.
- It provides access to:
  - Panels in different directions (top, bottom, left, right).
  - Utility functions (e.g., `update_widget`, `utils`).
  - The plugin loader (`plugin_loader`).

### `append_widget()`
- A method used by plugins to append widgets to the panel.
- The widget is added to the appropriate section based on the plugin's placement.

### `panel_set_content(widget)`
- A method used to set content directly into a specific panel (e.g., bottom, left).
- This is useful when you need to manage widgets in panels other than the one associated with the plugin's position.

---

## Conclusion

Waypanel provides a flexible and extensible framework for building a customizable panel for Wayfire. By leveraging the `Panel` instance, plugins can dynamically modify the UI and respond to system events. The automatic plugin loading system simplifies development, allowing developers to focus on creating unique features.
