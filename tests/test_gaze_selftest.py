"""The "Check VR eye gaze" self-test (ovr/gaze_selftest.py): each check's verdict with faked
probes, dependency skipping, vrserver.txt parsing and the "what to do next" text."""

import ctypes
import json
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from osc import gaze_shared_memory as gsm
from osc.gaze_shared_memory import FLAG_GAZE_VALID, FLAG_OPENNESS_VALID, GazeEye
from ovr import gaze_selftest as st
from ovr import openxr_layer_registration as xr
from ovr import steamvr_driver_registration as reg
from ovr.gaze_selftest import FAIL, PASS, SKIP, WARN

DRIVER_SRC = Path(__file__).resolve().parents[1] / "native" / "steamvr_driver" / "src"
NOW = 50_000_000_000

# Format strings exactly as native/steamvr_driver/src/*.cpp pass them to Log() (checked below).
FMT_START = "EyeTrackVR gaze driver starting"
FMT_WATCHING = "Watching for the HMD"
FMT_NO_SHIM = "HMD shim unavailable; relying on direct attach"
FMT_WRAP = "Wrapping HMD '%s' to attach eye tracking"
FMT_ATTACH = "Attach via %s to device %u: CreateEyeTrackingComponent -> %s (%d)"
FMT_UPDATE = "UpdateEyeTrackingComponent -> %s (%d)"
FMT_PROP = "Prop_SupportsXrEyeGazeInteraction_Bool = %d -> %d"
FMT_PATCH = "Could not patch IVRServerDriverHost::TrackedDeviceAdded"


def test_format_strings_match_the_driver_source():
    source = "".join(p.read_text(encoding="utf-8") for p in DRIVER_SRC.glob("*.cpp"))
    for fmt in (FMT_START, FMT_WRAP, FMT_ATTACH, FMT_UPDATE, FMT_PROP, FMT_PATCH):
        assert f'"{fmt}"' in source, fmt
    assert f'"{FMT_WATCHING}" : "{FMT_NO_SHIM}"' in source


# ------------------------------------------------------------------ vrserver.txt excerpts

_clock = iter(range(10**6))


def _ts() -> str:
    return f"Sat Nov 14 2026 10:10:{next(_clock) % 60:02d}.946"


def steamvr(msg: str, level: str = "Info") -> str:
    """A line as SteamVR writes vrserver.txt (format copied from a real 2.18 log)."""
    return f"{_ts()} [{level}] - {msg}"


def driver(fmt: str, *args) -> str:
    """One of our driver's Log() calls, which SteamVR prefixes with the driver name."""
    return steamvr("eyetrackvr: " + (fmt.replace("%u", "%d") % args if args else fmt))


def session(*lines: str, version: str = "2.18.4") -> list[str]:
    return [
        steamvr("================================================================================================"),
        steamvr(
            f"vrserver {version} startup with PID=15812, config=C:\\Program Files (x86)\\Steam\\config, "
            "runtime=C:\\Program Files (x86)\\Steam\\steamapps\\common\\SteamVR, arch=win64"
        ),
        steamvr("[vrserver] watchdogs enabled"),
        *lines,
    ]


LOADED = steamvr(
    "Loaded server driver eyetrackvr (IServerTrackedDeviceProvider_004) from "
    "C:\\EyeTrackVR\\steamvr_driver\\eyetrackvr\\bin\\win64\\driver_eyetrackvr.dll"
)
GOOD = session(
    steamvr(
        "Loaded server driver lighthouse (IServerTrackedDeviceProvider_004) from C:\\SteamVR\\driver_lighthouse.dll"
    ),
    LOADED,
    driver(FMT_START),
    driver(FMT_WATCHING),
    steamvr("lighthouse: LHR-1234ABCD H: Activating"),
    driver(FMT_WRAP, "LHR-1234ABCD"),
    driver(FMT_ATTACH, "shim", 0, "None", 0),
    driver(FMT_PROP, 0, 0),
    driver(FMT_PROP, 1, 0),
)
DENIED = session(
    LOADED,
    driver(FMT_START),
    driver(FMT_WATCHING),
    driver(FMT_WRAP, "BSB-0042"),
    driver(FMT_ATTACH, "shim", 0, "PermissionDenied", 7),
)
DISABLED = session(
    steamvr("Not loading driver eyetrackvr because it is disabled in settings", "Warning"),
    steamvr("Not loading driver eyetrackvr because it is disabled in settings", "Warning"),
)


