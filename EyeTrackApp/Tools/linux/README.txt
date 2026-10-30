Linux x86_64 calibration overlay runtime (Ubuntu 22.04 / glibc 2.35 or newer).

Built from the overlay/ submodule by scripts/build_overlay.bat linux (or
`bash scripts/build_overlay.sh` on Linux), which also writes OVERLAY_COMMIT.
Keep the executable, .so libraries, assets/ and licenses/ together.

The app and Linux PyInstaller bundle use this folder directly. A running
SteamVR/OpenXR headset runtime and the system's Vulkan graphics driver are
still required. Windows uses the existing .exe and DLL files in Tools/.
