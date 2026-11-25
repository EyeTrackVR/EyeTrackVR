"""Regenerate packaging/linux/requirements.txt from poetry.lock.

Usage: python packaging/export_requirements.py [--check]

The Linux x86_64 (packaging/linux/build.sh) and Steam Frame arm64
(packaging/steamframe/build.sh) releases install this file with --require-hashes,
so they bundle exactly the versions CI tests from poetry.lock. It is
`poetry export --with dev` (the dev group holds PyInstaller) with a header: one
file for every platform, the environment markers pick the Linux packages.

Run it after every `poetry lock` / `poetry add` and commit the result.
--check exits 1 when the committed file differs from a fresh export (CI runs it).

Needs Poetry with the export plugin (poetry self add poetry-plugin-export).
CI pins the versions it checks with; the export can differ slightly between
plugin versions, so regenerate with the same ones if the check disagrees.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "packaging" / "linux" / "requirements.txt"

HEADER = """\
# GENERATED from poetry.lock by packaging/export_requirements.py - do not edit.
# Regenerate after changing dependencies:  python packaging/export_requirements.py
# Installed with --require-hashes by packaging/linux/build.sh and
# packaging/steamframe/build.sh, so the Linux releases ship the tested versions.
"""


def export() -> str:
    try:
        result = subprocess.run(
            ["poetry", "export", "--format", "requirements.txt", "--with", "dev"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        sys.exit("ERROR: poetry not found on PATH")
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR: poetry export failed (is poetry-plugin-export installed?)\n{e.stderr}")
    body = result.stdout.replace("\r\n", "\n")
    if "--hash=sha256:" not in body:
        sys.exit("ERROR: poetry export produced no hashes")
    return HEADER + body


def main() -> int:
    fresh = export()
    if "--check" in sys.argv[1:]:
        current = TARGET.read_text(encoding="utf-8").replace("\r\n", "\n") if TARGET.exists() else ""
        if current != fresh:
            print(
                f"ERROR: {TARGET.relative_to(REPO_ROOT)} is out of date with poetry.lock; "
                "run: python packaging/export_requirements.py",
                file=sys.stderr,
            )
            return 1
        print(f"{TARGET.relative_to(REPO_ROOT)} matches poetry.lock")
        return 0
    with TARGET.open("w", encoding="utf-8", newline="\n") as f:
        f.write(fresh)
    print(f"wrote {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
