# Waypanel Documentation

## Overview

Waypanel is a configurable panel application designed for the Wayfire compositor. It provides a modular architecture where plugins can be easily added, removed, or customized. The application is built using Python and leverages GTK4 for its user interface. Below is a detailed explanation of the main components and how to create a simple plugin.

---

## Main Components

### 1. `main.py`
- **Responsibility**:
  - `main.py` is responsible for the initial setup of the application.
  - It performs essential tasks such as:
    - Validating the configuration file (`waypanel.toml`).
    - Setting up logging.
    - Initializing the application environment.
  - If everything is configured correctly, it calls the `Panel` class from `panel.py` to start the panel.

---

### 2. `panel.py`
- **Responsibility**:
  - `panel.py` is the core module responsible for managing the panels in all directions (top, bottom, left, right).
  - It sets up the panels based on the configuration file and initializes the plugin loader.
  - Plugins interact with the `Panel` instance to append or remove widgets dynamically.

- **Key Features**:
  - **Panel Setup**:
    - Configures panels for different directions (e.g., top, bottom, left, right).
    - Each panel is created using the `CreatePanel` utility.
  - **Plugin Integration**:
    - Automatically loads plugins by scanning directories.
    - Plugins use the `Panel` instance to interact with the UI.
  - **Event Management**:
    - Integrates with the `EventManagerPlugin` to handle IPC events from Wayfire via `pywayfire`.
  - **Gestures**:
    - Supports gestures (e.g., swipe, click) on the panels through the `gestures_setup.py` plugin.

- **Methods**:
  - `_set_monitor_dimensions`: Sets the monitor dimensions based on the configuration or defaults.
  - `_initialize_utilities`: Initializes utility functions and properties.
  - `_setup_panels`: Configures panels for each direction (top, bottom, left, right).

---

### 3. Plugin System
- **Automatic Loading**:
  - Plugins are automatically loaded by scanning directories under `src/plugins`.
  - The system looks for specific metadata in each plugin file:
    - `get_plugin_placement()`: Defines the plugin's position (e.g., "left", "right", "center") and order.
    - `initialize_plugin(panel_instance)`: Initializes the plugin and returns its instance.
  - Plugins are sorted by priority and order before being initialized.

- **Interaction with Panels**:
  - Plugins interact with the `Panel` instance to modify the UI dynamically.
  - Key methods provided by the `Panel` instance:
    - **`append_widget()`**:
      - Used by plugins to append widgets to the panel.
      - The widget is added to the appropriate section (e.g., left, right, center) based on the plugin's placement.
    - **`panel_set_content(widget)`**:
      - Used when you need to set widgets in other panels (e.g., bottom, left).
      - This method allows setting content directly into a specific panel.

---

### 4. Event Manager
- **Responsibility**:
  - The `EventManagerPlugin` listens to IPC events from Wayfire via `pywayfire`.
  - It dispatches these events to subscribed plugins, enabling them to react dynamically to system changes.

- **Usage**:
  - Plugins can subscribe to specific events (e.g., "view-focused", "view-mapped") using the `subscribe_to_event` method.
  - Example:
    ```python
    event_manager = panel_instance.plugin_loader.plugins["event_manager"]
    event_manager.subscribe_to_event("view-focused", callback_function)
    ```

---

### 5. Gestures
- **Responsibility**:
  - The `gestures_setup.py` plugin adds gesture support to the panels.
  - Gestures include actions like swiping, clicking, or scrolling on the panel sections (left, center, right).

- **Usage**:
  - Plugins can define custom gestures and associate them with callbacks.
  - Example:
    ```python
    def pos_left_right_click(self, *_):
        print("Right-click detected on the left section.")
    ```

---

## How to Build a Simple Plugin

### Steps to Create a Plugin
1. **Define Metadata**:
   - Implement the `get_plugin_placement()` function to specify the plugin's position and order:
     ```python
     def get_plugin_placement():
         return "right", 10  # Position: right, Order: 10
     ```
   - The position can be `"left"`, `"right"`, `"center"`, `"systray"`, or `"after-systray"`.
   - The order determines the sequence of plugins within the same position.

2. **Initialize the Plugin**:
   - Implement the `initialize_plugin(panel_instance)` function:
     ```python
     def initialize_plugin(panel_instance):
         if ENABLE_PLUGIN:
             return MySimplePlugin(panel_instance)
     ```

3. **Create the Plugin Class**:
   - Define a class for your plugin:
     ```python
     class MySimplePlugin:
         def __init__(self, panel_instance):
             self.panel_instance = panel_instance
             self.widget = Gtk.Button(label="Click Me")
         
         def append_widget(self):
             return self.widget
     ```

4. **Append the Widget**:
   - Use the `append_widget()` method to add the widget to the panel:
     - The plugin loader will call this method automatically if defined.

5. **Optional: Set Content for Other Panels**:
   - If your plugin needs to set content in other panels (e.g., bottom, left), implement the `panel_set_content()` method:
     ```python
     def panel_set_content(self):
         return self.my_custom_widget
     ```

6. **Enable/Disable the Plugin**:
   - Set `ENABLE_PLUGIN = True` to enable the plugin or `False` to disable it.

---

## Key Concepts

### 1. Panel Instance
- The `Panel` instance is the central object that manages all panels and plugins.
- It provides access to:
  - Panels in different directions (top, bottom, left, right).
  - Utility functions (e.g., `update_widget`, `utils`).
  - The plugin loader (`plugin_loader`).

### 2. `append_widget()`
- A method used by plugins to append widgets to the panel.
- The widget is added to the appropriate section based on the plugin's placement.

### 3. `panel_set_content(widget)`
- A method used to set content directly into a specific panel (e.g., bottom, left).
- This is useful when you need to manage widgets in panels other than the one associated with the plugin's position.

---

## Conclusion

Waypanel provides a flexible and extensible framework for building a customizable panel for Wayfire. By leveraging the `Panel` instance, plugins can dynamically modify the UI and respond to system events. The automatic plugin loading system simplifies development, allowing developers to focus on creating unique features.
