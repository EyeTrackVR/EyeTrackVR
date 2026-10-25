"""Bug reports: encrypted issue bundles, separate receipts and quotas, and the report window."""
import io
import json
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
import zipfile

import pyrage
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EyeTrackApp"))
from contributions import report_window
from contributions.client import ContributionClient, ISSUE_QUOTA_MESSAGES, ServiceError, issue_home, receipt_home
from contributions.report_window import ReportWindow, previous_log, write_tail

TERMS = {"dataset": {"version": "dataset-test", "text": "18+ dataset notice"},
         "issue": {"version": "issue-test", "text": "18+ issue notice"}}


@pytest.fixture
def issue_client(tmp_path):
    identity = pyrage.x25519.Identity.generate()
    config = {"protocol": 3, "enabled": True, "recipients": [str(identity.to_public())], "chunk_bytes": 8192,
              "max_bytes": {"dataset": 131072, "issue": 65536}, "terms": TERMS, "issue_quota_full": None}
    client = ContributionClient(directory=tmp_path / "issues", recipients=[str(identity.to_public())])
    client.config = lambda: config
    return client, identity


def test_issue_report_is_encrypted_redacted_and_bound(issue_client, tmp_path):
    client, identity = issue_client
    log = tmp_path / "app.log"
    log.write_text("ERROR crash at C:\\Users\\alice\\EyeTrackVR from 192.168.1.20 mail bob@example.com\n",
                   encoding="utf-8")
    sid = client.prepare_issue("Tracking froze after 5 minutes", [log], TERMS["issue"],
                               threading.Event(), lambda *a: None)
    row = client.read(sid)
    assert row["kind"] == "issue" and "hmd" not in row and row["state"] == "prepared"
    plain = pyrage.decrypt(client.paths(sid)[1].read_bytes(), [identity])
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        assert archive.read("description.txt").decode() == "Tracking froze after 5 minutes"
        text = archive.read("log-1.txt").decode()
        bound = json.loads(archive.read("submission.json"))
    assert "alice" not in text and "192.168.1.20" not in text and "bob@example.com" not in text
    assert "<HOME>" in text and "<IP>" in text and "<EMAIL>" in text
    assert bound["kind"] == "issue" and bound["id"] == sid and "hmd" not in bound
    assert bound["terms_version"] == "issue-test"


def test_issue_report_respects_issue_size_limit(issue_client, tmp_path):
    client, _ = issue_client
    big = tmp_path / "big.log"
    big.write_text(__import__("os").urandom(100000).hex(), encoding="utf-8")
    with pytest.raises(ValueError, match="report exceeds the upload size limit"):
        client.prepare_issue("Too big", [big], TERMS["issue"], threading.Event(), lambda *a: None)


def test_issue_quota_refusal_uses_report_wording(issue_client):
    client, _ = issue_client
    sid = client.prepare_issue("Report", [], TERMS["issue"], threading.Event(), lambda *a: None)
    def request(method, path, token=None, **kwargs):
        if method == "GET":
            raise ServiceError(404)
        assert kwargs["json"]["kind"] == "issue" and kwargs["json"]["terms_version"] == "issue-test"
        raise ServiceError(429, "network_quota")
    client.request = request
    with pytest.raises(ValueError) as error:
        client.resume(sid, lambda *a: "token", lambda *a: False, threading.Event(), lambda *a: None)
    assert str(error.value) == ISSUE_QUOTA_MESSAGES["network_quota"]


def test_issue_receipts_live_apart_from_dataset_contributions():
    assert issue_home().parent == receipt_home().parent
    assert issue_home() != receipt_home()


def test_write_tail_keeps_newest_utf8_text(tmp_path):
    source = tmp_path / "eyetrackapp-1.log"
    source.write_bytes(("old line\n" * 100).encode() + "neue Zeile ü\n".encode() + b"\xff\x00end\n")
    out = tmp_path / "tail.txt"
    write_tail(source, out, limit=64)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("[showing the last")
    assert text.endswith("end\n") and "\x00" not in text and "neue Zeile ü" in text


def test_previous_log_skips_the_current_session(tmp_path, monkeypatch):
    import utils.logging_utils as logging_utils
    monkeypatch.setattr(logging_utils, "log_directory", lambda: tmp_path)
    older, current = tmp_path / "eyetrackapp-20260101-000000.log", tmp_path / "eyetrackapp-20260102-000000.log"
    older.write_text("crash", encoding="utf-8")
    current.write_text("now", encoding="utf-8")
    now = time.time()
    import os
    os.utime(older, (now - 100, now - 100))
    os.utime(current, (now, now))
    assert previous_log(current) == older
    current.unlink()
    assert previous_log(None) == older


