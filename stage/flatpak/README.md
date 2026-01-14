# Waypanel Flatpak

This documentation covers the build and deployment process for the **Waypanel** Flatpak manifest. This manifest bundles Python 3.13, GTK4 Layer Shell, and essential Wayland utilities.

## Prerequisites

You must have `flatpak` and `flatpak-builder` installed on your host system. The build process requires the GNOME 49 SDK and Platform runtimes.

**Runtime Information:** This manifest targets `runtime-version: "49"`. Ensure you are using the **GNOME 49** branch for build compatibility.

### 1\. Install Runtimes and SDK

Execute the following commands to pull the necessary dependencies from Flathub:

    # Add Flathub remote if not already configured
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

    # Install GNOME 49 Sdk and Platform
    flatpak install flathub org.gnome.Platform//49 org.gnome.Sdk//49

## Build Instructions

Follow these steps to compile native modules and bundle the Python environment.

### 1\. Build the manifest

This command compiles `gtk4-layer-shell`, `playerctl`, and `wl-clipboard`, then installs the Python package stack via pip.

    flatpak-builder --force-clean --user build-dir org.waypanel.Waypanel.yaml

### 2\. Install Locally

Install the resulting build into your user's Flatpak installation:

    flatpak-builder --user --install --force-clean build-dir org.waypanel.Waypanel.yaml

## Running Waypanel

Launch the panel from the sandboxed environment:

    flatpak run org.waypanel.Waypanel

## Sandbox Configuration

Waypanel is configured with specific permissions to interact with the host Wayland compositor:

- **Graphics & Sound:** `wayland`, `fallback-x11`, `dri`, and `pulseaudio`.
- **Filesystem Access:**
  - `host:ro`: Read-only access to host system icons and desktop files.
  - `xdg-config/waypanel`: Custom configuration storage.
  - `~/.local/share/waypanel`: Persistent data and theme assets.
- **D-Bus Communication:**
  - `org.freedesktop.Notifications`: System notification support.
  - `org.mpris.MediaPlayer2.*`: Media player controls.
  - `org.kde.StatusNotifierWatcher`: System tray/SNI monitoring.

## Development and Troubleshooting

To enter a shell within the build environment to verify `PYTHONPATH` or library paths:

    flatpak-builder --run build-dir org.waypanel.Waypanel.yaml sh
