"""
App updates from the project's GitHub releases.

Finds the newest release the user's channel allows (stable only, or stable and
pre-releases), and on an installed Windows build can update in place: download that
release's installer, check it against the SHA-256 GitHub publishes for the asset, and
run it. Nothing here installs without the user asking (utils/update_dialog.py).

Other builds (running from source, Linux tarball) get the release page instead.
"""

import hashlib
import logging
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from utils.version_utils import compare_app_versions, parse_app_version

logger = logging.getLogger(__name__)

REPOSITORY = "EyeTrackVR/EyeTrackVR"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
# Installers are only ever taken from this repository's own release downloads.
DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
# This app's releases. The repository also holds releases of the project's earlier app
# ("v2.0 BETA 14"), whose numbers would sort above every current version.
RELEASE_NAME = re.compile(r"^EyeTrackApp[ \-]", re.IGNORECASE)
WINDOWS_INSTALLER = re.compile(r"^EyeTrackVR-Setup-[\w.\-]+\.exe$")
MAX_INSTALLER_BYTES = 2 * 1024 * 1024 * 1024
CHUNK = 1024 * 256

# Inno Setup: progress window only, no questions; our installer starts the app again
# when it sees /RELAUNCH (packaging/windows/installer.iss).
INSTALLER_ARGUMENTS = "/SILENT /SUPPRESSMSGBOXES /NORESTART /RELAUNCH"


class UpdateError(Exception):
    pass


class Cancelled(UpdateError):
    pass


@dataclass(frozen=True)
class Update:
    version: str  # release name, e.g. "EyeTrackApp 0.3.0 BETA 12"
    prerelease: bool
    page_url: str
    notes: str = ""
    installer_url: str = ""
    installer_name: str = ""
    installer_size: int = 0
    installer_sha256: str = ""

    @property
    def installable(self) -> bool:
        """This build can replace itself with this release."""
        return bool(
            sys.platform == "win32" and getattr(sys, "frozen", False) and self.installer_url and self.installer_sha256
        )


def is_prerelease(version: str) -> bool:
    """An alpha / beta / rc build."""
    parsed = parse_app_version(version)
    return parsed is not None and parsed[1] < 3


def include_prereleases(installed: str, opted_in: bool) -> bool:
    """Someone already running a pre-release keeps getting them: for them "stable only"
    would mean no updates until the final release."""
    return bool(opted_in) or is_prerelease(installed)


def _windows_installer(release: dict) -> dict:
    for asset in release.get("assets") or []:
        name, url = str(asset.get("name") or ""), str(asset.get("browser_download_url") or "")
        digest = str(asset.get("digest") or "")
        if WINDOWS_INSTALLER.match(name) and url.startswith(DOWNLOAD_PREFIX) and digest.startswith("sha256:"):
            return {
                "installer_url": url,
                "installer_name": name,
                "installer_size": int(asset.get("size") or 0),
                "installer_sha256": digest.split(":", 1)[1].lower(),
            }
    return {}


def pick_update(releases: list, installed: str, prereleases: bool, skipped: str = "") -> Update | None:
    """The newest published release that is newer than ``installed``, or None."""
    best = None
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        if release.get("prerelease") and not prereleases:
            continue
        # The tag is the version: early 0.3.0 betas were all *named* "EyeTrackApp 0.3.0".
        tag = str(release.get("tag_name") or release.get("name") or "")
        if not RELEASE_NAME.match(tag):
            continue
        version = tag.replace("-", " ")
        if compare_app_versions(installed, version) != -1:
            continue  # not newer, or a name that is not a version
        if best is None or compare_app_versions(str(best["name"]), version) == -1:
            best = dict(release, name=version)
    if best is None or (skipped and compare_app_versions(skipped, str(best["name"])) == 0):
        return None
    return Update(
        version=str(best["name"]),
        prerelease=bool(best.get("prerelease")),
        page_url=str(best.get("html_url") or RELEASES_PAGE),
        notes=str(best.get("body") or "").strip(),
        **_windows_installer(best),
    )


def fetch_releases(timeout=(3, 10)) -> list:
    import requests  # off the startup path (~200 ms)

    response = requests.get(RELEASES_API, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
    response.raise_for_status()
    releases = response.json()
    if not isinstance(releases, list):
        raise ValueError("unexpected release list")
    return releases


def check(installed: str, opted_in_prereleases: bool, skipped: str = "", fetch=fetch_releases) -> Update | None:
    """Ask GitHub. Raises on a network or format problem."""
    return pick_update(fetch(), installed, include_prereleases(installed, opted_in_prereleases), skipped)


def download_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "EyeTrackVR" / "updates"


def _open_stream(url: str):
    import requests

    response = requests.get(url, stream=True, timeout=(5, 30))
    response.raise_for_status()
    return response.iter_content(CHUNK)


def download_installer(
    update: Update,
    target_dir: Path | None = None,
    progress=lambda done, total: None,
    cancel: threading.Event | None = None,
    open_stream=_open_stream,
) -> Path:
    """Download the release's installer and return its path once its size and SHA-256
    match what GitHub lists. Anything else is deleted and raises UpdateError."""
    if not (update.installer_url.startswith(DOWNLOAD_PREFIX) and update.installer_sha256):
        raise UpdateError("this release has no verifiable installer")
    if not WINDOWS_INSTALLER.match(update.installer_name) or update.installer_size > MAX_INSTALLER_BYTES:
        raise UpdateError("unexpected installer file")
    target_dir = target_dir or download_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    for old in target_dir.iterdir():  # earlier downloads: each is ~200 MB
        if old.is_file():
            try:
                old.unlink()
            except OSError:
                pass
    target = target_dir / update.installer_name
    partial = target_dir / (update.installer_name + ".part")
    digest, done = hashlib.sha256(), 0
    try:
        with open(partial, "wb") as file:
            for chunk in open_stream(update.installer_url):
                if cancel is not None and cancel.is_set():
                    raise Cancelled("cancelled")
                done += len(chunk)
                if done > max(update.installer_size, 1) or done > MAX_INSTALLER_BYTES:
                    raise UpdateError("download is larger than the release lists")
                digest.update(chunk)
                file.write(chunk)
                progress(done, update.installer_size)
        if done != update.installer_size or digest.hexdigest() != update.installer_sha256:
            raise UpdateError("download does not match the published checksum")
        os.replace(partial, target)
    except Exception as e:
        try:
            partial.unlink()
        except OSError:
            pass
        if isinstance(e, UpdateError):
            raise
        raise UpdateError(str(e) or e.__class__.__name__) from e
    return target


def steamvr_running() -> bool:
    """Whether SteamVR is up on Windows. vrserver.exe and the games it runs hold the
    driver and OpenXR layer DLLs in the install folder open, so the silent installer
    would close them or fail half-way. A check that raises doesn't block an update."""
    if sys.platform != "win32":
        return False
    try:
        from ovr.openvr_service import _windows_process_running

        return bool(_windows_process_running("vrserver.exe"))
    except Exception:
        logger.debug("Could not check whether SteamVR is running", exc_info=True)
        return False


def launch_installer(path: Path) -> None:
    """Start the downloaded installer. The caller then closes the app so its files can
    be replaced. Through the shell: the installer asks for elevation itself (UAC)."""
    os.startfile(str(path), "open", INSTALLER_ARGUMENTS)  # noqa: S606 (verified download)
