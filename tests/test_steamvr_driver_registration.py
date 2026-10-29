"""SteamVR driver registration: openvrpaths.vrpath's external_drivers follows the
"Foveated rendering gaze" toggle, without disturbing other drivers or keys."""

import json
import sys
import time
from queue import Queue
from unittest import mock


from OVR import SteamVRDriverRegistration as reg
from osc.osc import OSCManager


def _driver(root, name="eyetrackvr", sub=("steamvr_driver", "eyetrackvr")):
    d = root.joinpath(*sub)
    (d / reg._binary_relpath()).parent.mkdir(parents=True)
    (d / reg._binary_relpath()).write_bytes(b"\0")
    (d / reg.MANIFEST).write_text(json.dumps({"name": name, "alwaysActivate": True}))
    return d


def _paths(tmp_path, drivers, **extra):
    p = tmp_path / "openvrpaths.vrpath"
    p.write_text(json.dumps({"jsonid": "vrpathreg", "version": 1, "external_drivers": drivers, **extra}, indent="\t"))
    return p


def _drivers(p):
    return json.loads(p.read_text())["external_drivers"]


def test_register_adds_once_and_keeps_others(tmp_path):
    ours = _driver(tmp_path / "install")
    paths = _paths(tmp_path, ["C:\\other\\driver"], runtime=["C:\\SteamVR"], config=["C:\\cfg"])
    assert reg.sync(True, paths, ours) == reg.REGISTERED
    assert _drivers(paths) == ["C:\\other\\driver", str(ours)]
    data = json.loads(paths.read_text())
    assert data["runtime"] == ["C:\\SteamVR"] and data["config"] == ["C:\\cfg"] and data["jsonid"] == "vrpathreg"

    before = paths.stat().st_mtime_ns
    assert reg.sync(True, paths, ours) == reg.ALREADY_REGISTERED
    assert paths.stat().st_mtime_ns == before  # nothing rewritten


def test_register_replaces_other_and_removed_installs(tmp_path):
    old_install = _driver(tmp_path / "old")
    gone = tmp_path / "removed" / "steamvr_driver" / "eyetrackvr"  # uninstalled, folder gone
    unrelated_gone = tmp_path / "x" / "somedriver"  # someone else's dead entry: not ours to remove
    ours = _driver(tmp_path / "new")
    paths = _paths(tmp_path, [str(old_install), "C:\\keep", str(gone), str(unrelated_gone)])
    assert reg.sync(True, paths, ours) == reg.REGISTERED
    assert _drivers(paths) == ["C:\\keep", str(unrelated_gone), str(ours)]


def test_other_vendor_driver_named_folder_is_not_ours(tmp_path):
    lookalike = _driver(tmp_path / "vendor", name="somethingelse")
    paths = _paths(tmp_path, [str(lookalike)])
    assert reg.sync(False, paths) == reg.NOT_REGISTERED
    assert _drivers(paths) == [str(lookalike)]


def test_unregister_removes_every_copy(tmp_path):
    a = _driver(tmp_path / "a")
    b = _driver(tmp_path / "b")
    paths = _paths(tmp_path, [str(a), "C:\\keep", str(b)])
    assert reg.sync(False, paths) == reg.UNREGISTERED
    assert _drivers(paths) == ["C:\\keep"]
    assert reg.sync(False, paths) == reg.NOT_REGISTERED


def test_missing_null_and_bad_files(tmp_path):
    ours = _driver(tmp_path / "i")
    assert reg.sync(True, None, ours) == reg.NO_STEAMVR  # the autouse fixture hides the real file
    paths = _paths(tmp_path, None)
    assert reg.sync(True, paths, ours) == reg.REGISTERED
    assert _drivers(paths) == [str(ours)]

    broken = tmp_path / "broken.vrpath"
    broken.write_text("{ not json")
    assert reg.sync(True, broken, ours) == reg.NOT_REGISTERED
    assert broken.read_text() == "{ not json"  # never clobber a file we can't parse


def test_no_bundled_driver(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "bundled_driver_dir", lambda: None)
    paths = _paths(tmp_path, [])
    assert reg.sync(True, paths) == reg.NO_DRIVER
    assert _drivers(paths) == []


def test_bundled_driver_dir_needs_manifest_and_binary(tmp_path, monkeypatch):
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "eyetrackapp.exe"))
    assert reg.bundled_driver_dir() is None
    d = _driver(exe_dir)
    assert reg.bundled_driver_dir() == d.resolve()
    (d / reg._binary_relpath()).unlink()
    assert reg.bundled_driver_dir() is None


def test_sync_quietly_never_raises(tmp_path):
    with mock.patch.object(reg, "sync", side_effect=PermissionError("locked")):
        assert reg.sync_quietly(True) is None


def test_osc_manager_follows_the_toggle(main_config_v2_params):
    calls = []

    def wait_for(n):
        deadline = time.monotonic() + 5
        while len(calls) < n and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(calls) == n, calls

    s = main_config_v2_params.settings
    with (
        mock.patch("OVR.SteamVRDriverRegistration.sync_quietly", side_effect=calls.append),
        mock.patch("osc.osc.udp_client.SimpleUDPClient"),
    ):
        manager = OSCManager(config=main_config_v2_params, osc_message_in_queue=Queue())
        manager.start()
        try:
            wait_for(1)  # startup: toggle off -> make sure no stale registration is left
            s.gui_foveation_gaze = True
            manager.update({"gui_foveation_gaze": True})
            wait_for(2)
            s.gui_foveation_gaze = False
            manager.update({"gui_foveation_gaze": False})
            wait_for(3)
            manager.update({"gui_osc_port": 9999})  # unrelated setting: no sync
            time.sleep(0.1)
        finally:
            manager.shutdown()
    assert calls == [False, True, False]
