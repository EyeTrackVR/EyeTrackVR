"""FrameDrop manifest for the Steam Frame release (scripts/frame/write_framedrop_manifest.py)."""

import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "frame" / "write_framedrop_manifest.py"
spec = importlib.util.spec_from_file_location("write_framedrop_manifest", SCRIPT)
manifest_writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest_writer)

BASE = "https://github.com/EyeTrackVR/EyeTrackVR/releases/download/EyeTrackApp-0.3.0-BETA-9"


def run(monkeypatch, tmp_path, url):
    zip_path = tmp_path / "app.zip"
    zip_path.write_bytes(b"zip bytes")
    out = tmp_path / "app.framedrop.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "write_framedrop_manifest.py",
            "--zip",
            str(zip_path),
            "--url",
            url,
            "--out",
            str(out),
            "--manifest-url",
            f"{BASE}/app.framedrop.json",
        ],
    )
    manifest_writer.main()
    return json.loads(out.read_text(encoding="utf-8"))


def test_manifest_matches_framedrop_v1_schema(monkeypatch, tmp_path, capsys):
    manifest = run(monkeypatch, tmp_path, f"{BASE}/app.zip")
    assert manifest == {
        "schema": "framedrop.install/v1",
        "name": "EyeTrackVR",
        "files": [{"url": f"{BASE}/app.zip", "sha256": hashlib.sha256(b"zip bytes").hexdigest()}],
    }
    link = capsys.readouterr().out.split("FRAMEDROP_LINK=")[1].strip()
    parsed = urlparse(link)
    assert (parsed.netloc, parsed.path) == ("framedropvr.com", "/install")
    assert parse_qs(parsed.query) == {"manifest": [f"{BASE}/app.framedrop.json"]}


@pytest.mark.parametrize("url", ["http://example.com/app.zip", f"{BASE}/", f"{BASE}/app.tar.gz"])
def test_rejects_urls_framedrop_cannot_fetch(monkeypatch, tmp_path, url):
    with pytest.raises(SystemExit):
        run(monkeypatch, tmp_path, url)