def _text(*lines) -> str:
    return "\n".join(lines) + "\n"


def test_parse_good_session():
    f = st.parse_vrserver_log(_text(*GOOD))
    assert f.session_found and f.loaded and f.driver_started and f.shim is True
    assert f.wrapped_serial == "LHR-1234ABCD"
    assert (f.attach_route, f.attach_device, f.attach_error, f.attach_code) == ("shim", 0, "None", 0)
    assert (f.prop_value, f.prop_code) == (1, 0)
    assert f.update_error is None
    assert f.driver_lines[0] == FMT_START


def test_parse_direct_attach_and_update_error():
    f = st.parse_vrserver_log(
        _text(
            *session(
                LOADED,
                driver(FMT_START),
                driver(FMT_PATCH),
                driver(FMT_NO_SHIM),
                driver(FMT_ATTACH, "direct", 0, "None", 0),
                driver(FMT_UPDATE, "InvalidHandle", 3),
                driver(FMT_PROP, 1, 0),
            )
        )
    )
    assert f.shim is False and f.shim_patch_failed
    assert f.attach_route == "direct" and f.update_error == "InvalidHandle (3)"


def test_parse_reads_only_the_last_session():
    f = st.parse_vrserver_log(_text(*GOOD, *DENIED))
    assert f.attach_error == "PermissionDenied" and f.prop_value is None
    f = st.parse_vrserver_log(_text(*DENIED, *session(steamvr("lighthouse: hello"))))
    assert not f.loaded and f.attach_error is None


def test_parse_disabled_in_steamvr_settings():
    f = st.parse_vrserver_log(_text(*DISABLED))
    assert f.disabled and not f.loaded and len(f.steamvr_lines) == 2


def test_read_tail_drops_the_partial_first_line(tmp_path):
    path = tmp_path / "vrserver.txt"
    body = _text(*GOOD).encode("utf-8")
    path.write_bytes(b"first line that gets cut\n" + body)
    assert st.read_tail(path, max_bytes=len(body) + 5) == body.decode("utf-8")


# ------------------------------------------------------------------ fakes


def _sample(age_s=0.01, flags=FLAG_GAZE_VALID | FLAG_OPENNESS_VALID, count=42, clock=None):
    eye = GazeEye((0.0, 0.0, -1.0), 1.0, 1.0, flags)
    return {
        "clock": gsm.clock_id() if clock is None else clock,
        "sample_count": count,
        "pid": 1234,
        "publish_time_ns": NOW - int(age_s * 1e9),
        "sample_time_ns": NOW,
        "eyes": [eye, eye, eye],
        "fov": (45.0, 30.0, 30.0),
    }


def _driver_state(tmp_path, **over):
    expected = tmp_path / "steamvr_driver" / "eyetrackvr"
    values = dict(
        expected_dir=expected,
        binary_relpath="bin/win64/driver_eyetrackvr.dll",
        has_manifest=True,
        has_binary=True,
        paths_file=tmp_path / "openvrpaths.vrpath",
        registered=[str(expected)],
        steamvr_setting=None,
    )
    values.update(over)
    return st.DriverState(**values)


def _good_probe(**over):
    result = {
        "ok": True,
        "hmd_connected": True,
        "tracking_system": "lighthouse",
        "model": "Index",
        "manufacturer": "Valve",
        "runtime_version": "2.18.4",
        "interface": "IVRSystem_023",
        "prop": {"value": True, "code": 0, "error": "TrackedProp_Success"},
        "foveation": {"available": True, "where": "test", "samples": [[0.1, 0.2], [0.15, 0.2]], "errors": []},
    }
    result.update(over)
    return result


class Calls:
    def __init__(self):
        self.openvr = 0


