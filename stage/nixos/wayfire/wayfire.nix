{ lib
, stdenv
, fetchgit
# --- Build Tools ---
, cmake
, meson
, ninja
, pkg-config
# --- Wayland & Graphics Stack ---
, cairo
, libGL
, libdrm
, pango
, vulkan-headers
, wayland
, wayland-protocols
, wayland-scanner
, wlroots_0_19
# --- Input & System Libraries ---
, doctest
, glm
, libevdev
, libexecinfo
, libinput
, libjpeg
, libxkbcommon
, libxml2
, wf-config
, xorg
, yyjson
}:

stdenv.mkDerivation (finalAttrs: {
  pname = "wayfire";
  version = "0.11.0-dev-${lib.substring 0 7 (finalAttrs.src.rev or "master")}";

  src = fetchgit {
    url = "https://github.com/WayfireWM/wayfire.git";
    rev = "refs/heads/master";
    fetchSubmodules = true;
    hash = "sha256-XAvQba6heVZKj7AgEn5UxM7HI/LpGneOsbWdfulpp0U=";
  };

  nativeBuildInputs = [
    cmake
    meson
    ninja
    pkg-config
    wayland-scanner
  ];

  buildInputs = [
    # Core Graphics & Display
    cairo
    libGL
    libdrm
    pango
    vulkan-headers
    wayland
    wayland-protocols
    wlroots_0_19
    xorg.xcbutilwm

    # Input, Compression & Logic
    doctest
    glm
    libevdev
    libexecinfo
    libinput
    libjpeg
    libxkbcommon
    libxml2
    yyjson
  ];

  NIX_CFLAGS_COMPILE = "-I${lib.getDev libdrm}/include/libdrm";

  mesonFlags = [
    "--sysconfdir=/etc"
    (lib.mesonEnable "use_system_wlroots" true)
    (lib.mesonEnable "use_system_wfconfig" false)
    (lib.mesonEnable "xwayland" true)
    (lib.mesonEnable "wf-touch:tests" (stdenv.buildPlatform.canExecute stdenv.hostPlatform))
  ];

  dontUseCmakeConfigure = true;

  doCheck = true;

  passthru.providedSessions = [ "wayfire" ];

  meta = with lib; {
    homepage = "https://wayfire.org/";
    description = "Next-generation 3D Wayland compositor (Master Branch)";
    license = licenses.mit;
    platforms = platforms.linux;
    mainProgram = "wayfire";
  };
})
