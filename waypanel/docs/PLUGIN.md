## Plugin Documentation

### Loading Plugins

Plugins are loaded dynamically from two primary locations:

1. **Built-in Plugins**: Located in the `src.plugins` package (e.g., `waypanel/src/plugins`).
2. **Custom Plugins**: Located in the user's configuration directory (`~/config/waypanel/plugins`).

The `PluginLoader` automatically clears the cache directory (`../custom/cache`) and copies all custom plugins from `~/config/waypanel/plugins` to the cache before loading them.

---

### Plugin Structure

#### `get_plugin_placement(panel_instance)`

Defines where the plugin should be placed in the panel and its order of appearance. It returns a tuple `(position, order, priority)`:

- **Position**: `"top-panel-left"`, `"top-panel-right"`, `"top-panel-center"`, etc.
- **Order**: Determines the sequence of plugins within the same position.
- **Priority**: Determines the initialization order of plugins.

#### `initialize_plugin(panel_instance)`

Initializes the plugin and returns its instance.

---

### BasePlugin Class

All plugins should inherit from the `BasePlugin` class, which provides essential utilities and lifecycle methods.

#### Initialization

Call `super().__init__(panel_instance)` in the constructor to set up the plugin's connection to the panel instance.

#### Lifecycle Methods

Optional methods that can be overridden:

- `on_enable()`: Called when the plugin is enabled.
- `on_stop()`: Called when the plugin is stopped or disabled.
- `on_reload()`: Called when the configuration is reloaded.
- `on_cleanup()`: Called during cleanup to release resources.

---

### Defining the Main Widget

Plugins that add UI elements to the panel must define `self.main_widget`. This tells the `PluginLoader` how to integrate the plugin's widget into the panel.

#### Syntax

`self.main_widget = (widget, action)`

- **`widget`**: The widget to be added to the panel (e.g., a `Gtk.Button` or `Gtk.Box`).
- **`action`**: Specifies how the widget should be added:
  - `"append"`: Adds the widget to the specified panel section.
  - `"set_content"`: Sets the widget as the main content of a specific panel.

#### Background Plugins

If `get_plugin_placement()` returns `None`, the plugin is treated as a **background plugin** with no UI.

---

### Accessing Utilities

The `panel_instance` passed to the plugin provides access to various utilities:

- **Logger**: `self.logger` for logging messages.
- **IPC Client**: `self.ipc` for inter-process communication.
- **Configuration**: `self.config` for accessing plugin-specific settings from `waypanel.toml`.

---

### Dependencies

Plugins can specify dependencies using the `DEPS` list. The `PluginLoader` ensures that dependent plugins are loaded before the current plugin.

---

### Best Practices

1. **Keep Plugins Lightweight**:
   - Focus on a single responsibility for each plugin.
   - Avoid heavy computations in the main thread; use `GLib.idle_add()` for non-blocking tasks.

2. **Error Handling**:
   - Implement proper error handling to avoid crashing the entire plugin system.
   - Use the logger (`self.logger.error()`) to report issues.

3. **Configuration**:
   - Use `waypanel.toml` for plugin-specific settings only when necessary.
   - Load configuration using `self.config` and handle missing keys gracefully.

---

### Additional Notes

- **Logging**: Use the `logger` utility for consistent and structured logs.
- **Theming**: Custom CSS can be applied to widgets for styling.
- **Performance**: Waypanel is lightweight and avoids unnecessary monitoring of Bluetooth, network, etc.
- **some examples**: waypanel/src/plugins/examples
