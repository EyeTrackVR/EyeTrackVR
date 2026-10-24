# Steam Frame release (FrameDrop)

EyeTrackVR ships a native Linux ARM64 build for Valve's Steam Frame. Users install it with
[FrameDrop](https://framedropvr.com/), which unpacks the zip, uploads it to a paired headset and
adds it to the headset's Steam library as **EyeTrackVR**.

## What gets built

| Artifact | Purpose |
| --- | --- |
| `EyeTrackVR-<version>-steamframe-arm64.zip` | PyInstaller onedir bundle in an `EyeTrackVR/` wrapper folder |
| `EyeTrackVR-<version>-steamframe.framedrop.json` | `framedrop.install/v1` manifest pointing at the zip on the GitHub release, with its sha256 |

Both are produced by [`scripts/build_frame.sh`](../scripts/build_frame.sh):

* **Locally:** `build_release.bat` step 5 builds `scripts/frame/Dockerfile` (Ubuntu 24.04 arm64)
  and runs the build in it. Docker Desktop must be running. On an x86 PC it runs under QEMU, so
  expect it to take a lot longer than the x86 Linux build. The `etvr-frame-cache` volume keeps
  Python and the pip cache between runs. The build uses a pinned standalone CPython plus pip
  instead of uv, because uv and GNU tar fail to create files under Docker Desktop's QEMU
  emulation (see `scripts/frame/install_python.sh`).
  Docker Desktop and the WSL distros share one kernel, so they also share the binfmt_misc
  registrations. When the Ubuntu-22.04 build distro idles out (~20 s after step 4), every
  registration is dropped, including Docker's arm64 QEMU handler. The Frame build then dies
  partway with `Exec format error`. To prevent that, `build_release.bat` terminates the distro
  first, which doesn't drop them. It then re-registers QEMU with `tonistiigi/binfmt` and checks
  that an arm64 container runs. Don't start or stop other WSL distros during step 5. If emulation
  ever breaks outside the script, run
  `docker run --privileged --rm tonistiigi/binfmt --install arm64` to restore it.
* **CI:** the `build-frame` job in `.github/workflows/build.yml` runs the same script natively on
  GitHub's `ubuntu-24.04-arm` runner.

### Why these choices

* **glibc 2.39 / Ubuntu 24.04.** FrameDrop launches Linux titles in *Steam Linux Runtime 4.0
  ARM64* (glibc 2.41), and the Frame's own SteamOS has glibc 2.39. Building on 24.04 runs in both.
  It is also the oldest base the PySide6 aarch64 wheels (`manylinux_2_39`) install on. The script
  fails the build if the bundle needs a newer glibc.
* **`eyetrackvr` is the only executable at the zip's top level.** FrameDrop uses the top-level
  binary as the Steam start command.
* **Symlinks are dereferenced, and the build fails on case-colliding paths.** FrameDrop unpacks
  the zip on Windows (NTFS) before uploading, and NTFS can't recreate those.
* **OpenVR.** The pyopenvr wheel only bundles x86 libraries, so the build fetches the aarch64
  `libopenvr_api.so` from ValveSoftware/openvr `v2.12.14` (hash-pinned). Without it, SteamVR
  auto-start and quit-with-SteamVR don't work.

## Publishing a release

1. Run `build_release.bat` and upload everything in `release/<version>/` to the GitHub release
   tagged **`EyeTrackApp-<version>`**. The manifest's URLs assume that tag. To host elsewhere, set
   `ETVR_RELEASE_BASE_URL` for `build_frame.sh`.
2. Put the install button in the release notes and docs. The build prints the link as
   `FRAMEDROP_LINK=...`. It has this shape:

   ```
   https://framedropvr.com/install?manifest=https%3A%2F%2Fgithub.com%2FEyeTrackVR%2FEyeTrackVR%2Freleases%2Fdownload%2FEyeTrackApp-<version>%2FEyeTrackVR-<version>-steamframe.framedrop.json
   ```

   A Markdown button for release notes:

   ```markdown
   [**Install on Steam Frame with FrameDrop**](<FRAMEDROP_LINK>)
   ```

   The self-contained HTML button from the [FrameDrop docs](https://framedropvr.com/docs) works on
   web pages. Keep the plain zip download next to it, as FrameDrop recommends.

Releases are published as GitHub *pre-releases*. `releases/latest/download/...` never resolves to
those, so each release links its own versioned manifest.

## Installing (users)

1. On the Frame: **Settings → System → Developer Mode**. Then **Settings → Developer → Pair new
   host**, and pair it with FrameDrop on the PC.
2. Click **Install with FrameDrop** on the release page, or drop the zip onto FrameDrop.
3. Start **EyeTrackVR** from the headset's Steam library.

Settings are kept in `~/.config/EyeTrackVR` on the headset, and logs go to `logs/` inside the
install folder (`~/devkit-game/<name>/EyeTrackVR/logs` for a FrameDrop install).

Without FrameDrop, use the SteamOS Devkit Client's Title Upload. Set Start Command to `eyetrackvr`
and Runtime to *Steam Linux Runtime 4.0 ARM64*.

## Current limitations

* **In-VR calibration overlay.** `EyeTrackApp/Tools/linux-arm64/` holds an aarch64 build of the
  overlay runtime, which the spec bundles as `Tools/linux/` (the folder the app looks in). It was
  built with the overlay repository's `build-linux.sh` in the `etvr-frame-builder` image. That
  build needs the overlay CMake's `linuxarm64` OpenVR support and these extra packages:
  `libvulkan-dev libopenxr-dev libopenxr-loader1 libstb-dev patchelf`. Its `libopenvr_api.so` is
  replaced with the OpenVR v2.12.14 aarch64 library the app uses. The SDK copy in the overlay
  repository looks for its path registry in `/data/work`, so it fails on the Frame with
  `VRInitError_Init_PathRegistryNotFound`. On the headset the overlay attaches to SteamVR as an
  OpenVR overlay over the running app.
* **Camera sources.** The usual network (ESP32/OpenIris) camera sources work too, in ETVR mode.

## Built-in eye cameras ("Steam Frame" setup mode)

On the headset, the Tracking tab offers a third setup type, **Steam Frame**, next to ETVR and
Bigscreen Beyond. It's picked automatically on first launch when no camera is configured. It pins
the sources to `frame://left` and `frame://right` and starts tracking without a Connect step. The
option is hidden on a PC, which has no way to reach the cameras.

[`EyeTrackApp/frame_eye.py`](../EyeTrackApp/frame_eye.py) reads them from Valve's `dsp_service`. That
service is unprivileged and undocumented. The protocol was learned from Project Babble's
Babble-Frame-Runtime and the Frame-Reverse-Eng notes, then reimplemented here independently:

* Connect to the abstract unix socket `@dsp_service`. It passes a 16 MB dma-buf, and the client
  sends request type `0` (shared memory only).
* Map the control block the way Babble does, at file offset `0x80000000` of that dma-buf, falling
  back to offset 0 (on a 2026-10 retail unit both show the same memory). Probe for it at `0x234000`,
  then `0x124000`. The probe validates the index, lock, enable and fps words and writes nothing
  until the layout checks out.
* Map the memory read-only and only watch it. Poll the two ring indices, skip the slots already
  in the ring at connect time (they are stale), and copy each new 512x512 slot. Nothing is ever
  written back. See [Sharing the cameras with SteamVR](#sharing-the-cameras-with-steamvr).
* One process-wide reader thread feeds both eyes. The DSP puts a 400x400 image inside each slot
  and zero-fills the rest. On 2026-10 retail firmware the image sits at x=64, y=0, but the position
  differs on other firmware. So the reader finds the image box on the first frame of each
  connection and publishes only that box. Without the crop, the camera view had black bars on the
  right and bottom.
* The left camera is mounted rotated 180 degrees from the right one, so the left image is turned
  upright before it is published.
* The ring Babble calls `ring_l` is the **wearer's right** eye (closed-eye test in
  Frame-Reverse-Eng), so `frame://left` reads `ring_r`.

### Sharing the cameras with SteamVR

SteamVR's `eyetracking` process owns the cameras. Each slot's lock word shows where that slot is:

| Lock | Meaning |
| --- | --- |
| `1` | Free |
| `4` | Queued to the camera |
| `8`, `2` | Filled, being claimed or read by SteamVR's tracker |

SteamVR's tracker claims each filled slot itself and frees it when it's done. Babble's reader, which
an earlier version of this one copied, writes `1` to a slot as soon as it sees it. That takes the
frame away from SteamVR's tracker: its log fills with `CEyeTracker: Timed out waiting for image` and
`Failed to grab cdsp input buffer`. It can also hand the DSP a slot that SteamVR is still reading. The
reader also used to write the `enables` and `transition` words. Those writes do nothing useful:
frames flow with both `enables` at 0 while SteamVR drives the cameras.

### Camera frame rate

SteamVR picks the camera rate, and it changes with what is running:

* **15 fps** with no VR app running, for example while EyeTrackVR is open on the headset's desktop.
* **36–72 fps** while a VR app runs. The headset's logs show 72, 60, 54, 45 and 36.

The rate shows up as `CStereoAdspCams: Set framerate` in
`~/.local/share/Steam/logs/eyetracking.txt`, and the app logs it as `Steam Frame eye camera rate`.
Writing the rate words in the control block changes nothing, because they only mirror the rate
SteamVR set through `dsp_service`. So 15 fps on the desktop is expected, not an app or CPU limit.

### Requirement: SteamVR eye tracking must be on

The cameras are only ever set up by SteamVR's own eye tracker. If eye tracking is turned off in
SteamVR settings (`"allowEyeTracking" : false` under `"steamvr"` in
`~/.config/openvr/config/steamvr.vrsettings`), the `eyetracking` process never starts, the
camera-rate word stays 0, and no app can get frames. Babble Frame Runtime has the same dependency.
The app then shows **"Eye tracking is off in SteamVR settings"** and checks again every 2 s, so
frames start shortly after it's turned back on. Other "not set up yet" states show **"Waiting for
SteamVR eye tracking to start"**.

### When frames stop

SteamVR's own eye tracker runs the cameras, and only while the headset is worn. The journal logs
"HMD on, starting eye tracking" and "HMD off, stopping eye tracking". So a gap in frames is normal,
not a broken connection:

* The reader keeps its mapping and waits, and the cameras show **"Waiting for the eye cameras (put
  the headset on)"**. Frames resume on the same connection once SteamVR starts the cameras again.
* It reconnects only when `dsp_service` closes the socket or the index words go out of range three
  times in a row, backing off 5 s → 60 s like Babble.
* An earlier version wrote the enable words back to 0 on every reconnect. That cut off the streams
  SteamVR was using and caused a "Reconnecting..." loop every 3–5 s.

* **Inference is CPU-only** (CPU onnxruntime, same as the x86 Linux bundle).
