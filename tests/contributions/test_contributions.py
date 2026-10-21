"""Run independently: pytest --confcutdir=tests/contributions tests/contributions."""
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import threading
import zipfile
import zlib

import pytest
import requests
import pyrage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EyeTrackApp"))
from contributions.client import ContributionClient, Paused, ServiceError, digest, save
from contributions import verification


def frame(width=240, height=240):
    """A PNG signature/IHDR header followed by incompressible test bytes."""
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + header
            + struct.pack(">I", zlib.crc32(b"IHDR" + header)) + os.urandom(25000))


@pytest.fixture
def setup_client(tmp_path):
    identity = pyrage.x25519.Identity.generate()
    public = str(identity.to_public())
    config = {"protocol": 3, "enabled": True, "recipients": [public], "chunk_bytes": 8192,
              "max_bytes": {"dataset": 131072}, "terms": {"dataset": {"version": "dataset-test", "text": "18+ private test notice"}}}
    client = ContributionClient(directory=tmp_path / "private", recipients=[public])
    source = tmp_path / "capture.zip"
    pixels = frame()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("capture_manifest.json", json.dumps({"schema": "etvr-capture-v1", "eyes": []}))
        archive.writestr("v6_Abc123456_Left_01_gaze.png", pixels)
    client.config = lambda: config
    return client, config, identity, source, pixels


def prepared(setup_client):
    client, config, identity, source, pixels = setup_client
    sid = client.prepare(source, "Free typed HMD", config["terms"]["dataset"], threading.Event(), lambda *a: None)
    return client, sid


def test_real_age_encryption_and_receipt_evidence(setup_client):
    client, config, identity, source, pixels = setup_client
    client, sid = prepared(setup_client)
    row = client.read(sid)
    plain = pyrage.decrypt(client.paths(sid)[1].read_bytes(), [identity])
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        assert archive.read("v6_Abc123456_Left_01_gaze.png") == pixels
        bound = json.loads(archive.read("submission.json"))
    assert row["terms_sha256"] == hashlib.sha256(config["terms"]["dataset"]["text"].encode()).hexdigest()
    assert row["hmd"] == "Free typed HMD" and row["state"] == "prepared" and row["schema"] == 3
    # The HMD text and consent evidence are bound to this submission inside the ciphertext.
    assert bound == {"schema": "etvr-submission-v1", "id": sid, "kind": "dataset", "hmd": "Free typed HMD",
                     "terms_version": row["terms_version"], "terms_sha256": row["terms_sha256"]}


def test_service_cannot_choose_the_encryption_key(setup_client):
    client, config, _, source, _ = setup_client
    unpinned = ContributionClient(directory=client.directory)
    real = config.copy()
    unpinned.request = client.request = lambda *a, **kw: real
    del client.config
    attacker = str(pyrage.x25519.Identity.generate().to_public())
    for advertised in ([attacker], [*config["recipients"], attacker], []):
        real["recipients"] = advertised
        with pytest.raises(ValueError, match="cannot verify"):
            client.prepare(source, "HMD", config["terms"]["dataset"], threading.Event(), lambda *a: None)
    real.update(recipients=config["recipients"], protocol=2)
    with pytest.raises(ValueError, match="cannot verify"):
        client.config()
    # A service that is not pinned in this release can never receive an upload.
    real["protocol"] = 3
    with pytest.raises(ValueError, match="cannot verify"):
        unpinned.config()
    assert client.config()["recipients"] == config["recipients"]
    assert not client.receipts() and not list(client.directory.glob("*.age"))


def test_hmd_text_is_cleaned_and_invalid_captures_fail_before_encryption(setup_client, tmp_path):
    client, config, identity, source, _ = setup_client
    sid = client.prepare(source, "  Bigscreen\u202e Beyond\n2e ", config["terms"]["dataset"],
                         threading.Event(), lambda *a: None)
    assert client.read(sid)["hmd"] == "Bigscreen Beyond 2e"
    for hmd in ("", "\u200b\n", "x" * 161):
        with pytest.raises(ValueError, match="HMD"):
            client.prepare(source, hmd, config["terms"]["dataset"], threading.Event(), lambda *a: None)
    bogus = tmp_path / "bogus.zip"
    with zipfile.ZipFile(bogus, "w") as archive:
        archive.writestr("capture_manifest.json", json.dumps({"schema": "etvr-capture-v1", "eyes": []}))
        archive.writestr("v6_Abc123456_Left_01_gaze.png", b"not a png")
    with pytest.raises(ValueError, match="Invalid PNG"):
        client.prepare(bogus, "HMD", config["terms"]["dataset"], threading.Event(), lambda *a: None)
    assert [row["id"] for row in client.receipts()] == [sid]


