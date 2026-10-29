# EyeTrackVR OpenXR eye gaze layer

`XR_APILAYER_EYETRACKVR_eye_gaze` is an implicit OpenXR API layer that gives runtimes without eye
tracking `XR_EXT_eye_gaze_interaction`, fed by EyeTrackVR's gaze shared memory
([docs/gaze-shared-memory.md](../docs/gaze-shared-memory.md)). It targets Monado, WiVRn, Envision
setups, Virtual Desktop's VDXR, WMR and other non-SteamVR runtimes, on Linux and Windows. It needs
no graphics API and no hooking library.

On SteamVR, use the [SteamVR driver](../steamvr_driver/README.md), which feeds SteamVR's own eye
tracking input. Once SteamVR offers the extension, this layer steps aside.

## What it does

The layer does nothing unless the app enables `XR_EXT_eye_gaze_interaction` **and** the runtime
below doesn't already offer it. `ETVR_GAZE_LAYER_FORCE=1` overrides the second condition. When it
is active, it:

- **Extensions:** declares the extension in its manifest, so the loader lists it, and hides it from
  the runtime's `xrCreateInstance`. If the runtime can convert times, it also enables
  `XR_KHR_convert_timespec_time` or `XR_KHR_win32_convert_performance_counter_time`, for gaze sample
  times.
- **Support flag:** sets `supportsEyeGazeInteraction` only while EyeTrackVR publishes gaze. It takes
  that struct out of the chain before calling the runtime, so strict runtimes don't reject it.
- **Paths:** takes the `/interaction_profiles/ext/eye_gaze_interaction` bindings and the
  `/user/eyes_ext` subaction path, both of which the runtime would reject.
- **Gaze pose:** locates gaze pose action spaces as the session's VIEW pose × the gaze rotation ×
  `poseInActionSpace`. The gaze ray starts at the VIEW origin, between the eyes. This works through
  `xrLocateSpace`, `xrLocateSpaces` (1.1) and `xrLocateSpacesKHR`.
- **Sample time:** fills `XrEyeGazeSampleTimeEXT` with the camera capture time.
- **Input queries:** answers `xrGetActionStatePose` (active while gaze is available),
  `xrGetCurrentInteractionProfile(/user/eyes_ext)`, `xrEnumerateBoundSourcesForAction` and
  `xrGetInputSourceLocalizedName` for the gaze source.
- **No gaze:** during blinks, lost tracking, or with EyeTrackVR closed, gaze spaces report no
  location flags. Apps then fall back to their non-eye-tracked path.

It serves one instance at a time; a second concurrent instance is passed through untouched.
`DISABLE_XR_APILAYER_EYETRACKVR_eye_gaze=1` turns the layer off for one app.
`ETVR_GAZE_LAYER_QUIET=1` silences its stderr lines.

## Installation

EyeTrackVR installs the layer while **Foveated rendering gaze** is on, and removes it when the toggle
is turned off and on uninstall (`EyeTrackApp/OVR/OpenXRLayerRegistration.py`). It is per user, with
no admin rights:

| OS | Where |
|---|---|
| Windows | `HKCU\SOFTWARE\Khronos\OpenXR\1\ApiLayers\Implicit`: value = path of the bundled manifest, `0` = enabled. The loader ignores HKCU for elevated processes. |
| Linux | `$XDG_DATA_HOME/openxr/1/api_layers/implicit.d/XR_APILAYER_EYETRACKVR_eye_gaze.json` (default `~/.local/share/...`), with an absolute `library_path` |

Games read the layer list when they start.

## Building

```bash
cmake -S openxr_layer -B build/openxr_layer -DCMAKE_BUILD_TYPE=Release
```

```bash
cmake --build build/openxr_layer --config Release
```

The output, `build/openxr_layer/eyetrackvr_openxr_layer/`, holds the library and its manifest. On
Linux the `.so` links libstdc++ statically and exports only `xrNegotiateLoaderApiLayerInterface`.

## Testing

`-DETVR_LAYER_TESTS=ON` builds two test tools:

- `fake_runtime`: a strict OpenXR runtime. It has no eye gaze and rejects `/user/eyes_ext`, the eye
  gaze profile and unknown structs. Its head is placed and rotated, so pose composition is checked.
- `gaze_probe`: a headless app that uses eye gaze like a game and prints `key=value` lines. With
  `ETVR_PROBE_VULKAN=1` (Linux, built with Vulkan) it uses a Vulkan session instead. Runtimes that
  don't focus headless sessions, such as older Monado, need this.

Run without an OpenXR loader, chaining the layer and runtime directly:

```bash
gaze_probe 40 --direct eyetrackvr_openxr_layer/libXR_APILAYER_EYETRACKVR_eye_gaze.so tests/fake_runtime.so
```

Or through the system loader:

```bash
XR_RUNTIME_JSON=tests/fake_runtime.json XR_API_LAYER_PATH=eyetrackvr_openxr_layer XR_ENABLE_API_LAYERS=XR_APILAYER_EYETRACKVR_eye_gaze gaze_probe 40
```

Publish gaze while it runs, with EyeTrackVR's toggle on or with `EyeTrackApp/osc/GazeSharedMemory.py`.
