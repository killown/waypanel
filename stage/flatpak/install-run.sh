rm -rf build* .flatpak-builder/
flatpak-builder --user --install --force-clean build-dir org.waypanel.Waypanel.yaml
flatpak run org.waypanel.Waypanel
