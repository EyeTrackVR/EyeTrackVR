"""Tk lifecycle and capture handoff checks without starting cameras or models."""

from pathlib import Path
import sys
import time
import tkinter as tk

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EyeTrackApp"))
from contributions.client import ContributionClient, save
from contributions.window import DATASET_CONSENTS, ContributionWindow


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


def window(root, tmp_path, enabled=True):
    client = ContributionClient(directory=tmp_path / "private")
    config = {"enabled": enabled, "terms": {"dataset": {"version": "test", "text": "Current 18+ terms"}}}
    client.config = lambda: config
    ui = ContributionWindow(root, client=client)
    ui.window.withdraw()
    drain(root, lambda: ui.config is not None)
    return ui


def test_terms_are_visible_and_consent_not_preselected(root, tmp_path):
    ui = window(root, tmp_path)
    assert "Current 18+ terms" in ui.notice.get("1.0", "end")
    assert not ui.agree.get()
    ui.start_upload()
    assert not ui.busy and "agree" in ui.status.get()
    ui.close()


def test_notice_sections_render_as_headings_without_changing_wording(root, tmp_path):
    client = ContributionClient(directory=tmp_path / "private")
    text = (
        "Dataset agreement\n\nBy ticking both boxes you confirm:\n1. First statement.\n2. Second statement.\n\n"
        "Who we are. Fovea Labs LLC runs this.\n\nHow long we keep it. Our schedule.\n- Recordings: 365 days."
    )
    client.config = lambda: {"enabled": True, "terms": {"dataset": {"version": "test", "text": text}}}
    ui = ContributionWindow(root, client=client)
    ui.window.withdraw()
    drain(root, lambda: ui.config is not None)
    shown = ui.notice.get("1.0", "end")
    for words in ("1. First statement.", "2. Second statement.", "Fovea Labs LLC runs this.", "Recordings: 365 days."):
        assert words in shown
    headings = ui.notice.tag_ranges("heading")
    assert [ui.notice.get(a, b).strip() for a, b in zip(headings[::2], headings[1::2])] == [
        "Who we are",
        "How long we keep it",
    ]
    assert ui.notice.yview()[0] == 0
    # Short labels that point at the numbered statements in the notice.
    assert (ui.consent.cget("text"), ui.consent_sensitive.cget("text")) == DATASET_CONSENTS
    assert not any(label.startswith("Statement") for label in DATASET_CONSENTS)
    # The page has its own title, so the notice's title line is not repeated; the wording otherwise is.
    assert "Dataset agreement" not in shown
    ui.show_step(2)
    assert "Tick both boxes" in ui.upload_hint.cget("text")
    ui.agree.set(True)
    ui.agree_sensitive.set(True)
    ui.update_navigation()
    assert ui.upload_hint.cget("text") == ""
    ui.close()


def test_closed_collection_still_offers_withdrawal(root, tmp_path):
    ui = window(root, tmp_path, enabled=False)
    assert str(ui.upload.cget("state")) == "disabled"
    # Per-contribution actions wait for a selection, then stay available while collection is closed.
    assert str(ui.withdraw_button.cget("state")) == "disabled"
    ui.rows["d" * 32] = {"id": "d" * 32, "state": "pending", "size": 1024**2}
    ui.history.insert(
        "", "end", iid="d" * 32, values=("2026-10-20", "Test HMD", "Awaiting review", "1.0 MiB", "dddddddd")
    )
    ui.history.selection_set("d" * 32)
    ui.update_history_buttons()
    assert str(ui.withdraw_button.cget("state")) == "normal"
    assert "closed" in ui.status.get()
    ui.close()


def test_worker_progress_and_pause_do_not_touch_tk_from_worker(root, tmp_path):
    ui = window(root, tmp_path)

    def operation():
        ui.report_progress("Uploading", 50, 100)
        assert ui.cancel.wait(3)
        return ("status", "pending")

    ui.run(operation)
    assert ui.busy
    ui.close()
    assert ui.cancel.is_set() and ui.window.winfo_exists()
    drain(root, lambda: not ui.busy)
    # The Upload page reports the outcome; the footer only carries errors and live progress.
    assert ui.upload_state == "complete" and ui.status.get() == ""
    ui.close()


def test_recording_advances_to_readable_agreement_before_upload(root, tmp_path):
    ui = window(root, tmp_path)
    capture = tmp_path / "reviewed.zip"
    capture.write_bytes(b"test fixture; not uploaded")
    ui.hmd.set("Test HMD")
    ui.capture_started()
    ui.capture_stopped(capture)
    assert ui.step == 2
    assert ui._capture_path == capture.resolve()
    assert "Automatically attached" in ui.selection.get()
    assert not hasattr(ui, "pick_source")
    assert not hasattr(ui, "choose")
    assert "Current 18+ terms" in ui.notice.get("1.0", "end")
    assert not ui.agree.get() and not ui.agree_sensitive.get()
    assert str(ui.upload.cget("state")) == "disabled"
    ui.agree.set(True)
    ui.update_navigation()
    # The separate sensitive-data/transfer consent is required too.
    assert str(ui.upload.cget("state")) == "disabled"
    ui.agree_sensitive.set(True)
    ui.update_navigation()
    assert str(ui.upload.cget("state")) == "normal"
    ui.close()


def test_connection_failure_never_leaves_agreement_blank(root, tmp_path):
    client = ContributionClient(directory=tmp_path / "private")

    def offline():
        raise ValueError("Offline")

    client.config = offline
    ui = ContributionWindow(root, client=client)
    ui.window.withdraw()
    drain(root, lambda: not ui.busy)
    ui.show_step(2)
    assert "Fovea Labs LLC" in ui.notice.get("1.0", "end")
    assert "support@fovea-labs.com" in ui.notice.get("1.0", "end")
    # The short labels stay in place whichever notice is shown.
    assert (ui.consent.cget("text"), ui.consent_sensitive.cget("text")) == DATASET_CONSENTS
    assert str(ui.upload.cget("state")) == "disabled"
    assert "offline" in ui.availability.get().lower()
    ui.close()


