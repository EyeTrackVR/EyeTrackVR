"""The overlay binaries in EyeTrackApp/Tools must come from the pinned overlay/ submodule."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "EyeTrackApp" / "Tools"
REBUILD = "rebuild with scripts/build_overlay.bat (or scripts/build_overlay.sh on Linux)"


def _pinned_overlay_commit() -> str:
    # The index entry, so this also works before the submodule bump is committed
    # and without the submodule checked out (CI clones without submodules).
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("needs a git checkout")
    out = subprocess.run(
        ["git", "ls-files", "--stage", "--", "overlay"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    assert out and out[0] == "160000", "overlay/ is not registered as a submodule"
    return out[1]


@pytest.mark.parametrize("folder", ["", "linux", "linux-arm64"])
def test_overlay_binaries_match_pinned_submodule(folder):
    pinned = _pinned_overlay_commit()
    stamp = TOOLS / folder / "OVERLAY_COMMIT"
    assert stamp.is_file(), f"{stamp.relative_to(ROOT)} is missing; {REBUILD}"
    built = stamp.read_text(encoding="utf-8").strip()
    assert built == pinned, f"Tools/{folder} was built from overlay {built[:9]}, submodule pins {pinned[:9]}; {REBUILD}"


def test_gitmodules_points_at_org_overlay_repo():
    text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert "path = overlay" in text
    assert "url = https://github.com/EyeTrackVR/EyeTrackVR-Calibration-Overlay.git" in text
