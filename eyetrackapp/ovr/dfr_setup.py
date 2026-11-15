"""
One-step setup for per-game DFR (ovr/dfr.py): get a PimaxMagic4All copy and install
its system files, so the user doesn't have to find, unzip and point at a release.

The build is pinned: one URL, checked against its SHA-256 before anything is
unpacked. To ship another build, change RELEASE_URL / RELEASE_SHA256 together.

For now that is EyeTrackVR's own build of PimaxMagic4All 1.0 plus the EyeTrackVR gaze
source, which upstream has merged (mbucchia/PimaxMagic4All commit 464fe7a) but not yet
released. Go back to upstream's zip once a release includes it: stock 1.0 ignores
EyeTrackVR's gaze and would foveate around the centre of the view.
"""

import hashlib
import io
import logging
import os
import urllib.request
import zipfile
from pathlib import Path

from ovr import dfr

logger = logging.getLogger(__name__)

RELEASE_URL = "https://github.com/prohurtz/PimaxMagic4All/releases/download/1.0-etvr.1/PimaxMagic4All-1.0-etvr.1.zip"
RELEASE_SHA256 = "c8d1826319bbada94129ef4a0403446996d832c3d62318fb7828be289241714e"
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
TIMEOUT_S = 30

# Why setup stopped, for the panel's message.
DOWNLOAD_FAILED = "download_failed"
BAD_DOWNLOAD = "bad_download"  # wrong checksum, or not the expected archive
WRITE_FAILED = "write_failed"
STEAMVR_RUNNING = "steamvr_running"  # replacing System32 copies needs it closed
SYSTEM_FILES_FAILED = "system_files_failed"  # UAC declined, or the copy failed


class SetupError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def install_dir() -> Path:
    """Where the downloaded copy lives; ovr/dfr.py picks it up from here by default."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "EyeTrackVR" / "PimaxMagic4All"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "EyeTrackVR"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError("download is larger than expected")
    return data


def extract_tool(archive: bytes, target: Path) -> None:
    """Write the files DFR needs from a PimaxMagic4All release zip into ``target``.
    Only those files, by name, wherever the zip keeps them: nothing else in the archive
    is written, and no path from it is used."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = {}
            for info in bundle.infolist():
                name = info.filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
                if not info.is_dir() and info.file_size <= MAX_FILE_BYTES:
                    members.setdefault(name, info)
            missing = [name for name in dfr.TOOL_FILES if name.lower() not in members]
            if missing:
                raise SetupError(BAD_DOWNLOAD, "archive lacks " + ", ".join(missing))
            contents = {name: bundle.read(members[name.lower()]) for name in dfr.TOOL_FILES}
    except (zipfile.BadZipFile, KeyError, RuntimeError) as e:
        raise SetupError(BAD_DOWNLOAD, str(e)) from e
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name, data in contents.items():
            partial = target / (name + ".part")
            partial.write_bytes(data)
            os.replace(partial, target / name)
    except OSError as e:
        raise SetupError(WRITE_FAILED, str(e)) from e


def download_tool(target: Path | None = None, fetch=_fetch) -> Path:
    """Download the pinned PimaxMagic4All release into ``target`` and return it."""
    target = target or install_dir()
    try:
        archive = fetch(RELEASE_URL)
    except Exception as e:
        raise SetupError(DOWNLOAD_FAILED, str(e)) from e
    digest = hashlib.sha256(archive).hexdigest()
    if digest != RELEASE_SHA256:
        raise SetupError(BAD_DOWNLOAD, f"checksum {digest}")
    extract_tool(archive, target)
    logger.info("DFR: PimaxMagic4All installed in %s", target)
    return target


def run(
    controller: dfr.DfrController,
    progress=lambda step: None,
    *,
    download=download_tool,
    install=dfr.install_system_files,
    installed=dfr.system_files_installed,
    present=dfr.system_files_present,
    steamvr_running=dfr._vrserver_running,
) -> str:
    """Everything between "nothing installed" and "ready": download if no complete copy
    is around, then the System32 files. Returns the folder that is now set up; raises
    SetupError. ``progress`` gets "download" / "system_files" as each step starts.
    Blocking, and it changes no settings: call it off the UI thread, then hand the
    result to ``finish`` on the UI thread."""
    tool_dir = controller.tool_dir()
    if dfr.tool_missing_files(tool_dir):
        progress("download")
        tool_dir = str(download())
    if not installed(tool_dir):
        if present() and steamvr_running():
            raise SetupError(STEAMVR_RUNNING)
        progress("system_files")
        if not install(tool_dir):
            raise SetupError(SYSTEM_FILES_FAILED)
    return tool_dir


def finish(controller: dfr.DfrController, tool_dir: str) -> None:
    """Make the controller use the folder ``run`` set up."""
    chosen = str(getattr(controller.settings, "gui_dfr_tool_dir", "") or "")
    if chosen and os.path.normcase(chosen) != os.path.normcase(tool_dir):
        controller.set_tool_dir("")  # an incomplete chosen folder would hide the downloaded copy
    else:
        controller.recheck_setup()
