echo "Running post-install script..."
cd /tmp/
git clone https://github.com/wmww/gtk4-layer-shell
cd gtk4-layer-shell/
meson setup --prefix=~/.local/lib/gtk4-layer-shell -Dexamples=true -Ddocs=true -Dtests=true build
ninja -C build
ninja -C build install