@pytest.fixture
def probes(tmp_path):
    """Every link working; tests break one at a time."""
    calls = Calls()

    def openvr_probe():
        calls.openvr += 1
        return _good_probe()

    p = st.Probes(
        read_gaze=lambda: st.GazeBlock(True, _sample(), "Local\\EyeTrackVR.Gaze.v1"),
        now_ns=lambda: NOW,
        mutex_exists=lambda: True,
        driver_state=lambda: _driver_state(tmp_path),
        layer_state=lambda: st.LayerState(tmp_path / "layer", True, True, ["layer.json"]),
        steamvr_running=lambda: True,
        vrserver_log=lambda: st.LogTail(tmp_path / "vrserver.txt", _text(*GOOD)),
        openvr_probe=openvr_probe,
        frozen=True,
    )
    p.calls = calls
    return p


ON = SimpleNamespace(settings=SimpleNamespace(gui_foveation_gaze=True))
OFF = SimpleNamespace(settings=SimpleNamespace(gui_foveation_gaze=False))


def _by_id(checks):
    return {c.id: c for c in checks}


# ------------------------------------------------------------------ the whole chain


def test_all_links_working(probes):
    checks = st.run_checks(ON, probes)
    assert [c.id for c in checks] == [
        "setting",
        "publisher",
        "mutex",
        "driver",
        "openxr_layer",
        "steamvr",
        "vrserver_log",
        "openvr_hmd",
        "openvr_foveation",
    ]
    assert all(c.status == PASS for c in checks), [(c.id, c.status, c.message) for c in checks]
    assert probes.calls.openvr == 1  # one child process serves both OpenVR checks
    assert st.next_steps(checks).startswith("Every link works")


def test_setting_off_skips_what_depends_on_it(probes):
    checks = _by_id(st.run_checks(OFF, probes))
    assert checks["setting"].status == FAIL
    for cid in ("publisher", "mutex", "driver", "openxr_layer"):
        assert checks[cid].status == SKIP and checks[cid].message == "skipped: Setting failed"
    assert checks["vrserver_log"].status == SKIP and "SteamVR driver was skipped" in checks["vrserver_log"].message
    # SteamVR is checked regardless.
    assert checks["steamvr"].status == PASS and checks["openvr_hmd"].status == PASS
    assert st.next_steps(list(checks.values())).startswith('First failure: Setting. Turn on "Foveated rendering support"')


def test_setting_reads_plain_settings_object_too():
    assert st.check_setting(SimpleNamespace(gui_foveation_gaze=True)).status == PASS
    assert st.check_setting(SimpleNamespace()).status == FAIL


def test_steamvr_not_running_skips_openvr_and_never_starts_the_probe(probes):
    probes.steamvr_running = lambda: False
    checks = _by_id(st.run_checks(ON, probes))
    assert checks["steamvr"].status == FAIL
    assert checks["openvr_hmd"].status == SKIP and checks["openvr_foveation"].status == SKIP
    assert "SteamVR running failed" in checks["openvr_hmd"].message
    assert probes.calls.openvr == 0
    # The log check still runs, on the previous session.
    assert checks["vrserver_log"].status == PASS and "SteamVR is not running now" in checks["vrserver_log"].message
    steps = st.next_steps(list(checks.values()))
    assert steps.startswith("First failure: SteamVR running. Start SteamVR with the headset connected")


def test_driver_failure_skips_the_log_check(probes, tmp_path):
    probes.driver_state = lambda: _driver_state(tmp_path, registered=[])
    checks = _by_id(st.run_checks(ON, probes))
    assert checks["driver"].status == FAIL and checks["vrserver_log"].status == SKIP
    assert "SteamVR driver failed" in checks["vrserver_log"].message


def test_a_crashing_probe_is_reported_not_raised(probes):
    def boom():
        raise RuntimeError("nope")

    probes.read_gaze = boom
    checks = _by_id(st.run_checks(ON, probes))
    assert checks["publisher"].status == FAIL and "check crashed: RuntimeError: nope" in checks["publisher"].message
    assert checks["driver"].status == PASS


# ------------------------------------------------------------------ publisher


