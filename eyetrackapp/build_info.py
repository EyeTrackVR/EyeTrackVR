"""
What kind of build is running.

packaging/build_release.bat sets ETVR_RELEASE_BUILD=1 for PyInstaller, and the Windows
spec then bundles an empty ``release_build`` file. Runs from source, and builds made
without the release script, have no marker and keep the developer-only options.
"""

import sys
from pathlib import Path

MARKER = "release_build"


def is_release_build() -> bool:
    base = getattr(sys, "_MEIPASS", None)
    return bool(base) and (Path(base) / MARKER).is_file()
