# EyeTrackVR SteamVR gaze driver

Feeds EyeTrackVR's gaze into SteamVR's eye tracking input on **any** headset, so:

- SteamVR's OpenXR runtime offers `XR_EXT_eye_gaze_interaction` (`/user/eyes_ext/input/gaze_ext/pose`)
  to OpenXR games and tools (Quad-Views-Foveated, OpenXR Toolkit, native eye-tracked foveation);
- OpenVR apps see `Prop_SupportsXrEyeGazeInteraction_Bool` on the HMD (PimaxMagic4All's
  OpenVR eye tracker uses it).

It reads the gaze shared memory ([docs/gaze-shared-memory.md](../docs/gaze-shared-memory.md))
and does nothing unless EyeTrackVR's **Foveated rendering gaze** output is on. EyeTrackVR
registers it with SteamVR while that toggle is on (`EyeTrackApp/OVR/SteamVRDriverRegistration.py`).
SteamVR loads drivers at startup, so restart SteamVR after changing the toggle.

## How it attaches to another vendor's HMD

SteamVR only creates driver input components on a device's property container. The headset
belongs to its own driver (lighthouse, Bigscreen, Pimax, Virtual Desktop, Steam Link...), so
this driver has no device of its own and attaches an `/eyetracking` component to the HMD:

1. **Shim** (normal path): at `Init` it patches slot 0 of the shared
   `IVRServerDriverHost` vtable (`TrackedDeviceAdded`). When the headset's driver registers its
   HMD, the HMD is wrapped in a forwarding proxy; right after the HMD's own `Activate()` the
   component is created. Bigscreen's own Beyond eye tracking driver uses the same technique.
2. **Direct**: if the HMD was registered before this driver loaded, it attaches on the next
   `RunFrame`.

Each route logs its result to `vrserver.txt` (`eyetrackvr: Attach via shim|direct ... -> <error>`).
If SteamVR refuses cross-driver components the log says `PermissionDenied`; nothing else changes.

`Prop_SupportsXrEyeGazeInteraction_Bool` follows whether EyeTrackVR is publishing gaze (checked
once a second), so apps started without EyeTrackVR keep their normal fixed-foveation path.

Gaze goes to `UpdateEyeTrackingComponent` as origin `(0,0,0)` and a target 1 m along the combined
gaze direction in HMD space, with `fTimeOffset` = −(now − camera capture time).

The vtable patch is a plain pointer swap (no Detours), so it works the same on Windows (MSVC) and
Linux (Itanium ABI): `TrackedDeviceAdded` is slot 0 in both, and `IVRServerDriverHost` has no
virtual destructor.

## Building

```bash
cmake -S steamvr_driver -B build/steamvr_driver -DCMAKE_BUILD_TYPE=Release
```

```bash
cmake --build build/steamvr_driver --config Release
```

Output: `build/steamvr_driver/eyetrackvr/` (`bin/win64/driver_eyetrackvr.dll` or
`bin/linux64/driver_eyetrackvr.so`, plus the manifest). Running from source, EyeTrackVR registers
that folder. Release builds (`build_release.bat`, `scripts/build_linux.sh`) ship it as
`steamvr_driver/eyetrackvr/` beside the app executable.

On Linux the `.so` links libstdc++ statically, exports only `HmdDriverFactory`, and opens
`/dev/shm/eyetrackvr_gaze_v1` directly. Built on Ubuntu 22.04 it needs glibc 2.34+, the same as
the app.

## Testing without SteamVR

`-DETVR_DRIVER_TESTS=ON` also builds `fake_vrserver`. It loads the real driver binary, registers
a fake HMD through an interface pointer the way a headset driver does, runs frames, and prints
every `CreateEyeTrackingComponent` and `UpdateEyeTrackingComponent` call:

```bash
fake_vrserver build/steamvr_driver/eyetrackvr/bin/linux64/driver_eyetrackvr.so shim 100
```

Modes: `shim` (HMD added after the driver loads), `direct` (before), and a trailing `deny` to make
the HMD refuse other drivers' writes. Publish gaze with EyeTrackVR's toggle on (or
`osc/GazeSharedMemory.py`) while it runs.

## Testing in SteamVR

`tests/xr_gaze_probe.cpp` (Windows, D3D11) creates an OpenXR session on the active runtime, checks
`supportsEyeGazeInteraction`, and prints the forward vector of `/user/eyes_ext/input/gaze_ext/pose`.
With the driver registered, SteamVR running with a headset, and gaze published, it should report
`supportsEyeGazeInteraction=1` and a forward vector that follows the published direction.

## Not covered: Monado, WiVRn, other OpenXR runtimes

SteamVR drivers only load in SteamVR. Monado's `steamvr_lh` hosts only Valve's lighthouse (and
optionally SlimeVR) driver, and its eye tracking entry points are stubs. For those runtimes, use the
[OpenXR eye gaze layer](../openxr_layer/README.md), which reads the same shared memory.
