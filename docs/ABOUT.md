The `waypanel` application's core structure is built around a main execution flow and a central `Panel` class. This class is responsible for managing the entire application's lifecycle and its UI components.

### Startup Process and Key Components

1.  **Environment Setup**: The application begins with `run.py`, which sets up the environment. This includes:
    - Identifying the correct installation paths.
    - Loading the essential `libgtk4-layer-shell.so` library for the graphical interface.
    - Setting up the virtual environment and installing dependencies from `requirements.txt`.
    - Ensuring a `config.toml` file exists, which is the primary configuration file.

2.  **Application Initialization**: The `main.py` script takes over after the environment is ready. Its key tasks are:
    - Setting up logging.
    - Initializing an IPC (Inter-Process Communication) socket.
    - Starting a separate thread for an IPC server to handle communication.
    - Verifying and enabling required Wayfire plugins.
    - Creating an instance of the central `Panel` class.

3.  **The Panel Class**: Located in `src/panel.py`, this class is the core of the application. It inherits from `Adw.Application` and is responsible for:
    - **Configuration Management**: It loads and manages the `config.toml` file, which is described as the "single source of truth for the application's state and appearance." It also provides methods to save and reload the configuration dynamically.
    - **UI Creation**: The `setup_panels()` method acts as a factory, using the configuration to create the user interface. It can create panels for different screen positions (e.g., top, bottom, left, right).
    - **Plugin Management**: It uses a `PluginLoader` to load plugins asynchronously, which ensures the UI remains responsive during startup. The `on_activate` method uses `GLib.idle_add` to facilitate this process.

### Interactions and Modularity

- **`config.toml`**: This file is central to how the application behaves and appears. It controls which panels are active, their placement, and how plugins are configured.
- **Plugins**: `waypanel` is designed to be modular. Plugins are separate components that add widgets to the panels. The `PluginLoader` handles their integration, and they can be designed to react to configuration changes.
- **IPC**: The application uses an IPC server to allow external processes to interact with it, enabling features like sending commands or events to the running application.
