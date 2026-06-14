"""UVC camera enumeration with stable per-device addresses.

The goal is letting users pick a webcam by *name* rather than by cv2 integer
index, so unplug/replug or a new USB device doesn't silently swap which camera
each eye tracks. Each scan returns a ``name`` (friendly, e.g. "OBS Virtual
Camera") and an ``address`` (per-OS stable id: DirectShow device path on
Windows, ``/dev/v4l/by-id/...`` symlink on Linux, AVFoundation unique-id on
macOS). The capture-source resolver in ``camera.py`` accepts a string of the
form ``uvc:<name>@<address>`` and re-runs this scan to translate the address
back to whatever cv2 index the OS happens to be using *right now*.

Strategy: probe cv2 indices 0..N to find what cv2 can actually open, then ask
the OS for camera metadata and pair them positionally. Both lists are in
enumeration order, so position N in one matches position N in the other on the
platforms we support. If OS metadata is unavailable (no helper installed,
permission denied, etc.) we fall back to an index-derived address so the
feature still functions; the user just won't get rebinding across reorders.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

import cv2

logger = logging.getLogger(__name__)

_MAX_PROBE_INDEX = 10
_UVC_PREFIX = "uvc:"


def is_uvc_named_source(s: str) -> bool:
    return isinstance(s, str) and s.startswith(_UVC_PREFIX)


def parse_uvc_named_source(s: str) -> tuple[str, str]:
    """Split ``uvc:<name>@<address>`` into (name, address). The address is the
    portion after the LAST ``@`` to tolerate ``@`` characters appearing in
    camera names (which DirectShow does occasionally produce)."""
    body = s[len(_UVC_PREFIX):]
    at = body.rfind("@")
    if at < 0:
        return body, ""
    return body[:at], body[at + 1:]


def format_uvc_named_source(name: str, address: str) -> str:
    return f"{_UVC_PREFIX}{name}@{address}"


def _probe_cv2_indices(max_index: int = _MAX_PROBE_INDEX) -> list[int]:
    indices = []
    # Use DSHOW on Windows so the obsensor backend never probes every index
    # (which causes error spam and a ~1 s stall per probe call).
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
    for i in range(max_index):
        cap = cv2.VideoCapture(i, backend)
        try:
            if cap.isOpened():
                indices.append(i)
        finally:
            cap.release()
    return indices


def _windows_pnp_name_to_deviceid() -> dict[str, list[str]]:
    """Map PnP friendly name → list of DeviceIDs (stable per USB descriptor).
    A list because two identical webcams share a friendly name; callers need
    to handle the ambiguity rather than picking the wrong one silently."""
    ps = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPClass -eq 'Camera' -or $_.PNPClass -eq 'Image' -or $_.Service -eq 'usbvideo' } | "
        "Select-Object Name, DeviceID | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=8, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return {}
        data = json.loads(out.stdout)
        if isinstance(data, dict):
            data = [data]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.debug("Windows PnP enumeration failed: %s", e)
        return {}

    mapping: dict[str, list[str]] = {}
    for d in data:
        name = d.get("Name") or "Camera"
        device_id = d.get("DeviceID") or ""
        if device_id:
            mapping.setdefault(name, []).append(device_id)
    return mapping


def _windows_wmi_only_metadata(pnp_map: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Camera metadata from WMI alone, used when pygrabber is unavailable.

    Includes every DeviceID per name so that two identical cameras (same
    friendly name, same VID/PID) both appear as selectable sources. WMI
    registration order may not match DirectShow/cv2 enumeration order for
    multi-camera setups — cameras might be swapped — but both are at least
    visible and carry stable per-port DeviceID addresses, which is strictly
    better than the blind ``'Camera N'``/``'index:N'`` probe fallback."""
    result: list[tuple[str, str]] = []
    for name, device_ids in pnp_map.items():
        for device_id in device_ids:
            result.append((name, device_id))
    return result


