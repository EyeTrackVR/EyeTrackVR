"""The calibration overlay comes from the overlay/ submodule, whose dist/ ships
prebuilt runtimes. Each runtime's SOURCE_TREE must match the overlay sources it
claims to be built from, so a source change without a rebuild can't ship."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "overlay"
DIST = OVERLAY / "dist"
REBUILD = "run build-dist.bat in the overlay repo and commit dist/"


def _source_tree() -> str:
    if shutil.which("git") is None or not (OVERLAY / ".git").exists():
        pytest.skip("needs the overlay/ submodule checked out with git")
    inputs = (DIST / "SOURCE_INPUTS").read_text(encoding="utf-8").split()
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--", *inputs], cwd=OVERLAY, capture_output=True, check=True
    ).stdout
    return (
        subprocess.run(["git", "hash-object", "--stdin"], cwd=OVERLAY, input=listing, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )


@pytest.mark.parametrize("folder", ["windows", "linux", "linux-arm64"])
def test_overlay_runtime_matches_its_sources(folder):
    stamp = DIST / folder / "SOURCE_TREE"
    assert stamp.is_file(), f"overlay/dist/{folder} is missing; {REBUILD}"
    assert stamp.read_text(encoding="utf-8").strip() == _source_tree(), (
        f"overlay/dist/{folder} was built from different overlay sources; {REBUILD}"
    )


def test_gitmodules_points_at_org_overlay_repo():
    text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert "path = overlay" in text
    assert "url = https://github.com/EyeTrackVR/EyeTrackVR-Calibration-Overlay.git" in text