@pytest.fixture(scope="module")
def root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No desktop display available")
    root.withdraw()
    yield root
    root.destroy()


def drain(root, condition):
    until = time.monotonic() + 4
    while not condition() and time.monotonic() < until:
        root.update()
        time.sleep(0.01)
    assert condition()


class FakeClient:
    def __init__(self, directory):
        self.directory = directory
        self.prepared, self.resumed, self.withdrawn = [], [], []
        self.fail = True
        self.rows = []

    def exclusive(self):
        import contextlib
        return contextlib.nullcontext()

    def config(self):
        return {"enabled": True, "terms": TERMS, "issue_quota_full": None}

    def prepare_issue(self, description, logs, terms, cancel, progress):
        sid = f"{len(self.prepared):032x}"
        self.prepared.append((sid, description, [Path(p).read_text(encoding="utf-8") for p in logs], terms))
        self.rows.append({"id": sid, "kind": "issue", "state": "prepared"})
        return sid

    def resume(self, sid, verify, consent, cancel, progress):
        self.resumed.append(sid)
        if self.fail:
            raise ValueError("Today's bug report limit")
        return "pending"

    def receipts(self):
        return [r for r in self.rows if r["state"] == "prepared"]

    def withdraw(self, sid):
        self.withdrawn.append(sid)
        next(r for r in self.rows if r["id"] == sid)["state"] = "cancelled"
        return "cancelled"


def test_report_window_retries_the_same_report_and_remakes_edited_ones(root, tmp_path, monkeypatch):
    log = tmp_path / "eyetrackapp-now.log"
    log.write_text("session log line\n", encoding="utf-8")
    monkeypatch.setattr("utils.logging_utils.current_log_path", lambda: log)
    fake = FakeClient(tmp_path)
    ui = ReportWindow(root, details=lambda: "App: test", client=fake)
    ui.window.withdraw()
    drain(root, lambda: ui.config is not None and not ui.busy)
    ui.description.delete("1.0", "end")
    root.update()
    assert str(ui.send_button.cget("state")) == "disabled"
    ui.description.insert("1.0", "Camera stops after an hour")
    ui.agree.set(True)
    ui.update_buttons()
    # The separate transfer consent is required too.
    assert str(ui.send_button.cget("state")) == "disabled"
    ui.agree_transfer.set(True)
    ui.update_buttons()
    assert str(ui.send_button.cget("state")) == "normal"

    ui.send()
    drain(root, lambda: not ui.busy)
    sid, description, logs, terms = fake.prepared[0]
    assert description.startswith("Camera stops after an hour") and "--- App details ---\nApp: test" in description
    assert logs == ["session log line\n"] and terms == TERMS["issue"]
    assert "bug report limit" in ui.status.get()
    # Consent is asked again for each attempt.
    assert not ui.agree.get() and not ui.agree_transfer.get()

    ui.agree.set(True)
    ui.agree_transfer.set(True)
    ui.send()
    drain(root, lambda: not ui.busy)
    assert len(fake.prepared) == 1 and fake.resumed == [sid, sid]

    ui.description.insert("end", " (edited)")
    ui.agree.set(True)
    ui.agree_transfer.set(True)
    fake.fail = False
    ui.send()
    drain(root, lambda: not ui.busy)
    assert len(fake.prepared) == 2 and fake.withdrawn == [sid]
    # A "Report sent" panel with the ID replaces the form.
    assert ui.sent_panel.winfo_manager() and not ui.form.winfo_manager()
    assert ui.sent_title.cget("text") == "Report sent" and ui.status.get() == ""
    assert ui.sent_id.get() == fake.prepared[1][0][:8]
    assert ui.description_text() == ""
    ui.window.destroy()


def test_dataset_window_ignores_issue_receipts(root, tmp_path):
    from contributions.client import save
    from contributions.window import ContributionWindow
    client = ContributionClient(directory=tmp_path / "private")
    client.config = lambda: {"enabled": True, "terms": TERMS}
    base = {"schema": 3, "api": client.service, "withdrawal_token": "A" * 43, "sha256": "0" * 64, "size": 10,
            "chunk_bytes": 1024, "chunks": ["0" * 64], "prepared": "2026-10-24", "state": "pending"}
    for sid, kind in (("a" * 32, "dataset"), ("b" * 32, "issue")):
        save(client.paths(sid)[0], {**base, "id": sid, "kind": kind})
    ui = ContributionWindow(root, client=client)
    ui.window.withdraw()
    drain(root, lambda: ui.config is not None)
    assert list(ui.rows) == ["a" * 32]
    ui.window.destroy()
