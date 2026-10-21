"""Invoked by ETVR-Dataset-Sync's optional real workerd integration test."""
import io
import json
import os
from pathlib import Path
import struct
import sys
import threading
import zipfile
import zlib

import pyrage
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EyeTrackApp"))
from contributions.client import ContributionClient, digest

base, identity_file, directory = sys.argv[1:]
root = Path(directory)
key = next(line for line in Path(identity_file).read_text().splitlines() if line.startswith("AGE-SECRET-KEY-"))
identity = pyrage.x25519.Identity.from_str(key)
# A loopback service is never pinned in a release; the test pins its fixture key explicitly.
client = ContributionClient(base, root / "desktop-private", recipients=[str(identity.to_public())])
header = struct.pack(">IIBBBBB", 240, 240, 8, 0, 0, 0, 0)
pixels = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + header
          + struct.pack(">I", zlib.crc32(b"IHDR" + header)) + os.urandom(40000))
source = root / "desktop-capture.zip"
with zipfile.ZipFile(source, "w") as archive:
    archive.writestr("capture_manifest.json", json.dumps({"schema": "etvr-capture-v1", "eyes": []}))
    archive.writestr("v6_Abc123456_Left_01_gaze.png", pixels)
cancel = threading.Event()
cancel.wait = lambda _: False
terms = client.config()["terms"]["dataset"]
sid = client.prepare(source, "Desktop free typed HMD", terms, cancel, lambda *a: None)
row = client.read(sid)
actual_request = client.request
attempts = []
def interrupted(method, path, token=None, **kwargs):
    if method == "PUT":
        part = int(path.rsplit("/", 1)[1])
        attempts.append(part)
        if part == 1:
            raise requests.ConnectionError("Synthetic interruption")
    return actual_request(method, path, token, **kwargs)
client.request = interrupted
try:
    client.resume(sid, lambda *a: "good-desktop-token", lambda *a: False, cancel, lambda *a: None)
except requests.ConnectionError:
    pass
else:
    raise AssertionError("Expected interruption")
assert attempts.count(0) == 1
assert digest(client.paths(sid)[1]) == row["sha256"]
client.request = actual_request
def unexpected(*a):
    raise AssertionError("Existing uploads must not reverify or reconfirm consent")
assert client.resume(sid, unexpected, unexpected, cancel, lambda *a: None) == "pending"
assert not client.paths(sid)[1].exists()

sync = "fixture-only-read-only-sync-token-not-a-real-secret-0002"
manifest = client.request("GET", "/v1/sync/submissions/" + sid, sync)
encrypted = b""
for chunk in manifest["chunks"]:
    response = requests.get(base + "/v1/sync/submissions/" + sid + "/chunks/" + str(chunk["part"]),
                            headers={"Authorization": "Bearer " + sync},timeout=30)
    response.raise_for_status()
    encrypted += response.content
plain = pyrage.decrypt(encrypted, [identity])
with zipfile.ZipFile(io.BytesIO(plain)) as archive:
    assert archive.read("v6_Abc123456_Left_01_gaze.png") == pixels
    assert json.loads(archive.read("submission.json"))["hmd"] == "Desktop free typed HMD"
assert manifest["hmd"] is None
assert manifest["terms_sha256"] == row["terms_sha256"]
assert client.withdraw(sid) == "withdrawn"
response = requests.get(base + "/v1/sync/submissions/" + sid + "/chunks/0",
                        headers={"Authorization": "Bearer " + sync},timeout=30)
assert response.status_code in (403,404,409)
print(json.dumps({"id":sid,"resumed":True,"decrypted":True,"withdrawn":True}))
