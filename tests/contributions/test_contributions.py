"""Run independently: pytest --confcutdir=tests/contributions tests/contributions."""
import hashlib
import json
from pathlib import Path
import sys
import threading
import zipfile

import pytest
import requests
import pyrage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EyeTrackApp"))
from contributions.client import ContributionClient, Paused, ServiceError, digest, save
from contributions import verification


@pytest.fixture
def setup_client(tmp_path):
    identity = pyrage.x25519.Identity.generate()
    config = {"enabled": True, "recipient": str(identity.to_public()), "chunk_bytes": 8192,
              "max_bytes": {"dataset": 131072}, "terms": {"dataset": {"version": "dataset-test", "text": "18+ private test notice"}}}
    client = ContributionClient(directory=tmp_path / "private")
    source = tmp_path / "capture.zip"
    pixels = __import__("os").urandom(25000)
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
    with zipfile.ZipFile(__import__("io").BytesIO(plain)) as archive:
        assert archive.read("v6_Abc123456_Left_01_gaze.png") == pixels
    assert row["terms_sha256"] == hashlib.sha256(config["terms"]["dataset"]["text"].encode()).hexdigest()
    assert row["hmd"] == "Free typed HMD" and row["state"] == "prepared"


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
