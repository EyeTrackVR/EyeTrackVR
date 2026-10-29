"""Write the FrameDrop install manifest for a Steam Frame release zip.

Usage: python write_framedrop_manifest.py --zip <path> --url <zip-url>
                                          --out <manifest-path> --manifest-url <url>

FrameDrop (https://framedropvr.com/docs) reads a framedrop.install/v1 manifest,
downloads each file, unpacks zips and installs them to the paired headset.
Prints the "Install with FrameDrop" link for the manifest's hosted URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

APP_NAME = "EyeTrackVR"  # shown in the headset's Steam library


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_link(manifest_url: str) -> str:
    return "https://framedropvr.com/install?manifest=" + quote(manifest_url, safe="")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--manifest-url", required=True)
    args = parser.parse_args()

    if not args.url.startswith("https://") or not args.url.endswith(".zip"):
        raise SystemExit(f"FrameDrop needs an https URL ending in the zip filename: {args.url}")

    manifest = {
        "schema": "framedrop.install/v1",
        "name": APP_NAME,
        "files": [{"url": args.url, "sha256": sha256_of(args.zip)}],
    }
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"FRAMEDROP_LINK={install_link(args.manifest_url)}")


if __name__ == "__main__":
    main()
