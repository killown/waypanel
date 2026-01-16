def get_manager():
    from .providers import (
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
            config = config or {}
            all_potential = [
                PacmanProvider(config.get("pacman")),
                DnfProvider(config.get("dnf")),
                AptProvider(config.get("apt")),
                ZypperProvider(config.get("zypper")),
                XbpsProvider(config.get("xbps")),
                ApkProvider(config.get("apk")),
                FlatpakProvider(config.get("flatpak")),
            ]
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
