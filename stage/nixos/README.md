# Waypanel Nix Package

This documentation provides details for the **Waypanel** Nix derivation, a highly customizable status bar for Wayland compositors.

## Included Features

- **GTK4 Layer Shell:** Native support for desktop surface layering via `gtk4-layer-shell`.
- **Media Control:** Full integration with `playerctl` for MPRIS support.
- **Audio Management:** Includes `libpulseaudio` and `soundcard` integration.
- **System Utilities:** Bundled with `wl-clipboard` and `git` for internal plugin functionality.
- **Optimized Environment:** Automatic configuration of `GI_TYPELIB_PATH` and `WAYPANEL_GTK_LAYER_SHELL_PATH`.

## Build Instructions

### 1\. Build via Command Line

To compile the package and generate a `result` symlink in your current directory, execute:

    nix-build -E 'with import <nixpkgs> {}; callPackage ./package.nix {}'

### 2\. Testing the Build

You can execute the panel directly from the Nix store path without installing it system-wide:

    ./result/bin/waypanel

### 3\. Installation on NixOS

To add Waypanel to your permanent system configuration, reference the derivation in your `environment.systemPackages`:

    # configuration.nix
    { pkgs, ... }:
    let
      waypanel = pkgs.callPackage ./path/to/waypanel.nix {};
    in
    {
      environment.systemPackages = [
        waypanel
      ];
    }

### 4\. Development Environment

To enter a shell containing all C libraries and Python dependencies for manual debugging:

    nix-shell -E 'with import <nixpkgs> {}; (callPackage ./package.nix {}).overrideAttrs (old: { nativeBuildInputs = old.nativeBuildInputs ++ [ python3Packages.ipython ]; })'

**Note:** Ensure Wayfirse has ipc, ipc-rules and stipc plugins.