def test_cancelled_capture_cannot_reuse_previous_recording(root, tmp_path):
    ui = window(root, tmp_path)
    capture = tmp_path / "previous.zip"
    capture.write_bytes(b"synthetic fixture")
    ui.capture_stopped(capture)
    assert ui._capture_path is not None
    ui.capture_started()
    assert ui._capture_path is None
    ui.capture_stopped(None)
    ui.agree.set(True)
    ui.agree_sensitive.set(True)
    ui.update_navigation()
    assert ui.step == 1 and ui._capture_path is None
    assert str(ui.upload.cget("state")) == "disabled"
    ui.start_upload()
    assert not ui.busy
    ui.close()


def test_existing_preparation_cannot_create_another_submission(root, tmp_path):
    ui = window(root, tmp_path)
    capture = tmp_path / "captured.zip"
    capture.write_bytes(b"synthetic fixture")
    ui.capture_stopped(capture)
    ui._capture_receipt = "a" * 32
    ui.agree.set(True)
    ui.agree_sensitive.set(True)
    ui.update_navigation()
    assert str(ui.upload.cget("state")) == "disabled"
    ui.close()


def test_capture_engine_uses_one_window_and_attaches_its_result(root, tmp_path, monkeypatch):
    from types import SimpleNamespace
    import data_collection

    monkeypatch.setattr("contributions.client.receipt_home", lambda: tmp_path / "private")
    monkeypatch.setattr(
        ContributionClient,
        "config",
        lambda _: {"enabled": True, "terms": {"dataset": {"version": "test", "text": "Current terms"}}},
    )
    camera = SimpleNamespace(add_extra_output_queue=lambda _: None, remove_extra_output_queue=lambda _: None)
    eye = SimpleNamespace(started=lambda: True, _effective_camera=lambda: camera, eye_id=SimpleNamespace(name="LEFT"))
    capture = tmp_path / "only_this_capture.zip"
    capture.write_bytes(b"synthetic fixture")

    def run(self):
        self.gui_queue.put(("capture_ready", str(capture)))
        self._cleanup_session()

    monkeypatch.setattr(data_collection.DataCollectionWindow, "_run_collection", run)
    controller = data_collection.DataCollectionWindow(root, [eye])
    assert controller.window is None  # No connection/window before the user opens the flow.
    controller.show()
    ui = controller._contributions
    assert controller.window is ui.window
    drain(root, lambda: not ui.busy)
    ui.hmd.set("Test HMD")
    ui.continue_flow()
    ui.start_capture()
    drain(root, lambda: not controller.session_running)
    assert ui.step == 2 and ui._capture_path == capture.resolve()
    assert not ui.agree.get() and not ui.busy
    assert not controller.active_queues

    # An engine failure in the next session clears the previous attachment.
    def fail(self):
        raise RuntimeError("synthetic capture failure")

    monkeypatch.setattr(data_collection.DataCollectionWindow, "_run_collection", fail)
    ui.start_capture()
    drain(root, lambda: not controller.session_running)
    assert ui._capture_path is None and ui.step == 1
    controller.close()
    assert ui.window.winfo_exists()  # Reused when Contribute is opened again.
    ui.window.destroy()


def test_hmd_guidance_and_support_details_without_exposing_the_receipt(root, tmp_path):
    ui = window(root, tmp_path)
    assert "Valve Index" in ui.hmd_entry.cget("values")
    ui.hmd.set("x" * 200)
    assert "at most" in ui.hmd_hint.cget("text")
    ui.continue_flow()
    assert ui.step == 0 and "HMD" in ui.status.get()
    ui.hmd.set("Bigscreen Beyond‮  2e")
    assert "Encrypted" in ui.hmd_hint.cget("text")
    sid = "b" * 32
    chunk = "c" * 64
    save(
        ui.client.paths(sid)[0],
        {
            "schema": 3,
            "api": ui.client.service,
            "id": sid,
            "withdrawal_token": "t" * 43,
            "kind": "dataset",
            "hmd": "Bigscreen Beyond 2e",
            "consent": True,
            "prepared": "2026-10-20",
            "terms_version": "test",
            "terms_sha256": chunk,
            "size": 2048,
            "sha256": chunk,
            "chunk_bytes": 1024,
            "chunks": [chunk, chunk],
            "state": "pending",
        },
    )
    ui.refresh_history(sid)
    assert ui.history.item(sid)["values"][0] == "2026-10-20"
    assert ui.history.item(sid)["values"][-1] == sid[:8]
    ui.copy_id()
    assert ui.window.clipboard_get() == sid and "t" * 43 not in ui.window.clipboard_get()
    assert str(ui.backup_button.cget("state")) == "disabled"
    ui._capture_receipt = sid
    ui.update_navigation()
    assert str(ui.backup_button.cget("state")) == "normal"
    ui.close()


def test_full_daily_quota_is_announced_before_recording(root, tmp_path):
    client = ContributionClient(directory=tmp_path / "private")
    client.config = lambda: {
        "enabled": True,
        "quota_full": "daily_quota",
        "terms": {"dataset": {"version": "test", "text": "Current 18+ terms"}},
    }
    ui = ContributionWindow(root, client=client)
    ui.window.withdraw()
    drain(root, lambda: ui.config is not None)
    assert "upload limit reached" in ui.availability.get() and "prohurtz" in ui.availability.get()
    assert "prohurtz on Discord" in ui.status.get() and "Resume" in ui.status.get()
    ui.close()
