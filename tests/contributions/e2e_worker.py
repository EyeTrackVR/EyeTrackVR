"""Invoked by ETVR-Dataset-Sync's optional real workerd integration test."""
import io
import json
import os
from pathlib import Path
import sys
import threading
import zipfile

import pyrage
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EyeTrackApp"))
from contributions.client import ContributionClient, digest

base, identity_file, directory = sys.argv[1:]
root = Path(directory)
client = ContributionClient(base, root / "desktop-private")
pixels = os.urandom(40000)
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

admin = "fixture-only-maintainer-token-not-a-real-secret-0001"
manifest = client.request("GET", "/v1/admin/submissions/" + sid, admin)
encrypted = b""
for chunk in manifest["chunks"]:
    response = requests.get(base + "/v1/admin/submissions/" + sid + "/chunks/" + str(chunk["part"]),
                            headers={"Authorization": "Bearer " + admin},timeout=30)
    response.raise_for_status()
    encrypted += response.content
key = next(line for line in Path(identity_file).read_text().splitlines() if line.startswith("AGE-SECRET-KEY-"))
plain = pyrage.decrypt(encrypted, [pyrage.x25519.Identity.from_str(key)])
with zipfile.ZipFile(io.BytesIO(plain)) as archive:
    assert archive.read("v6_Abc123456_Left_01_gaze.png") == pixels
assert manifest["terms_sha256"] == row["terms_sha256"]
assert client.withdraw(sid) == "withdrawn"
response = requests.get(base + "/v1/admin/submissions/" + sid + "/chunks/0",
                        headers={"Authorization": "Bearer " + admin},timeout=30)
assert response.status_code in (403,404,409)
print(json.dumps({"id":sid,"resumed":True,"decrypted":True,"withdrawn":True}))
