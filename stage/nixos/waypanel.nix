{ lib
, buildPythonPackage
, fetchFromGitHub
, setuptools
, wrapGAppsHook3
, gobject-introspection
# C Libraries
, gtk4-layer-shell
, playerctl
, libpulseaudio
# Python Deps
, pywayland
, py-cpuinfo
, pyyaml
, requests
, pygobject3
, aiohttp
, beautifulsoup4
, numpy
, psutil
, pulsectl
, soundcard
, toml
, colorama
, dbus-next
, dbus-fast
, orjson
, cffi
, watchdog
, pyperclip
, aiosqlite
, pillow
, structlog
, rich
, pygments
, cairosvg
, unidecode
, rapidfuzz
, lazy-loader
, distro
, tldextract
# Extra Tools
, wl-clipboard
, git
}:

buildPythonPackage rec {
  pname = "waypanel";
  version = "unstable-2024-01-18";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "killown";
    repo = "waypanel";
    rev = "master";
    hash = "sha256-s2Z4Nz/kq8ZDYs/sJ5GKbPyNOhNaSA6UENfaVFv/oGo=";
  };

  build-system = [ setuptools ];

  nativeBuildInputs = [
    wrapGAppsHook3
    gobject-introspection
  ];

  buildInputs = [
    gtk4-layer-shell
    playerctl
    libpulseaudio
  ];

  dependencies = [
    pywayland py-cpuinfo pyyaml requests pygobject3
    aiohttp beautifulsoup4 numpy psutil pulsectl
    soundcard toml colorama dbus-next dbus-fast
    orjson cffi watchdog pyperclip aiosqlite
    pillow structlog rich pygments cairosvg
    unidecode rapidfuzz lazy-loader distro tldextract
  ];

  makeWrapperArgs = [
    "--prefix PATH : ${lib.makeBinPath [ git wl-clipboard ]}"
    "--set WAYPANEL_GTK_LAYER_SHELL_PATH ${gtk4-layer-shell}/lib/libgtk4-layer-shell.so"
    # GI_TYPELIB_PATH is needed so Python can find the 'Playerctl' and 'Gtk4LayerShell' metadata
    "--prefix GI_TYPELIB_PATH : ${lib.makeSearchPath "lib/girepository-1.0" [ playerctl gtk4-layer-shell ]}"
  ];

  doCheck = false;

  meta = with lib; {
    description = "A highly customizable status bar for Wayland compositors";
    homepage = "https://github.com/killown/waypanel";
    license = licenses.mit;
    platforms = platforms.linux;
    mainProgram = "waypanel";
  };
}
