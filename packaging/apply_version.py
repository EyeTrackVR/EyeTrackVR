"""Stamp the version from version.txt into every place the build cares about.

Usage: python packaging/apply_version.py [--check]

Reads <repo-root>/version.txt (single line, e.g. "0.3.0 BETA 7") and rewrites:
  - eyetrackapp/eyetrackapp.py           APP_VERSION = "EyeTrackApp <version>"
  - packaging/windows/installer.iss       #define MyAppVersion "<version>"
                                          OutputBaseFilename=EyeTrackVR-Setup-<version-with-dashes>
  - pyproject.toml                        version = "<PEP 440 form>"  e.g. 0.3.0b7, 0.3.0rc1

--check exits 1 if any file is out of sync without modifying anything
(packaging/build_release.bat and CI refuse to build a release that is out of sync).

Prints the version (and the file-safe variant) so batch callers can capture it:
  line 1: raw version        e.g. 0.3.0 BETA 7
  line 2: file-safe version  e.g. 0.3.0-BETA-7
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "version.txt"
APP_PY = REPO_ROOT / "eyetrackapp" / "eyetrackapp.py"
ISS_FILE = REPO_ROOT / "packaging" / "windows" / "installer.iss"
PYPROJECT = REPO_ROOT / "pyproject.toml"

APP_VERSION_RE = re.compile(r'^APP_VERSION = ".*"$', re.MULTILINE)
ISS_VERSION_RE = re.compile(r'^#define MyAppVersion ".*"$', re.MULTILINE)
ISS_OUTPUT_RE = re.compile(r"^OutputBaseFilename=.*$", re.MULTILINE)
# The first top-level `version = ` line: [tool.poetry]'s (dependency tables are indented or inline).
PYPROJECT_VERSION_RE = re.compile(r'^version = ".*"$', re.MULTILINE)

# "0.3.0 BETA 7" / "0.3.0-RC1" / "0.3.0": release, then an optional pre-release tag and number.
_VERSION_PARTS_RE = re.compile(
    r"^(\d+(?:\.\d+)*)(?:[ ._-]*(ALPHA|A|BETA|B|RC|C|PRE|PREVIEW)[ ._-]*(\d+))?$", re.IGNORECASE
)
_PEP440_PRE = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "rc": "rc", "c": "rc", "pre": "rc", "preview": "rc"}


def pep440(version: str) -> str:
    """0.3.0 BETA 7 -> 0.3.0b7, 0.3.0 RC1 -> 0.3.0rc1, 0.3.0 -> 0.3.0 (pyproject.toml)."""
    match = _VERSION_PARTS_RE.match(version.strip())
    if not match:
        sys.exit(f"ERROR: cannot turn {version!r} into a PEP 440 version for pyproject.toml")
    release, tag, number = match.groups()
    return release + (f"{_PEP440_PRE[tag.lower()]}{number}" if tag else "")


def file_safe(version: str) -> str:
    """0.3.0 BETA 7 -> 0.3.0-BETA-7 (matches historical installer names)."""
    return re.sub(r"[^A-Za-z0-9.+_-]+", "-", version.strip())


def apply(text: str, pattern: re.Pattern, replacement: str, path: Path) -> str:
    new_text, n = pattern.subn(replacement, text, count=1)
    if n != 1:
        sys.exit(f"ERROR: pattern {pattern.pattern!r} not found in {path}")
    return new_text


def main() -> int:
    check_only = "--check" in sys.argv[1:]

    if not VERSION_FILE.exists():
        sys.exit(f"ERROR: {VERSION_FILE} not found. Create it with the release version.")
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        sys.exit(f"ERROR: {VERSION_FILE} is empty.")
    safe = file_safe(version)

    targets = [
        (APP_PY, APP_VERSION_RE, f'APP_VERSION = "EyeTrackApp {version}"'),
        (ISS_FILE, ISS_VERSION_RE, f'#define MyAppVersion "{version}"'),
        (ISS_FILE, ISS_OUTPUT_RE, f"OutputBaseFilename=EyeTrackVR-Setup-{safe}"),
        (PYPROJECT, PYPROJECT_VERSION_RE, f'version = "{pep440(version)}"'),
    ]

    dirty = False
    # Group edits per file so multi-pattern files are written once.
    by_file: dict[Path, list[tuple[re.Pattern, str]]] = {}
    for path, pattern, replacement in targets:
        by_file.setdefault(path, []).append((pattern, replacement))

    for path, edits in by_file.items():
        original = path.read_text(encoding="utf-8")
        text = original
        for pattern, replacement in edits:
            text = apply(text, pattern, replacement, path)
        if text != original:
            dirty = True
            if check_only:
                print(f"out of sync with version.txt: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
            else:
                path.write_text(text, encoding="utf-8", newline="")
                print(f"stamped {path.relative_to(REPO_ROOT)}", file=sys.stderr)

    print(version)
    print(safe)
    if check_only and dirty:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