def _windows_camera_metadata() -> list[tuple[str, str]]:
    """Returns ``[(name, address), ...]`` in cv2/DSHOW index order.

    cv2's DSHOW backend opens cameras in DirectShow moniker enumerator order.
    pygrabber walks the *same* enumerator, so its name list is index-aligned
    with cv2 — unlike ``Win32_PnPEntity`` which returns devices in PnP-
    registration order and silently mis-pairs names with indices. PowerShell
    is kept only to attach stable DeviceID addresses to the pygrabber names.

    When pygrabber is unavailable or fails, falls back to WMI-only metadata
    so that at least camera names and DeviceID addresses are preserved
    (instead of the ``'Camera N'``/``'index:N'`` blind-probe fallback).
    """
    pnp_map = _windows_pnp_name_to_deviceid()

    try:
        from pygrabber.dshow_graph import FilterGraph  # type: ignore
    except ImportError:
        logger.warning(
            "pygrabber not installed; Windows camera names may be mis-ordered. "
            "Reinstall dependencies to fix."
        )
        return _windows_wmi_only_metadata(pnp_map)

    # pygrabber drives DirectShow through COM, which requires the calling thread
    # to have initialized COM. The GUI scan thread inherits an initialized
    # apartment (Tk/cv2 set one up), but the camera *capture* thread does not —
    # there the first FilterGraph() raises "CoInitialize has not been called",
    # pygrabber silently falls back to WMI ordering, and WMI device order does
    # NOT match cv2/DirectShow index order, so the wrong index gets opened (the
    # "solid black ~10 fps wrong camera" symptom on first connect). Initialize
    # COM just for the enumeration; the Initialize/Uninitialize pair is
    # ref-count balanced, so it neither leaks nor tears down COM on a thread
    # (like the scan thread) that already had it up.
    _com_up = False
    try:
        import comtypes  # pygrabber's own COM layer — always present with pygrabber
        try:
            comtypes.CoInitialize()
            _com_up = True
        except OSError:
            # Already initialized in an incompatible apartment; use it as-is.
            pass
    except ImportError:
        pass

    try:
        names = list(FilterGraph().get_input_devices())
    except Exception as e:
        logger.debug("pygrabber enumeration failed: %s", e)
        return _windows_wmi_only_metadata(pnp_map)
    finally:
        if _com_up:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    consumed: dict[str, int] = {}
    result: list[tuple[str, str]] = []
    for pos, name in enumerate(names):
        device_ids = pnp_map.get(name, [])
        idx = consumed.get(name, 0)
        # When multiple cameras share a name (e.g. two identical webcams),
        # pop DeviceIDs in PnP order. The pairing isn't provably correct in
        # that case, but it's deterministic and per-USB-port stable, which is
        # what users actually need for rebinding. Fall back to index when we
        # run out of DeviceIDs so the entry still has a usable key.
        if idx < len(device_ids):
            address = device_ids[idx]
            consumed[name] = idx + 1
        else:
            address = f"index:{pos}"
        result.append((name, address))
    return result


def _linux_camera_metadata() -> list[tuple[str, str]]:
    # /sys/class/video4linux exposes the device name; /dev/v4l/by-id has stable
    # symlinks keyed on USB descriptor. We iterate /dev/video* in numeric order
    # (v4l2 indices match cv2 indices) and resolve each to its by-id symlink if
    # one exists. Devices without a by-id entry fall back to the sysfs name.
    video_devs = []
    try:
        for entry in sorted(os.listdir("/dev")):
            if entry.startswith("video") and entry[5:].isdigit():
                video_devs.append((int(entry[5:]), f"/dev/{entry}"))
    except OSError:
        return []
    video_devs.sort()

    by_id_map: dict[str, str] = {}
    by_id_dir = "/dev/v4l/by-id"
    if os.path.isdir(by_id_dir):
        for link in os.listdir(by_id_dir):
            link_path = os.path.join(by_id_dir, link)
            try:
                target = os.path.realpath(link_path)
                by_id_map[target] = link_path
            except OSError:
                pass

    result: list[tuple[str, str]] = []
    for _, dev_path in video_devs:
        name = "Camera"
        try:
            with open(f"/sys/class/video4linux/{os.path.basename(dev_path)}/name") as f:
                name = f.read().strip() or name
        except OSError:
            pass
        address = by_id_map.get(dev_path, dev_path)
        result.append((name, address))
    return result


