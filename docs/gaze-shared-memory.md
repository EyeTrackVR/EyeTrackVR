# Gaze shared memory (v1)

EyeTrackVR publishes the latest gaze in a 256-byte shared memory block for
foveated rendering and foveated streaming integrations on the same PC. It is
on while **Settings → OSC → Foveated rendering gaze** is enabled, alongside any
VRChat output mode. The same toggle also sends VRChat-style
`/tracking/eye/LeftRightPitchYaw` to UDP 9020 for PimaxMagic4All.

- Definition: [`sdk/eyetrackvr_gaze.h`](../sdk/eyetrackvr_gaze.h), header-only C/C++. Copy it into a consumer as is.
- Writer: [`EyeTrackApp/osc/GazeSharedMemory.py`](../EyeTrackApp/osc/GazeSharedMemory.py)
- Reference reader: [`sdk/examples/etvr_gaze_dump.c`](../sdk/examples/etvr_gaze_dump.c)

Consumers:

| Tool | Transport | What it gives you |
|---|---|---|
| [OpenXR-Eye-Trackers](https://github.com/mbucchia/OpenXR-Eye-Trackers) (`eyetrackvr.cpp` backend) | shared memory | `XR_EXT_eye_gaze_interaction` for OpenXR games, Quad-Views-Foveated, OpenXR Toolkit. Used on any headset when the block exists at game start. |
| [PimaxMagic4All](https://github.com/mbucchia/PimaxMagic4All) | UDP 9020 + mutex `Local\eyetrackvr-osc-gaze` | Dynamic foveated rendering for D3D11 SteamVR (OpenVR) games |
| [EyeTrackVR OpenXR layer](../openxr_layer/README.md) | shared memory | `XR_EXT_eye_gaze_interaction` on runtimes without it: Monado, WiVRn, VDXR, WMR and others. Windows and Linux. Installed as an implicit layer while the toggle is on; steps aside where the runtime already has eye gaze. |
| [EyeTrackVR SteamVR driver](../steamvr_driver/README.md) | shared memory | SteamVR's own eye tracking input on any headset: `XR_EXT_eye_gaze_interaction` from SteamVR's OpenXR runtime, `Prop_SupportsXrEyeGazeInteraction_Bool` for OpenVR apps. Windows and Linux. Registered while the toggle is on. |

## Opening it

| OS | Name | API |
|---|---|---|
| Windows | `Local\EyeTrackVR.Gaze.v1` | `OpenFileMappingW(FILE_MAP_READ, ...)` + `MapViewOfFile` |
| Linux | `/eyetrackvr_gaze_v1` | `shm_open(..., O_RDONLY)` + `mmap` |

`Local\` is per login session, which covers games, SteamVR's `vrserver` and
OpenXR layers started by the same user. If the block doesn't exist, the
output is off: use fixed foveation and try again every second or so.

## Reading it

Call `etvr_gaze_read()`. It copies the block under a seqlock and accepts the copy
only when:

1. `seq` was even and unchanged across the copy (the writer makes it odd while updating),
2. magic is `ETVG`, version is 1 and size is 256,
3. the CRC-32 (zlib polynomial) of bytes 16..256 matches `crc32`.

Retry a few times on failure; an update takes microseconds. Then
`etvr_gaze_usable(&g, now_ns)` checks that a sample exists, the combined eye is
valid, and the sample was published within 100 ms.

## Fields

| Field | Meaning |
|---|---|
| `clock` | `1` = QueryPerformanceCounter in ns (Windows), `2` = `CLOCK_MONOTONIC` in ns (Linux) |
| `publish_time_ns` | When the writer stored this sample. Use it for staleness. |
| `sample_time_ns` | Camera capture time of the newest frame behind the sample. `now - sample_time_ns` is the end-to-end tracking latency; predict gaze forward by it if you extrapolate. |
| `sample_count` | +1 per sample, 0 before the first. |
| `eyes[0..2]` | Left, right, combined. |
| `direction` | Unit vector in head (HMD) space, OpenXR axes: +X right, +Y up, −Z forward. Calibrated but **unfiltered**: the tracker's output after calibration, flips and recenter, with none of the smoothing VRChat output gets (no running median, One-Euro, eye falloff, snap hold or blink hold). Do your own smoothing if you need it. |
| `openness` | 0 closed to 1 open. |
| `confidence` | 0 to 1. In v1 it is 1 for every valid sample. |
| `flags` | bit 0 gaze valid, bit 1 openness valid. |
| `fov_*_deg` | The calibrated angle range normalized gaze maps to, for information only. |

To turn a `*_time_ns` into an `XrTime`, convert back to the native unit and use
`xrConvertWin32PerformanceCounterToTimeKHR` (QPC ticks = ns × frequency / 1e9)
or `xrConvertTimespecTimeToTimeKHR`.

### Validity

- An eye whose lid is below 25 % open, or whose gaze is not finite, has gaze
  valid cleared. Its last direction stays in place but should not be used.
- The combined eye is the normalized average of the valid eyes, so it is still
  valid with one eye closed. It is invalid only when both are.
- When the output is turned off or EyeTrackVR quits, the writer first publishes
  a sample with every eye invalid. A reader still holding the mapping then sees
  "no gaze" at once, instead of having to wait 100 ms for the sample to go stale.

On loss of gaze, ease the foveal region back to the centre (fixed foveation)
instead of leaving it where the eye was.

## Versioning

New fields go into `reserved` and keep version 1. A layout change bumps
`version` and the mapping name (`...v2`). Readers must reject any version they
don't know.