@pytest.mark.parametrize(
    "block, status, words",
    [
        (st.GazeBlock(False, where="Local\\EyeTrackVR.Gaze.v1"), FAIL, "no gaze shared memory"),
        (st.GazeBlock(True, None, "x"), FAIL, "holds no valid sample"),
        (st.GazeBlock(True, _sample(count=0), "x"), FAIL, "nothing was published yet"),
        (st.GazeBlock(True, _sample(age_s=4.2), "x"), FAIL, "last sample 4.2 s old"),
        (st.GazeBlock(True, _sample(flags=FLAG_OPENNESS_VALID), "x"), WARN, "flagged invalid"),
        (st.GazeBlock(True, _sample(clock=99), "x"), WARN, "can't tell its age"),
        (st.GazeBlock(True, _sample(age_s=0.02), "x"), PASS, "fresh (20 ms old), combined gaze valid"),
    ],
)
def test_publisher(probes, block, status, words):
    probes.read_gaze = lambda: block
    check = st.check_publisher(probes)
    assert check.status == status and words in check.message


def test_publisher_detail_shows_flags_and_pid(probes):
    probes.read_gaze = lambda: st.GazeBlock(True, _sample(flags=FLAG_OPENNESS_VALID), "Local\\EyeTrackVR.Gaze.v1")
    detail = st.check_publisher(probes).detail
    assert "pid 1234" in detail and "combined: flags=openness" in detail


def test_publisher_missing_next_step(probes):
    probes.read_gaze = lambda: st.GazeBlock(False, where="Local\\EyeTrackVR.Gaze.v1")
    steps = st.next_steps(st.run_checks(ON, probes))
    assert steps.startswith("First failure: Publisher. Start EyeTrackVR with both cameras streaming")


def test_mutex(probes):
    for value, status in ((True, PASS), (False, WARN), (None, SKIP)):
        probes.mutex_exists = lambda value=value: value
        assert st.check_mutex(probes).status == status


# ------------------------------------------------------------------ driver and layer


@pytest.mark.parametrize(
    "over, words",
    [
        (dict(has_binary=False), "missing bin/win64/driver_eyetrackvr.dll"),
        (dict(has_manifest=False, has_binary=False), "missing driver.vrdrivermanifest, bin/win64"),
        (dict(paths_file=None), "SteamVR has never run for this user"),
        (dict(registered=None), "cannot read"),
        (dict(registered=[]), "not listed"),
        (dict(registered=["D:\\Old\\steamvr_driver\\eyetrackvr"]), "another install's copy is registered"),
        (dict(steamvr_setting="disabled"), "turned off in SteamVR's settings"),
        (dict(steamvr_setting="blocked_by_safe_mode"), "blocked by SteamVR safe mode"),
    ],
)
def test_driver_failures(probes, tmp_path, over, words):
    probes.driver_state = lambda: _driver_state(tmp_path, **over)
    check = st.check_driver(probes)
    assert check.status == FAIL and words in check.message, check.message


def test_driver_pass_and_hints(probes, tmp_path):
    assert st.check_driver(probes).status == PASS
    probes.driver_state = lambda: _driver_state(tmp_path, registered=[])
    steps = st.next_steps(st.run_checks(ON, probes))
    assert steps.startswith("First failure: SteamVR driver.") and "turn the setting off and on again" in steps
    probes.frozen = False
    probes.driver_state = lambda: _driver_state(tmp_path, has_binary=False)
    assert "cmake -S native/steamvr_driver" in st.check_driver(probes).hint
    probes.driver_state = lambda: _driver_state(tmp_path, steamvr_setting="disabled")
    assert "Manage Add-ons" in st.check_driver(probes).hint


def test_layer_is_a_warning_only(probes, tmp_path):
    probes.layer_state = lambda: st.LayerState(tmp_path, False, False)
    assert st.check_layer(probes).status == WARN
    probes.layer_state = lambda: st.LayerState(tmp_path, True, False, ["D:\\old\\layer.json"])
    check = st.check_layer(probes)
    assert check.status == WARN and "registered elsewhere" in check.message
    checks = st.run_checks(ON, probes)
    assert not any(c.status == FAIL for c in checks)
    assert st.next_steps(checks).startswith("Nothing failed. First warning: OpenXR layer.")


# ------------------------------------------------------------------ vrserver log check


def _log_check(probes, lines, running=True):
    probes.vrserver_log = lambda: st.LogTail(Path("vrserver.txt"), _text(*lines))
    return st.check_vrserver_log(probes, running)


