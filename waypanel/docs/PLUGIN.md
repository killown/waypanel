Managing Plugins:

1.  Plugin Loading:
    
    *   Plugins are automatically loaded from directories under `src/plugins`.
    *   The system looks for specific metadata in each plugin file.
2.  Configuration:
    
    *   Plugins can be enabled or disabled via a flag or by removing the plugin file.
    *   Use the `ENABLE_PLUGIN` flag to enable or disable individual plugins.
    *   Manage plugin dependencies using the `DEPS` list.
3.  Plugin Placement:
    
    *   Define plugin position and order using `get_plugin_placement(panel_instance)`.
    *   Positions can be "left", "right", "center", "systray", or "after-systray".
    *   Order determines the sequence of plugins within the same position.
4.  Initialization:
    
    *   Implement `initialize_plugin(panel_instance)` to initialize the plugin.
    *   This function should return the plugin instance.

Developing Plugins:

1.  Plugin Structure:
    
    *   Each plugin must define:
        *   `get_plugin_placement()` function
        *   `initialize_plugin(panel_instance)` function
        *   A plugin class that encapsulates its functionality
2.  Base Class:
    
    *   Inherit from `BasePlugin` class.
    *   Implement lifecycle methods if needed:
        *   `on_enable()`
        *   `on_stop()`
        *   `on_reload()`
        *   `on_cleanup()`
3.  UI Integration:
    
    *   Use `self.main_widget = (self.any_widget, "append")` to add widgets to the panel.
    *   Use `self.main_widget = (self.any_widget, "panel_set_content")` to set the content to a specific panel.
    use `get_plugin_placement()` to define which panel it should set the content:
    position = "left" for example.

4.  Event Handling:
    
    *   Subscribe to IPC events from Wayfire using the `EventManagerPlugin`.
    *   Handle events like "view-focused", "view-mapped", etc.
5.  Gestures:
    
    *   Define custom gestures (swipe, click) and associate them with callbacks.
6.  Dependencies:
    
    *   Specify dependencies using the `DEPS` list.
    *   Use `check_dependencies()` to ensure all dependencies are loaded.
7.  Reloading:
    
    *   Implement support for dynamic reloading if necessary.
    *   Use `reload_plugin(plugin_name)` for dynamic reloading.
8.  Configuration:
    
    *   Use `waypanel.toml` for plugin-specific configuration if needed.
    *   Load configuration using `_load_plugin_configuration()`.
9.  Error Handling:
    
    *   Implement proper error handling and logging.
    *   Use the provided logger for error messages and debugging information.
10.  Best Practices:
    
    *   Keep plugins lightweight and independent.
    *   Only implement configuration if necessary.
    *   Use GLib.idle\_add for non-blocking code execution.
    *   Test plugins thoroughly to avoid hanging the entire plugin system.