def _macos_camera_metadata() -> list[tuple[str, str]]:
    try:
        out = subprocess.run(
            ["system_profiler", "-json", "SPCameraDataType"],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return []
        data = json.loads(out.stdout)
        cams = data.get("SPCameraDataType", [])
        result = []
        for c in cams:
            name = c.get("_name") or "Camera"
            # spcamera_unique-id is the AVFoundation unique identifier.
            addr = c.get("spcamera_unique-id") or c.get("spcamera_model-id") or name
            result.append((name, addr))
        return result
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.debug("macOS camera enumeration failed: %s", e)
        return []


def _platform_metadata() -> list[tuple[str, str]]:
    if sys.platform.startswith("win"):
        return _windows_camera_metadata()
    if sys.platform == "darwin":
        return _macos_camera_metadata()
    if sys.platform.startswith("linux"):
        return _linux_camera_metadata()
    return []


_uvc_list_cache: "list[dict] | None" = None
_uvc_list_cache_time: float = 0.0
_uvc_list_cache_lock = threading.Lock()
_uvc_list_cache_last_invalidated: float = -999.0

# Per-camera-object claim registry.  Each Camera instance registers the device
# address it is currently using so that sibling cameras (same name, different
# address) can exclude it during fallback resolution.  Keyed by id(camera).
_claimed_lock = threading.Lock()
_claimed: "dict[int, str]" = {}


def claim_uvc_address(owner_id: int, address: str) -> None:
    """Record that a camera object has resolved and intends to open ``address``."""
    with _claimed_lock:
        _claimed[owner_id] = address


def release_uvc_claim(owner_id: int) -> None:
    """Release a previously claimed device address."""
    with _claimed_lock:
        _claimed.pop(owner_id, None)
# How long (seconds) to reuse a camera list before re-enumerating. Must be long
# enough that reconnect-retry loops from two camera threads don't trigger
# concurrent DirectShow enumerations that compete with active camera handles and
# cause read failures / 1-fps stalls. 10 s is a comfortable budget: plug/unplug
# events are still caught within a couple of loop ticks.
_UVC_LIST_CACHE_TTL = 10.0
# Prevents two threads from running _list_uvc_cameras_uncached() simultaneously.
# Without this, both camera threads see an expired cache at the same instant and
# both invoke pygrabber/DirectShow — the concurrent COM calls interfere with
# active cv2.CAP_DSHOW handles, producing read failures and 1-fps stalls.
_uvc_enumerate_lock = threading.Lock()


def _list_uvc_cameras_uncached() -> "list[dict]":
    metadata = _platform_metadata()
    if metadata:
        return [
            {
                "index": pos,
                "name": name or f"Camera {pos}",
                "address": address or f"index:{pos}",
            }
            for pos, (name, address) in enumerate(metadata)
        ]
    indices = _probe_cv2_indices()
    return [
        {"index": idx, "name": f"Camera {idx}", "address": f"index:{idx}"}
        for idx in indices
    ]


def list_uvc_cameras() -> "list[dict]":
    """Returns ``[{'index': int, 'name': str, 'address': str}, ...]`` for every
    detectable webcam. ``address`` is a stable per-device identifier when the
    OS exposes one, otherwise an ``index:N`` fallback so the dropdown still has
    a usable key.

    When OS metadata is available we trust its enumeration and skip probing
    cv2 indices entirely — probing opens/releases every index, which briefly
    grabs the device handle and races with whatever else (including our own
    capture thread on retry) is trying to open the same camera. We only fall
    back to probing when the OS query produced nothing usable.

    Results are cached for ``_UVC_LIST_CACHE_TTL`` seconds. A global
    ``_uvc_enumerate_lock`` ensures only one enumeration runs at a time: a
    second caller that sees an expired cache will block until the first
    finishes, then reuse its result rather than starting a second concurrent
    DirectShow / PowerShell enumeration."""
    global _uvc_list_cache, _uvc_list_cache_time
    now = time.monotonic()
    with _uvc_list_cache_lock:
        if _uvc_list_cache is not None and (now - _uvc_list_cache_time) < _UVC_LIST_CACHE_TTL:
            return list(_uvc_list_cache)
    # Serialize enumerations: only one thread runs _list_uvc_cameras_uncached()
    # at a time. Concurrent callers block here then hit the cache check below.
    with _uvc_enumerate_lock:
        now = time.monotonic()
        with _uvc_list_cache_lock:
            if _uvc_list_cache is not None and (now - _uvc_list_cache_time) < _UVC_LIST_CACHE_TTL:
                return list(_uvc_list_cache)
        result = _list_uvc_cameras_uncached()
        with _uvc_list_cache_lock:
            _uvc_list_cache = result
            _uvc_list_cache_time = time.monotonic()
        return result


def invalidate_uvc_camera_cache() -> None:
    """Force the next ``list_uvc_cameras()`` call to re-enumerate devices.
    Call this after a successful camera open or when the GUI requests a fresh scan.

    Rate-limited to once per TTL period: a flapping camera (opens then fails on
    read, over and over) would otherwise clear the cache on every retry cycle,
    spawning a new PowerShell/DirectShow enumeration every ~100 ms."""
    global _uvc_list_cache, _uvc_list_cache_last_invalidated
    now = time.monotonic()
    with _uvc_list_cache_lock:
        if now - _uvc_list_cache_last_invalidated < _UVC_LIST_CACHE_TTL:
            return
        _uvc_list_cache = None
        _uvc_list_cache_last_invalidated = now


# ETVR firmware (OpenIris) advertises itself on the LAN via mDNS as
# ``ETVR-Left.local`` / ``ETVR-Right.local`` and serves the MJPEG stream at the
# root URL. Resolution goes through the OS resolver: Bonjour on macOS / Windows
# (when Bonjour is installed) and Avahi on Linux. Hosts that are powered off or
# on a different VLAN simply fail to resolve and are silently omitted.
_ETVR_MDNS_HOSTS = ("ETVR-Left.local", "ETVR-Right.local")
_ETVR_MDNS_LOOKUP_TIMEOUT_S = 5.0


def _resolve_mdns_host(host: str) -> bool:
    """Returns True if ``host`` currently resolves (i.e. the device is
    advertising on the LAN). Uses ``socket.gethostbyname`` so this is a
    blocking call — callers must run it on a worker thread."""
    try:
        socket.gethostbyname(host)
        return True
    except (socket.gaierror, OSError):
        return False


def discover_etvr_mdns_sources(
    hosts: Iterable[str] = _ETVR_MDNS_HOSTS,
    timeout_s: float = _ETVR_MDNS_LOOKUP_TIMEOUT_S,
) -> list[str]:
    """Return HTTP capture-source URLs for ETVR trackers currently reachable on
    the LAN via mDNS. ``socket.gethostbyname`` has no per-call timeout, so we
    fan out one worker thread per host and join with a deadline; hosts that
    don't resolve in time are dropped from the result. Safe to call from the
    UVC scan thread (still don't call from the UI thread — it blocks)."""
    hosts = list(hosts)
    found: dict[str, bool] = {}

    def _worker(h: str) -> None:
        found[h] = _resolve_mdns_host(h)

    threads = [threading.Thread(target=_worker, args=(h,), daemon=True) for h in hosts]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout_s)
    # Build URLs in the original host order so left/right stay deterministic.
    return [f"http://{h}/" for h in hosts if found.get(h)]