def test_log_good(probes):
    check = _log_check(probes, GOOD)
    assert check.status == PASS
    assert "Attach via shim to device 0 -> None (0)" in check.message
    assert "Prop_SupportsXrEyeGazeInteraction_Bool = 1" in check.message
    assert "eyetrackvr: Attach via shim" in check.detail


def test_log_permission_denied_is_explained(probes):
    check = _log_check(probes, DENIED)
    assert check.status == FAIL
    assert "PermissionDenied" in check.message
    assert "SteamVR refused a cross-driver component" in check.message
    probes.vrserver_log = lambda: st.LogTail(Path("vrserver.txt"), _text(*DENIED))
    steps = st.next_steps(st.run_checks(ON, probes))
    assert steps.startswith("First failure: SteamVR log. SteamVR refused to let EyeTrackVR's driver add eye tracking")


def test_log_other_attach_error(probes):
    check = _log_check(probes, session(LOADED, driver(FMT_START), driver(FMT_ATTACH, "direct", 0, "InvalidParam", 4)))
    assert check.status == FAIL and "rejected the eye tracking component" in check.message


def test_log_not_loaded(probes):
    check = _log_check(probes, session(steamvr("lighthouse: hello")))
    assert check.status == FAIL and "did not load the driver" in check.message
    assert check.hint.startswith("Restart SteamVR")
    assert _log_check(probes, session(), running=False).hint.startswith("Start SteamVR")


def test_log_disabled(probes):
    check = _log_check(probes, DISABLED)
    assert check.status == FAIL and "disabled in its settings" in check.message and "Manage Add-ons" in check.hint


def test_log_loaded_but_no_headset(probes):
    check = _log_check(probes, session(LOADED, driver(FMT_START), driver(FMT_WATCHING)))
    assert check.status == FAIL and "never attached" in check.message
    check = _log_check(probes, session(LOADED, driver(FMT_START), driver(FMT_PATCH), driver(FMT_NO_SHIM)))
    assert "HMD hook could not be installed" in check.message


def test_log_property(probes):
    base = [LOADED, driver(FMT_START), driver(FMT_ATTACH, "shim", 0, "None", 0)]
    assert _log_check(probes, session(*base)).status == WARN  # property not set yet
    check = _log_check(probes, session(*base, driver(FMT_PROP, 0, 0)))
    assert check.status == WARN and "saw no gaze published" in check.message
    check = _log_check(probes, session(*base, driver(FMT_PROP, 1, 3)))
    assert check.status == FAIL and "error 3" in check.message
    check = _log_check(probes, session(*base, driver(FMT_PROP, 1, 0), driver(FMT_UPDATE, "InvalidHandle", 3)))
    assert check.status == WARN and "UpdateEyeTrackingComponent -> InvalidHandle (3)" in check.message


def test_log_not_found_is_a_warning(probes):
    probes.vrserver_log = lambda: st.LogTail(None, "", ["C:\\Steam\\logs\\vrserver.txt"])
    check = st.check_vrserver_log(probes, True)
    assert check.status == WARN and "C:\\Steam\\logs\\vrserver.txt" in check.detail


# ------------------------------------------------------------------ OpenVR checks


def test_openvr_session_failure(probes):
    probes.openvr_probe = lambda: {"ok": False, "error": "VRInitError_Init_NoServerForBackgroundApp"}
    checks = _by_id(st.run_checks(ON, probes))
    assert checks["openvr_hmd"].status == FAIL and "NoServerForBackgroundApp" in checks["openvr_hmd"].message
    assert checks["openvr_foveation"].status == SKIP


def test_openvr_hmd(probes):
    assert "lighthouse / Index" in st.check_openvr_hmd(_good_probe()).message
    check = st.check_openvr_hmd(_good_probe(hmd_connected=False))
    assert check.status == FAIL and "no headset" in check.message
    check = st.check_openvr_hmd(_good_probe(prop={"value": False, "code": 0, "error": "TrackedProp_Success"}))
    assert check.status == FAIL and "= false" in check.message and "fix the first failing check" in check.hint
    check = st.check_openvr_hmd(_good_probe(prop={"value": False, "code": 4, "error": "TrackedProp_UnknownProperty"}))
    assert check.status == FAIL and "TrackedProp_UnknownProperty" in check.message