def test_legacy_receipt_cannot_start_a_new_plaintext_session(setup_client):
    client, sid = prepared(setup_client)
    receipt = client.read(sid)
    receipt["schema"] = 2
    save(client.paths(sid)[0], receipt)
    def missing(*a, **kw):
        raise ServiceError(404)
    client.request = missing
    with pytest.raises(ValueError, match="older EyeTrackVR"):
        client.resume(sid, lambda *a: "token", lambda *a: True, threading.Event(), lambda *a: None)


def test_disabled_or_changed_consent_never_prepares_upload(setup_client):
    client, config, _, source, _ = setup_client
    with pytest.raises(ValueError, match="terms changed"):
        client.prepare(source, "HMD", {"version": "old", "text": "old"}, threading.Event(), lambda *a: None)
    config["enabled"] = False
    with pytest.raises(ValueError, match="closed"):
        client.prepare(source, "HMD", config["terms"]["dataset"], threading.Event(), lambda *a: None)
    assert not client.receipts()


def test_interrupt_resume_skips_confirmed_chunks_and_cleans_payload(setup_client):
    client, sid = prepared(setup_client)
    row = client.read(sid)
    accepted, calls = {}, []
    created = False
    interrupt = True
    progress = []
    def request(method, path, token=None, **kwargs):
        nonlocal created
        assert token == row["withdrawal_token"]
        if method == "GET":
            if not created:
                raise ServiceError(404)
            return {**row, "status": "uploading", "received": [{"part": p, "sha256": h} for p,h in accepted.items()]}
        if path == "/v1/submissions":
            created = True
            assert kwargs["json"]["challenge"] == "in-app-token"
            assert "hmd" not in kwargs["json"] and "Free typed" not in json.dumps(kwargs["json"])
            return {"status": "uploading", "received": []}
        if method == "PUT":
            part = int(path.rsplit("/", 1)[1])
            calls.append(part)
            if part == 1 and interrupt:
                raise requests.ConnectionError("simulated network loss")
            # Exercise the actual requests file-like body and byte progress callback.
            stream = kwargs["data"]
            data = b"".join(iter(lambda: stream.read(2048), b""))
            assert len(data) == int(kwargs["headers"]["Content-Length"])
            accepted[part] = hashlib.sha256(data).hexdigest()
            assert accepted[part] == row["chunks"][part]
            return {}
        assert path.endswith("/complete")
        return {"status": "pending"}
    client.request = request
    cancel = threading.Event()
    # Speed retries without changing cancellation semantics.
    cancel.wait = lambda _: False
    with pytest.raises(requests.ConnectionError):
        client.resume(sid, lambda *a: "in-app-token", lambda *a: pytest.fail("Unexpected consent"), cancel,
                      lambda *p: progress.append(p))
    assert 0 in accepted and calls.count(0) == 1
    exact_hash = digest(client.paths(sid)[1])
    interrupt = False
    assert client.resume(sid, lambda *a: pytest.fail("Resume must not verify again"), lambda *a: False,
                         cancel, lambda *p: progress.append(p)) == "pending"
    assert calls.count(0) == 1 and row["sha256"] == exact_hash
    assert not client.paths(sid)[1].exists()
    assert any(0 < done < total for _, done, total in progress)


def test_pause_and_payload_tampering_preserve_receipt(setup_client):
    client, sid = prepared(setup_client)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Paused):
        client.resume(sid, None, None, cancel, lambda *a: None)
    assert client.paths(sid)[1].exists()
    client.paths(sid)[1].write_bytes(b"tampered")
    def missing(*a, **kw):
        raise ServiceError(404)
    client.request = missing
    with pytest.raises(ValueError, match="missing or modified"):
        client.resume(sid, None, None, threading.Event(), lambda *a: None)
    assert client.read(sid)["withdrawal_token"]


