"""
Quad-Views-Foveated (mbucchia), the OpenXR API layer that gives quad-views games (DCS
World, Pavlov VR, ...) eye-tracked foveated rendering. It reads gaze through
XR_EXT_eye_gaze_interaction, which EyeTrackVR provides with its SteamVR driver or its
own OpenXR layer while "Foveated rendering support" is on.

DFR's Set up (ovr/dfr_setup.py) installs it next to PimaxMagic4All: the pinned MSI is
downloaded, checked against its SHA-256, and run silently in the same elevated step that
copies PimaxMagic4All's system files, so the user sees one Windows prompt.

The MSI installs for all users into Program Files and registers its manifest under
HKLM\\SOFTWARE\\Khronos\\OpenXR\\1\\ApiLayers\\Implicit, ahead of other layers. HKLM
layers load before EyeTrackVR's per-user one, so its eye gaze calls pass through ours.
"""

import hashlib
import logging
import os
import sys
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

VERSION = "1.1.3"
RELEASE_URL = (
    f"https://github.com/mbucchia/Quad-Views-Foveated/releases/download/{VERSION}/Quad-Views-Foveated-{VERSION}.msi"
)
RELEASE_SHA256 = "7b59593b83cd38da6f55070a06a1bbb26312d304cbee54a8d68ea493d3118326"
MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024
TIMEOUT_S = 30

REGISTRY_KEY = r"SOFTWARE\Khronos\OpenXR\1\ApiLayers\Implicit"
# The value name is the manifest path: <Program Files>\OpenXR-Quad-Views-Foveated\openxr-api-layer.json
MANIFEST_SUFFIX = "\\openxr-quad-views-foveated\\openxr-api-layer.json"


def _registered_layers() -> dict[str, int]:
    """HKLM implicit OpenXR layers (64-bit view): manifest path -> 0 enabled / 1 disabled."""
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except OSError:
        return {}
    out = {}
    with key:
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            out[name] = value if isinstance(value, int) else 1
            i += 1
    return out


def installed(layers=None, exists=os.path.isfile) -> bool:
    """Quad-Views-Foveated is registered, enabled, and its manifest is on disk."""
    if layers is None:
        if sys.platform != "win32":
            return False
        layers = _registered_layers()
    return any(path.lower().endswith(MANIFEST_SUFFIX) and value == 0 and exists(path) for path, value in layers.items())


def download_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "EyeTrackVR" / "Quad-Views-Foveated"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "EyeTrackVR"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError("download is larger than expected")
    return data


def download(target: Path | None = None, fetch=_fetch) -> Path:
    """Download the pinned MSI and return its path. Raises ValueError for a download that
    is not the pinned file, OSError when it cannot be saved, and whatever ``fetch``
    raises when it cannot be downloaded."""
    target = target or download_dir()
    path = target / f"Quad-Views-Foveated-{VERSION}.msi"
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() == RELEASE_SHA256:
            return path  # from an earlier setup that stopped at the Windows prompt
    except OSError:
        pass
    data = fetch(RELEASE_URL)
    digest = hashlib.sha256(data).hexdigest()
    if digest != RELEASE_SHA256:
        raise ValueError(f"checksum {digest}")
    target.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(data)
    os.replace(partial, path)
    return path


def install_command(msi: Path) -> str:
    """The cmd.exe command that installs the MSI silently and waits for it. Raises
    ValueError for a path cmd could misread."""
    source = str(msi)
    if any(c in source for c in '"%^&|<>'):
        raise ValueError(f"unsupported character in {source!r}")
    return f'start "" /wait msiexec.exe /i "{source}" /qn /norestart'
