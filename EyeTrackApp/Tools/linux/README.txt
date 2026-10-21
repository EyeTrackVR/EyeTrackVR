Linux x86_64 calibration overlay runtime (Ubuntu 22.04 / glibc 2.35 or newer).

Built in the sibling EyeTrackVR-OpenVR-Calibration-Overlay repository using
`bash build-linux.sh`. To update, copy its build-linux/package/ contents here.
Keep the executable, .so libraries, assets/ and licenses/ together.

The app and Linux PyInstaller bundle use this folder directly. A running
SteamVR/OpenXR headset runtime and the system's Vulkan graphics driver are
still required. Windows uses the existing .exe and DLL files in Tools/.