def test_openvr_foveation():
    unavailable = {"available": False, "where": "not available in this OpenVR binding (pyopenvr 2.12.1401, ...)"}
    check = st.check_openvr_foveation(_good_probe(foveation=unavailable))
    assert check.status == WARN and "not available in this OpenVR binding" in check.message
    assert st.check_openvr_foveation(_good_probe()).status == PASS
    same = {"available": True, "where": "t", "samples": [[0.1, 0.2]] * 10, "errors": []}
    assert st.check_openvr_foveation(_good_probe(foveation=same)).status == WARN
    broken = {"available": True, "where": "t", "samples": [], "errors": ["OSError: access violation"]}
    check = st.check_openvr_foveation(_good_probe(foveation=broken))
    assert check.status == FAIL and "access violation" in check.detail


def test_unavailable_foveation_alone_still_exits_clean(probes):
    probes.openvr_probe = lambda: _good_probe(foveation={"available": False, "where": "not available"})
    checks = st.run_checks(ON, probes)
    assert not any(c.status == FAIL for c in checks)
    assert st.next_steps(checks).startswith("Nothing failed. First warning: Foveation centre.")


class _FnTable(ctypes.Structure):
    _fields_ = [("getEyeTrackedFoveationCenter", ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_float)))]


def test_foveation_query_paths():
    fake_openvr = SimpleNamespace(IVRSystem_Version="IVRSystem_099")
    wrapper = SimpleNamespace(getEyeTrackedFoveationCenter=lambda: (0.25, -0.5), function_table=None)
    call, where = st._foveation_query(fake_openvr, wrapper)
    assert where == "pyopenvr IVRSystem wrapper" and call() == [0.25, -0.5]

    def impl(out):
        out[0] = 0.75
        return True

    table = _FnTable()
    table.getEyeTrackedFoveationCenter = _FnTable._fields_[0][1](impl)
    call, where = st._foveation_query(fake_openvr, SimpleNamespace(function_table=table))
    assert where.startswith("IVRSystem function table") and call() == {"result": True, "out": [0.75]}

    call, where = st._foveation_query(fake_openvr, SimpleNamespace(function_table=SimpleNamespace()))
    assert call is None and "not available in this OpenVR binding" in where and "IVRSystem_099" in where


def test_foveation_query_against_the_installed_pyopenvr():
    import openvr

    system = SimpleNamespace(function_table=openvr.IVRSystem_FnTable())
    if hasattr(openvr.IVRSystem, "getEyeTrackedFoveationCenter"):
        system.getEyeTrackedFoveationCenter = lambda: None
    call, where = st._foveation_query(openvr, system)
    has_entry = "getEyeTrackedFoveationCenter" in [n for n, *_ in openvr.IVRSystem_FnTable._fields_]
    if call is None and not has_entry:
        assert "not available in this OpenVR binding" in where and openvr.IVRSystem_Version in where


# ------------------------------------------------------------------ report


def test_report_has_one_line_per_check_then_next_steps(probes):
    probes.steamvr_running = lambda: False
    checks = st.run_checks(ON, probes)
    text = st.format_report(checks)
    lines = text.splitlines()
    rows = [line for line in lines if re.match(r"^(PASS|FAIL|WARN|SKIP)  ", line)]
    assert len(rows) == len(checks)
    assert rows[5].startswith("FAIL  SteamVR running")
    assert lines[-1].startswith("What to do next: First failure: SteamVR running.")


def test_main_writes_report_and_exit_code(monkeypatch, tmp_path, probes, capsys):
    import config
    from utils import logging_utils

    monkeypatch.setattr(config.EyeTrackConfig, "load", staticmethod(lambda: ON))
    monkeypatch.setattr(logging_utils, "log_directory", lambda: tmp_path)
    monkeypatch.setattr(st, "Probes", lambda: probes)
    assert st.main() == 0
    saved = (tmp_path / st.REPORT_NAME).read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert saved in out and f"Saved to {tmp_path / st.REPORT_NAME}" in out
    probes.steamvr_running = lambda: False
    assert st.main() == 1


