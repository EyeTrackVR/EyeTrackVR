"""Stamp the version from version.txt into every place the build cares about.

Usage: python scripts/apply_version.py [--check]

Reads <repo-root>/version.txt (single line, e.g. "0.3.0 BETA 7") and rewrites:
  - eyetrackapp/eyetrackapp.py     APP_VERSION = "EyeTrackApp <version>"
  - eyetrackapp/INNO/ETVR_SETUP.iss  #define MyAppVersion "<version>"
                                     OutputBaseFilename=EyeTrackVR-Setup-<version-with-dashes>

--check exits 1 if any file is out of sync without modifying anything
(used by the build script to decide whether a rebuild is needed).

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
ISS_FILE = REPO_ROOT / "eyetrackapp" / "INNO" / "ETVR_SETUP.iss"

APP_VERSION_RE = re.compile(r'^APP_VERSION = ".*"$', re.MULTILINE)
ISS_VERSION_RE = re.compile(r'^#define MyAppVersion ".*"$', re.MULTILINE)
ISS_OUTPUT_RE = re.compile(r"^OutputBaseFilename=.*$", re.MULTILINE)


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
            if not check_only:
                path.write_text(text, encoding="utf-8", newline="")
                print(f"stamped {path.relative_to(REPO_ROOT)}", file=sys.stderr)

    print(version)
    print(safe)
    if check_only and dirty:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