def test_withdraw_is_confirmed_before_deleting_local_payload(setup_client):
    client, sid = prepared(setup_client)
    row = client.read(sid)
    def failure(*a, **kw):
        raise requests.ConnectionError("offline")
    client.request = failure
    with pytest.raises(requests.ConnectionError):
        client.withdraw(sid)
    assert client.paths(sid)[1].exists() and client.read(sid)["state"] == "prepared"
    def withdraw(method, path, token=None, **kwargs):
        assert method == "POST" and path.endswith("/withdraw") and token == row["withdrawal_token"]
        return {"status": "withdrawn"}
    client.request = withdraw
    assert client.withdraw(sid) == "withdrawn"
    assert not client.paths(sid)[1].exists()
    assert client.read(sid)["withdrawal_token"] == row["withdrawal_token"]


def test_receipts_cannot_redirect_tokens_or_live_in_git(setup_client, tmp_path):
    client, sid = prepared(setup_client)
    row = client.read(sid)
    row["api"] = "https://attacker.example"
    with pytest.raises(ValueError, match="Invalid"):
        client.validate(row)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(ValueError, match="outside Git"):
        ContributionClient(directory=repo / "private")


def test_requests_have_no_redirects_or_url_secrets(setup_client, monkeypatch):
    client = setup_client[0]
    # Restore the actual request method (config alone was replaced by the fixture).
    captured = {}
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def json(self): return {}
    def request(method, url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()
    monkeypatch.setattr(requests, "request", request)
    client.request("GET", "/v1/config", "private-test-capability")
    assert "private-test-capability" not in captured["url"]
    assert captured["allow_redirects"] is False
    assert captured["headers"]["Authorization"] == "Bearer private-test-capability"


def test_verification_cancel_terminates_helper_without_browser(monkeypatch):
    calls = []
    class Process:
        def poll(self): return None
        def terminate(self): calls.append("terminate")
        def wait(self, **kw): pass
    def launch(command, **kwargs):
        calls.append(command)
        return Process()
    monkeypatch.setattr(verification.subprocess, "Popen", launch)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Paused):
        verification.verify_in_app("https://verify.example", cancel)
    assert calls[-1] == "terminate"
    assert "--contribution-verification" in calls[0]


def test_embedded_helper_disables_external_navigation(monkeypatch):
    import webview
    class Event:
        def __iadd__(self, callback): return self
    class Window:
        events = type("Events", (), {"closed": Event(), "shown": Event()})()
    captured = {}
    def create(title, url, **kwargs):
        captured.update(url=url, **kwargs)
        return Window()
    monkeypatch.setattr(webview, "create_window", create)
    monkeypatch.setattr(webview, "start", lambda *a, **kw: captured.update(start=kw))
    verification.run_helper("https://verify.example", "1234", "test-only-nonce")
    assert webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is False
    assert webview.settings["ALLOW_FILE_URLS"] is False
    assert webview.settings["ALLOW_DOWNLOADS"] is False
    assert captured["url"] == "https://verify.example/challenge?embedded=1"
    assert not captured.get("js_api")


@pytest.mark.parametrize("code, expected", [("daily_quota", "Today's upload limit"),
                                            ("network_quota", "Your network"),
                                            ("lifetime_quota", "full for now"),
                                            ("<script>", "upload limit has been reached"),
                                            (None, "upload limit has been reached")])
def test_quota_refusals_explain_what_happened_and_who_to_ping(setup_client, monkeypatch, code, expected):
    client = setup_client[0]
    class Response:
        status_code = 429
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def json(self): return {"error": "server text is never shown", "code": code}
    monkeypatch.setattr(requests, "request", lambda *a, **kw: Response())
    with pytest.raises(ServiceError) as error:
        client.request("POST", "/v1/submissions", "capability", json={})
    assert expected in str(error.value) and "prohurtz on Discord" in str(error.value)
    assert "server text" not in str(error.value)
