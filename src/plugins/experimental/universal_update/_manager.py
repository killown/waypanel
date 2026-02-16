def get_manager():
    from ._providers import (
        PacmanProvider,
        DnfProvider,
        AptProvider,
        ZypperProvider,
        XbpsProvider,
        ApkProvider,
        FlatpakProvider,
    )

    class UniversalUpdateManager:
        def __init__(self, config: dict | None = None):
            import os

            config = config or {}

            distro_id = "unknown"
            try:
                if os.path.exists("/etc/os-release"):
                    with open("/etc/os-release", "r") as f:
                        for line in f:
                            if line.startswith("ID="):
                                # We add .lower() to ensure 'Fedora' matches 'fedora'
                                distro_id = (
                                    line.strip().split("=")[1].strip('"').lower()
                                )
                                break
            except Exception:
                pass

            all_potential = []

            # STRICT LOGIC based on your successful test
            if distro_id == "fedora":
                all_potential.append(DnfProvider(config.get("dnf")))
            elif distro_id == "arch":
                all_potential.append(PacmanProvider(config.get("pacman")))
            elif distro_id in ["debian", "ubuntu", "pop"]:
                all_potential.append(AptProvider(config.get("apt")))
            elif distro_id in ["opensuse", "suse"]:
                all_potential.append(ZypperProvider(config.get("zypper")))
            elif distro_id == "void":
                all_potential.append(XbpsProvider(config.get("xbps")))
            elif distro_id == "alpine":
                all_potential.append(ApkProvider(config.get("apk")))
            else:
                # Fallback for unknown distros
                all_potential.extend(
                    [
                        PacmanProvider(config.get("pacman")),
                        DnfProvider(config.get("dnf")),
                    ]
                )

            # Always add Flatpak
            all_potential.append(FlatpakProvider(config.get("flatpak")))

            # Final filter: verify the binary actually exists
            self.active_providers = [p for p in all_potential if p.is_available()]

        async def check_all(self, asyncio_lib, subprocess_lib, timeout: int) -> int:
            import asyncio

            tasks = [
                p.get_update_count(asyncio_lib, subprocess_lib, timeout)
                for p in self.active_providers
            ]
            results = await asyncio.gather(*tasks)
            return sum(results)

        def get_combined_command(self) -> str:
            commands = [p.get_update_command() for p in self.active_providers]
            return " && ".join(commands) if commands else "echo 'No managers found'"

    return UniversalUpdateManager
