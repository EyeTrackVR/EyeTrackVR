"""OpenXR eye gaze layer registration: an implicit layer while "Foveated rendering gaze" is on,
per user, without disturbing other layers. Both platform paths run on any OS here."""

import json
import sys
import time
from queue import Queue
from unittest import mock

import pytest

from OVR import OpenXRLayerRegistration as reg
from osc.osc import OSCManager
from conftest import _FakeRegistry


def _layer(root):
    d = root / "openxr_layer"
    d.mkdir(parents=True)
    (d / reg._library_name()).write_bytes(b"\0")
    (d / reg.MANIFEST).write_text(json.dumps({
        "file_format_version": "1.0.0",
        "api_layer": {"name": reg.LAYER_NAME, "library_path": "./" + reg._library_name(),
                      "api_version": "1.0", "implementation_version": "1",
                      "disable_environment": "DISABLE_" + reg.LAYER_NAME},
    }))
    return d


# ------------------------------------------------------------------ Windows (registry)


def test_windows_install_is_one_enabled_value_and_idempotent(tmp_path):
    layer = _layer(tmp_path / "install")
    r = _FakeRegistry()
    r.set(r"C:\Other\layer.json", 0)
    assert reg.sync(True, layer, registry=r) == reg.INSTALLED
    assert r.data == {r"C:\Other\layer.json": 0, str(layer / reg.MANIFEST): 0}
    assert reg.sync(True, layer, registry=r) == reg.ALREADY_INSTALLED


def test_windows_replaces_disabled_or_other_install_entries(tmp_path):
    old = _layer(tmp_path / "old")
    new = _layer(tmp_path / "new")
    r = _FakeRegistry()
    r.set(str(old / reg.MANIFEST), 0)
    r.set(str(new / reg.MANIFEST), 1)  # present but disabled
    r.set(r"C:\keep\other.json", 1)
    assert reg.sync(True, new, registry=r) == reg.INSTALLED
    assert r.data == {str(new / reg.MANIFEST): 0, r"C:\keep\other.json": 1}


def test_windows_remove(tmp_path):
    layer = _layer(tmp_path / "i")
    r = _FakeRegistry()
    r.set(str(layer / reg.MANIFEST), 0)
    r.set(r"C:\keep\other.json", 0)
    assert reg.sync(False, registry=r) == reg.REMOVED
    assert r.data == {r"C:\keep\other.json": 0}
    assert reg.sync(False, registry=r) == reg.NOT_INSTALLED


@pytest.mark.skipif(sys.platform != "win32", reason="winreg")
def test_real_windows_registry_adapter_round_trip(monkeypatch):
    """The winreg adapter itself, against a throwaway HKCU key (never the real one)."""
    import uuid
    import winreg

    key = rf"SOFTWARE\EyeTrackVR-test-{uuid.uuid4().hex}"
    monkeypatch.setattr(reg, "REGISTRY_KEY", key)
    adapter = reg._WinregRegistry()  # conftest replaced reg.WindowsRegistry with a fake
    try:
        assert adapter.values() == {}
        adapter.set(r"C:\x\XR_APILAYER_EYETRACKVR_eye_gaze.json", 0)
        assert adapter.values() == {r"C:\x\XR_APILAYER_EYETRACKVR_eye_gaze.json": 0}
        adapter.delete(r"C:\x\XR_APILAYER_EYETRACKVR_eye_gaze.json")
        assert adapter.values() == {}
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass


# ------------------------------------------------------------------ Linux (implicit.d)


@pytest.fixture()
def linux(monkeypatch):
    """The Linux path on any OS (library name and implicit.d install both follow sys.platform)."""
    monkeypatch.setattr(reg.sys, "platform", "linux")


def _sync_linux(enabled, layer, implicit):
    return reg.sync(enabled, layer, implicit_dir=implicit)


def test_linux_install_writes_absolute_library_path(tmp_path, linux):
    layer = _layer(tmp_path / "opt")
    implicit = tmp_path / "share" / "openxr" / "1" / "api_layers" / "implicit.d"
    assert _sync_linux(True, layer, implicit) == reg.INSTALLED
    data = json.loads((implicit / reg.MANIFEST).read_text())
    assert data["api_layer"]["library_path"] == str(layer / reg._library_name())
    assert data["api_layer"]["name"] == reg.LAYER_NAME
    assert data["api_layer"]["disable_environment"] == "DISABLE_" + reg.LAYER_NAME
    assert _sync_linux(True, layer, implicit) == reg.ALREADY_INSTALLED
    # Moved install: the manifest follows it.
    moved = _layer(tmp_path / "moved")
    assert _sync_linux(True, moved, implicit) == reg.INSTALLED
    assert json.loads((implicit / reg.MANIFEST).read_text())["api_layer"]["library_path"] == str(moved / reg._library_name())


def test_linux_remove_leaves_other_layers(tmp_path, linux):
    layer = _layer(tmp_path / "opt")
    implicit = tmp_path / "implicit.d"
    implicit.mkdir()
    (implicit / "other.json").write_text("{}")
    _sync_linux(True, layer, implicit)
    assert _sync_linux(False, None, implicit) == reg.REMOVED
    assert sorted(p.name for p in implicit.iterdir()) == ["other.json"]
    assert _sync_linux(False, None, implicit) == reg.NOT_INSTALLED


def test_implicit_dir_follows_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert reg._xdg_implicit_layer_dir() == tmp_path / "data" / "openxr" / "1" / "api_layers" / "implicit.d"
    monkeypatch.delenv("XDG_DATA_HOME")
    assert reg._xdg_implicit_layer_dir() == reg.Path.home() / ".local" / "share" / "openxr" / "1" / "api_layers" / "implicit.d"


# ------------------------------------------------------------------ common


def test_no_bundled_layer(monkeypatch, tmp_path):
    monkeypatch.setattr(reg, "bundled_layer_dir", lambda: None)
    r = _FakeRegistry()
    assert reg.sync(True, registry=r) == reg.NO_LAYER
    assert r.data == {}


def test_bundled_layer_dir_needs_manifest_and_library(tmp_path, monkeypatch):
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "eyetrackapp.exe"))
    assert reg.bundled_layer_dir() is None
    d = _layer(exe_dir)
    assert reg.bundled_layer_dir() == d.resolve()
    (d / reg._library_name()).unlink()
    assert reg.bundled_layer_dir() is None


def test_sync_quietly_never_raises():
    with mock.patch.object(reg, "sync", side_effect=PermissionError("denied")):
        assert reg.sync_quietly(True) is None


def test_osc_manager_syncs_driver_and_layer_with_the_toggle(main_config_v2_params):
    calls = []

    def wait_for(n):
        deadline = time.monotonic() + 5
        while len(calls) < n and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(calls) == n, calls

    s = main_config_v2_params.settings
    with mock.patch("OVR.SteamVRDriverRegistration.sync_quietly", side_effect=lambda e: calls.append(("driver", e))), \
         mock.patch("OVR.OpenXRLayerRegistration.sync_quietly", side_effect=lambda e: calls.append(("layer", e))), \
         mock.patch("osc.osc.udp_client.SimpleUDPClient"):
        manager = OSCManager(config=main_config_v2_params, osc_message_in_queue=Queue())
        manager.start()
        try:
            wait_for(2)
            s.gui_foveation_gaze = True
            manager.update({"gui_foveation_gaze": True})
            wait_for(4)
        finally:
            manager.shutdown()
    assert calls == [("driver", False), ("layer", False), ("driver", True), ("layer", True)]