# ETVR firmware streams MJPEG over USB-serial at 3 Mbaud on Windows/Linux and
# 115200 on macOS (the high baud rate isn't reliably supported on darwin USB
# CDC drivers — keep these aligned with start_serial_connection in camera.py).
_SERIAL_BAUD_DEFAULT = 3_000_000
_SERIAL_BAUD_DARWIN = 115_200
# Total wall-clock budget per port.  Opening the port briefly toggles DTR,
# which triggers the ESP32 auto-reset circuit; the bootloader runs for ~3 s
# before firmware starts streaming.  4 s gives a comfortable margin.
_SERIAL_PROBE_TIMEOUT_S = 4.0
# Cap concurrent probes so we don't open dozens of ports at once on machines
# with many virtual COM ports (USB-CDC modems, debug ports, etc.).
_SERIAL_PROBE_WORKERS = 4
# Marker that identifies a JPEG payload — same SOI that camera.py looks for in
# the live stream. Three bytes is specific enough that random noise from a
# non-camera device hitting the same baud is vanishingly unlikely to match.
_JPEG_SOI = b"\xff\xd8\xff"


def _looks_like_usable_serial(port_info) -> bool:
    """Filter out ports we should not probe.

    macOS exposes Bluetooth modem endpoints (``/dev/cu.Bluetooth-*``,
    ``/dev/cu.debug-console``) as comports — opening them at 3 Mbaud is at
    best slow and at worst kicks an active Bluetooth session. Anything with a
    USB vendor ID is fair game; otherwise we look at the device name."""
    name = (port_info.device or "").lower()
    if "bluetooth" in name or "debug-console" in name:
        return False
    # Trust USB-VID ports unconditionally; serial-over-USB is what ETVR uses.
    if getattr(port_info, "vid", None):
        return True
    # No VID + non-Bluetooth → still try it. Built-in UART headers on Linux
    # SBCs (Pi, etc.) land here and could be perfectly valid ETVR connections.
    return True