# ------------------------------------------------------------------ real probes, isolated


@pytest.fixture
def private_shm(monkeypatch):
    tag = uuid.uuid4().hex
    monkeypatch.setattr(gsm, "WIN32_NAME", f"Local\\EyeTrackVR.Gaze.test.{tag}")
    monkeypatch.setattr(gsm, "POSIX_PATH", f"/dev/shm/eyetrackvr_gaze_test_{tag}")
    monkeypatch.setattr(st, "MUTEX_NAME", f"Local\\eyetrackvr-osc-gaze-test-{tag}")


@pytest.mark.skipif(gsm.clock_id() is None, reason="no gaze shared memory on this OS")
def test_read_gaze_block_reads_without_creating(private_shm):
    assert st.read_gaze_block().exists is False
    assert st.read_gaze_block().exists is False  # still not there: the probe never creates it
    writer = gsm.GazeSharedMemory()
    assert writer.open()
    try:
        valid = GazeEye((0.0, 0.0, -1.0), 1.0, 1.0, FLAG_GAZE_VALID | FLAG_OPENNESS_VALID)
        writer.publish(valid, valid)
        block = st.read_gaze_block()
        assert block.exists and block.sample["sample_count"] == 1
        assert block.sample["eyes"][gsm.EYE_COMBINED].flags & FLAG_GAZE_VALID
    finally:
        writer.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named mutex")
def test_mutex_probe_opens_only(private_shm):
    from osc.foveation_gaze_sender import _NamedMutex

    assert st.foveation_mutex_exists() is False
    mutex = _NamedMutex(st.MUTEX_NAME)
    assert mutex.acquire()
    try:
        assert st.foveation_mutex_exists() is True
    finally:
        mutex.release()
    assert st.foveation_mutex_exists() is False


def _openvrpaths(tmp_path, drivers, **extra):
    p = tmp_path / "openvrpaths.vrpath"
    p.write_text(json.dumps({"jsonid": "vrpathreg", "version": 1, "external_drivers": drivers, **extra}))
    return p


def test_driver_state_from_real_files(monkeypatch, tmp_path):
    ours = tmp_path / "install" / "steamvr_driver" / "eyetrackvr"
    (ours / reg._binary_relpath()).parent.mkdir(parents=True)
    (ours / reg._binary_relpath()).write_bytes(b"\0")
    (ours / reg.MANIFEST).write_text(json.dumps({"name": "eyetrackvr"}))
    config_dir = tmp_path / "Steam" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "steamvr.vrsettings").write_text(json.dumps({"driver_eyetrackvr": {"enable": False}}))
    paths = _openvrpaths(tmp_path, ["C:\\other", str(ours)], config=[str(config_dir)])
    monkeypatch.setattr(reg, "expected_driver_dir", lambda: ours)
    monkeypatch.setattr(reg, "openvrpaths_file", lambda: paths)

    s = st.driver_state()
    assert s.has_manifest and s.has_binary and s.registered == [str(ours)] and s.steamvr_setting == "disabled"
    (config_dir / "steamvr.vrsettings").write_text(json.dumps({"driver_eyetrackvr": {"blocked_by_safe_mode": True}}))
    assert st.driver_state().steamvr_setting == "blocked_by_safe_mode"
    (config_dir / "steamvr.vrsettings").write_text(json.dumps({"driver_eyetrackvr": {"enable": True}}))
    assert st.driver_state().steamvr_setting is None
    assert paths.read_text() == json.dumps(
        {"jsonid": "vrpathreg", "version": 1, "external_drivers": ["C:\\other", str(ours)], "config": [str(config_dir)]}
    )  # read only


def test_registration_read_helpers(tmp_path):
    ours = tmp_path / "a" / "steamvr_driver" / "eyetrackvr"
    ours.mkdir(parents=True)
    (ours / reg.MANIFEST).write_text(json.dumps({"name": "eyetrackvr"}))
    gone = str(tmp_path / "gone" / "steamvr_driver" / "eyetrackvr")  # an uninstalled copy
    paths = _openvrpaths(tmp_path, [str(tmp_path / "other" / "driver"), str(ours), gone])
    assert reg.registered_entries(paths) == [str(ours), gone]
    assert reg.registered_entries(None) is None  # conftest: no openvrpaths.vrpath
    paths.write_text("{not json")
    assert reg.registered_entries(paths) is None


