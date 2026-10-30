Linux aarch64 (Steam Frame) calibration overlay runtime (glibc 2.38 or newer).

Built from the overlay/ submodule by scripts/build_overlay.bat arm64 (an
Ubuntu 24.04 arm64 Docker container), which also writes OVERLAY_COMMIT.
Keep the executable, .so libraries, assets/ and licenses/ together.

The app and Linux PyInstaller bundle use this folder directly. A running
SteamVR/OpenXR headset runtime and the system's Vulkan graphics driver are
still required. Windows uses the existing .exe and DLL files in Tools/.

libopenvr_api.so here is the aarch64 build from ValveSoftware/openvr v2.12.14
(sha256 7fcdc649e5371c60530080c7ed3daef978daefd97304e1ff45b312aa344b3e76), the
same one the app bundles, not the overlay repository's external/OpenVR copy.
That older SDK build looks for its path registry in /data/work and so can't
find SteamVR on a Steam Frame (VRInitError_Init_PathRegistryNotFound).