def _probe_serial_for_jpeg(device: str, baud: int, timeout_s: float) -> bool:
    """Open ``device`` at ``baud`` and look for a JPEG SOI within ``timeout_s``.

    Returns True iff we see ``\\xff\\xd8\\xff`` in the byte stream — that's
    proof the port is currently emitting MJPEG frames the way ETVR firmware
    does. Anything that raises (port busy, permission denied, no such device)
    is silently treated as "not an ETVR cam"; the caller has nothing useful
    to do with the error and the user already gets a "none" result if no
    ports match."""
    try:
        import serial  # local import keeps camera_enum importable without pyserial in unrelated tools
    except ImportError:
        return False

    conn = None
    try:
        conn = serial.Serial(
            port=device,
            baudrate=baud,
            xonxoff=False,
            dsrdtr=False,
            rtscts=False,
            timeout=0.15,
        )
        # Discard any bytes already in the OS buffer (bootloader noise, partial
        # frames from a previous session) so the SOI search starts clean.
        conn.reset_input_buffer()
    except (serial.SerialException, OSError, ValueError):
        return False

    try:
        buf = b""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                chunk = conn.read(1024)
            except (serial.SerialException, OSError):
                return False
            if chunk:
                buf += chunk
                if _JPEG_SOI in buf:
                    return True
                # Cap the scanning buffer so a port spewing noise can't balloon memory.
                if len(buf) > 8192:
                    buf = buf[-2048:]
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except (Exception,):  # noqa: BLE001 — close failure during scan is irrelevant
            pass


