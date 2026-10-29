"""Adversarial receipt-storage and verification IPC checks; fake secrets only."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EyeTrackApp"))
from contributions.client import save
from contributions.verification import verified_reply


def test_verification_ignores_malformed_or_unauthenticated_local_replies():
    for result in (None, [], "text", 42, {}, {"nonce": 7}, {"nonce": "é"},
                   {"nonce": "wrong", "token": "fixture-token"},
                   {"nonce": "expected", "token": []},
                   {"nonce": "expected", "token": "x" * 2049}):
        assert verified_reply(result, "expected") is None
    assert verified_reply({"nonce": "expected", "token": "fixture-token"}, "expected") == "fixture-token"


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL regression")
def test_receipt_export_does_not_inherit_shared_folder_read_access(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    subprocess.run(["icacls", str(shared), "/grant", "*S-1-1-0:(OI)(CI)R"], check=True, capture_output=True)
    receipt = shared / "backup.json"
    save(receipt, {"withdrawal_token": "fixture-only-not-a-real-secret"})
    acl = tmp_path / "permissions.txt"
    subprocess.run(["icacls", str(receipt), "/save", str(acl)], check=True, capture_output=True)
    raw = acl.read_bytes()
    sddl = raw.decode("utf-16-le" if b"\0" in raw else "utf-8-sig")
    trustees = re.findall(r"\(A;[^)]*;;;([^)]*)\)", sddl)
    # The other entry is the owner. icacls writes the built-in Administrator,
    # which the GitHub Windows runner uses, as "LA" instead of its SID.
    assert len(trustees) == 2 and "SY" in trustees, sddl
    assert ";;;WD)" not in sddl and ";ID;" not in sddl
    assert json.loads(receipt.read_text())["withdrawal_token"] == "fixture-only-not-a-real-secret"


def test_receipt_permissions_failure_does_not_replace_or_leak_secret(tmp_path, monkeypatch):
    receipt = tmp_path / "backup.json"
    receipt.write_text("existing")
    def fail(*args, **kwargs):
        raise OSError("Synthetic permission failure")
    monkeypatch.setattr("contributions.client.restrict_access", fail)
    with pytest.raises(OSError):
        save(receipt, {"withdrawal_token": "fixture-secret-must-not-be-written"})
    assert receipt.read_text() == "existing"
    assert list(tmp_path.iterdir()) == [receipt]
