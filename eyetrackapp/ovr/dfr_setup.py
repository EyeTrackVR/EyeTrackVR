"""
One-step setup for foveated rendering in games (ovr/dfr.py): get a PimaxMagic4All copy
and install its system files, and install Quad-Views-Foveated (ovr/quad_views.py) for
OpenXR quad-views games, so the user doesn't have to find, unzip and point at releases.
Both installs share one elevated step, so there is one Windows prompt.

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

from ovr import dfr, quad_views

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


def install_elevated(tool_dir: str | None, msi: Path | None) -> bool:
    """One elevated cmd.exe (one UAC prompt) that copies PimaxMagic4All's system files
    from ``tool_dir`` and installs the Quad-Views-Foveated ``msi``, either one skipped
    when None. Returns whether the system files are now in place (True when not asked);
    Quad-Views-Foveated is checked by the caller."""
    commands = []
    if tool_dir is not None:
        try:
            commands.append(dfr.system_files_copy(tool_dir))
        except ValueError as e:
            logger.warning("DFR: cannot install the system files (%s)", e)
            return False
    if msi is not None:
        try:
            commands.append(quad_views.install_command(msi))
        except ValueError as e:
            logger.warning("DFR: cannot install Quad-Views-Foveated (%s)", e)
    if commands:
        # The MSI can take a while; the copies alone take a moment.
        dfr.run_elevated(dfr.cmd_arguments(*commands), timeout_ms=180_000 if msi is not None else 60_000)
    return tool_dir is None or dfr.system_files_installed(tool_dir)


def run(
    controller: dfr.DfrController,
    progress=lambda step: None,
    *,
    download=download_tool,
    install=install_elevated,
    installed=dfr.system_files_installed,
    present=dfr.system_files_present,
    steamvr_running=dfr._vrserver_running,
    quad_views_installed=quad_views.installed,
    download_quad_views=quad_views.download,
) -> str:
    """Everything between "nothing installed" and "ready": download PimaxMagic4All if no
    complete copy is around and Quad-Views-Foveated if it is not installed, then install
    the System32 files and Quad-Views-Foveated in one elevated step. Returns the folder
    that is now set up; raises SetupError for PimaxMagic4All only. Quad-Views-Foveated is
    best effort (it only matters for OpenXR games): check quad_views.installed() after.
    ``progress`` gets "download" / "download_quad_views" / "system_files" as each step
    starts. Blocking, and it changes no settings: call it off the UI thread, then hand
    the result to ``finish`` on the UI thread."""
    tool_dir = controller.tool_dir()
    if dfr.tool_missing_files(tool_dir):
        progress("download")
        tool_dir = str(download())
    msi = None
    if not quad_views_installed():
        progress("download_quad_views")
        try:
            msi = download_quad_views()
        except Exception as e:
            logger.warning("DFR: Quad-Views-Foveated could not be downloaded (%s)", e)
    need_system_files = not installed(tool_dir)
    if need_system_files and present() and steamvr_running():
        raise SetupError(STEAMVR_RUNNING)
    if need_system_files or msi is not None:
        progress("system_files")
        if not install(tool_dir if need_system_files else None, msi) and need_system_files:
            raise SetupError(SYSTEM_FILES_FAILED)
    if msi is not None:
        logger.info("DFR: Quad-Views-Foveated %s", "installed" if quad_views_installed() else "not installed")
    return tool_dir


def finish(controller: dfr.DfrController, tool_dir: str) -> None:
    """Make the controller use the folder ``run`` set up."""
    chosen = str(getattr(controller.settings, "gui_dfr_tool_dir", "") or "")
    if chosen and os.path.normcase(chosen) != os.path.normcase(tool_dir):
        controller.set_tool_dir("")  # an incomplete chosen folder would hide the downloaded copy
    else:
        controller.recheck_setup()