def test_layer_read_helpers(tmp_path):
    from tests.conftest import _FakeRegistry

    layer = tmp_path / "layer"
    registry = _FakeRegistry()
    assert not xr.is_installed(layer, registry=registry) and xr.installed_entries(registry=registry) == []
    xr.sync(True, layer, registry=registry)
    assert xr.is_installed(layer, registry=registry)
    assert xr.installed_entries(registry=registry) == [str(layer / xr.MANIFEST)]
    registry.data["D:\\old\\XR_APILAYER_EYETRACKVR_eye_gaze.json"] = 0
    assert not xr.is_installed(layer, registry=registry)
    registry.data[str(layer / xr.MANIFEST)] = 1  # disabled
    registry.data.pop("D:\\old\\XR_APILAYER_EYETRACKVR_eye_gaze.json")
    assert not xr.is_installed(layer, registry=registry) and xr.installed_entries(registry=registry) == []


def test_layer_read_helpers_linux(monkeypatch, tmp_path):
    layer = tmp_path / "layer"
    layer.mkdir()
    (layer / xr.MANIFEST).write_text(json.dumps({"api_layer": {"library_path": "./x.so"}}))
    implicit = tmp_path / "implicit.d"
    monkeypatch.setattr(sys, "platform", "linux")
    assert not xr.is_installed(layer, implicit_dir=implicit)
    assert xr.sync(True, layer, implicit_dir=implicit) == xr.INSTALLED
    assert xr.is_installed(layer, implicit_dir=implicit)
    assert xr.installed_entries(implicit_dir=implicit) == [str(implicit / xr.MANIFEST)]


def test_find_vrserver_log_via_openvrpaths(monkeypatch, tmp_path):
    logs = tmp_path / "Steam" / "logs"
    logs.mkdir(parents=True)
    paths = _openvrpaths(tmp_path, [], log=[str(logs)], config=[str(tmp_path / "Steam" / "config")])
    monkeypatch.setattr(reg, "openvrpaths_file", lambda: paths)
    monkeypatch.setattr(st, "_steam_dirs", lambda: [])
    tail = st.find_vrserver_log()
    assert tail.path is None and tail.searched == [str(logs / "vrserver.txt")]  # deduplicated
    (logs / "vrserver.txt").write_text(_text(*GOOD), encoding="utf-8")
    tail = st.find_vrserver_log()
    assert tail.path == logs / "vrserver.txt" and st.parse_vrserver_log(tail.text).prop_value == 1


def test_find_vrserver_log_without_steamvr(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "_steam_dirs", lambda: [tmp_path / "NoSteam"])
    tail = st.find_vrserver_log()
    assert tail.path is None and tail.searched == [str(tmp_path / "NoSteam" / "logs" / "vrserver.txt")]


def test_probe_main_writes_one_json_line(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(st, "openvr_probe_payload", lambda: {"ok": False, "error": "x"})
    out = tmp_path / "probe.json"
    assert st.probe_main(str(out)) == 0
    assert json.loads(out.read_text()) == {"ok": False, "error": "x"}
    assert json.loads(capsys.readouterr().out) == {"ok": False, "error": "x"}


def test_run_openvr_probe_reads_the_child_result(monkeypatch):
    script = "import json, sys; open(sys.argv[1], 'w').write(json.dumps({'ok': True, 'model': 'X'}))"
    monkeypatch.setattr(st, "probe_command", lambda out: [sys.executable, "-c", script, str(out)])
    assert st.run_openvr_probe() == {"ok": True, "model": "X"}
    monkeypatch.setattr(st, "probe_command", lambda out: [sys.executable, "-c", "import sys; sys.exit(3)"])
    result = st.run_openvr_probe()
    assert result["ok"] is False and "code 3" in result["error"]


def test_probe_command_from_source():
    cmd = st.probe_command(Path("out.json"))
    assert cmd[1].endswith("eyetrackapp.py") and cmd[2:] == ["--gaze-selftest-probe", "out.json"]
