# Universal Update

A modular orchestration engine for managing system updates across multiple Linux distributions and package managers.

## Features

- **Multi-Backend**: Supports Pacman, DNF, APT, Zypper, XBPS, APK, and Flatpak.
- **Asynchronous Polling**: Checks for updates in the background without freezing the UI.
- **Atomic Overrides**: Customize the update command for each specific manager.
- **Auto-Detection**: Only activates managers found in the system `$PATH`.

## Dependencies

The plugin requires the following binaries depending on your distribution:

- Arch: `pacman`, `pacman-contrib` (for `checkupdates`)
- Fedora: `dnf`
- Ubuntu/Debian: `apt`, `apt-get`
- openSUSE: `zypper`
- Void: `xbps-install`
- Alpine: `apk`
- Cross-distro: `flatpak`

## Configuration

Settings are located in `actions` and `commands` namespaces:

| Key                             | Default            | Description                        |
| :------------------------------ | :----------------- | :--------------------------------- |
| `commands/pacman`               | `sudo pacman -Syu` | Override the Pacman update string. |
| `timing/check_interval_seconds` | `3600`             | How often to poll for updates.     |

## Development

To add a new provider, implement the `UpdateProvider` interface in `providers.py`.