def discover_etvr_serial_cameras(
    timeout_s: float = _SERIAL_PROBE_TIMEOUT_S,
) -> list[tuple[str, str]]:
    """Return ``[(label, device), ...]`` for COM/tty ports currently streaming
    ETVR-style MJPEG. ``device`` is the raw port path the rest of the app
    already accepts as a capture source (e.g. ``COM5``, ``/dev/cu.usbserial-0001``).

    Probes run in parallel under a small thread pool so the wall-clock scan
    stays near ``timeout_s`` even on machines with multiple candidate ports.
    Ports that are already held by the live capture thread will fail to open
    and are silently dropped — that's correct, since the user already has
    them configured.

    Safe to call from a worker thread. Do not call from the UI thread; serial
    opens can stall for hundreds of milliseconds on some drivers."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []

    baud = _SERIAL_BAUD_DARWIN if sys.platform == "darwin" else _SERIAL_BAUD_DEFAULT
    candidates = [p for p in list_ports.comports() if _looks_like_usable_serial(p)]
    if not candidates:
        return []

    results: list[tuple[str, str]] = []
    with ThreadPoolExecutor(
        max_workers=min(_SERIAL_PROBE_WORKERS, len(candidates))
    ) as pool:
        futures = {
            pool.submit(_probe_serial_for_jpeg, p.device, baud, timeout_s): p
            for p in candidates
        }
        for fut in as_completed(futures):
            port = futures[fut]
            try:
                ok = fut.result()
            except Exception as e:  # noqa: BLE001 — defensive; a hung probe shouldn't sink the scan
                logger.debug("Serial probe %s raised: %s", port.device, e)
                ok = False
            if ok:
                # Friendly label: prefer the OS-supplied description when it's
                # something more useful than just the device path. PySerial
                # often returns the device path as description on macOS/Linux,
                # so de-dup that case.
                desc = (port.description or "").strip()
                if desc and desc.lower() != port.device.lower() and desc != "n/a":
                    label = f"{desc} ({port.device})"
                else:
                    label = port.device
                results.append((label, port.device))

    # Stable ordering so the dropdown doesn't reshuffle between scans.
    results.sort(key=lambda lv: lv[1])
    return results


def resolve_uvc_address_to_index(
    name: str,
    address: str,
    cameras: "Iterable[dict] | None" = None,
    owner_id: "int | None" = None,
) -> "tuple[int, str] | None":
    """Find the current cv2 index for a previously-saved (name, address) pair.

    Prefers address match (stable across reorders); falls back to name match
    if the same device was re-enumerated with a fresh address (rare but
    possible if drivers reinstall).

    When ``owner_id`` is provided (the ``id()`` of the calling Camera object),
    the registry of claims held by *other* cameras is used as a tie-breaker
    when multiple cameras share the same name: if exactly one of those cameras
    is not already claimed by a sibling, that one is returned automatically.
    This recovers the common case where one camera was replugged and Windows
    assigned it a new device-instance path — the sibling camera's claim
    identifies the "taken" slot so we can infer the unclaimed one must be ours.

    Returns ``(cv2_index, resolved_device_address)`` or ``None`` if the camera
    is not currently present.
    """
    cams = list(cameras) if cameras is not None else list_uvc_cameras()
    if address:
        # index:N fallback addresses encode the index directly; trust them only
        # if that index is still present.
        if address.startswith("index:"):
            try:
                target = int(address.split(":", 1)[1])
            except ValueError:
                target = None
            if target is not None and any(c["index"] == target for c in cams):
                return target, address
        for c in cams:
            if c["address"] == address:
                return c["index"], c["address"]
    if name:
        matches = [c for c in cams if c["name"] == name]
        if len(matches) == 1:
            return matches[0]["index"], matches[0]["address"]
        if len(matches) > 1:
            # Multiple cameras share this name; a name-only match would pick
            # the wrong device. Let the caller handle the miss gracefully.
            logger.debug(
                "UVC name fallback skipped for '%s': %d cameras share that name; "
                "re-select from the dropdown to re-assign by address.",
                name, len(matches),
            )
            # When an owner_id is provided, use the sibling-camera claim registry
            # to narrow down: exclude addresses claimed by other camera objects.
            # If exactly one camera is unclaimed, that must be ours — auto-route.
            if owner_id is not None:
                with _claimed_lock:
                    others = {addr for oid, addr in _claimed.items() if oid != owner_id}
                unclaimed = [c for c in matches if c["address"] not in others]
                if len(unclaimed) == 1:
                    logger.info(
                        "UVC '%s': stored address '%s' not present; auto-routing to "
                        "unclaimed camera '%s'. Re-select in the UI to make permanent.",
                        name, address, unclaimed[0]["address"],
                    )
                    return unclaimed[0]["index"], unclaimed[0]["address"]
    logger.debug(
        "UVC resolve failed for '%s'@'%s'; enumerated: %s",
        name, address, [(c["name"], c["address"]) for c in cams],
    )
    return None
