"""VRChat native face tracking (/tracking/face/v1) output in the pyVRCFT port."""

import io
import json
import queue
from types import SimpleNamespace
from unittest import mock

import pytest

from osc.osc import FULL_FACE_ADDRESS, OSCManager, OSCReceiver
from pyvrcft import FACE_V1_KEYS, UnifiedTrackingData, VRCFTClient, compute_face_v1
from pyvrcft import avatar as pyavatar
from pyvrcft import client as pyclient
from pyvrcft import osc as pyosc
from pyvrcft.avatar import AvatarInfo

FACE = "/tracking/face/v1"


def _byte(name, payload):
    return payload[FACE_V1_KEYS.index(name)]


def _face_payloads(client):
    return [args[0] for address, args in pyosc.parse(b"".join(_bundle(client))) if address == FACE]


def _bundle(client):
    return pyosc.pack_bundles(client._collect_messages())


# ------------------------------------------------------------------ OSC codec


def test_blob_encodes_size_and_padding_and_round_trips():
    payload = bytes(range(102))
    encoded = pyosc.encode_message(FACE, [payload])
    # address(20) + ",b\0\0"(4) + int32 size(4) + 102 data + 2 pad
    assert len(encoded) == 20 + 4 + 4 + 104
    assert encoded[20:24] == b",b\x00\x00"
    assert pyosc.parse(encoded) == [(FACE, [payload])]


def test_blob_with_bad_size_is_dropped_not_raised():
    encoded = bytearray(pyosc.encode_message(FACE, [b"\x01\x02"]))
    encoded[24:28] = (999).to_bytes(4, "big")
    assert pyosc.parse(bytes(encoded)) == [(FACE, [])]


# -------------------------------------------------------------------- payload


def test_key_order_matches_vrchat_docs():
    assert len(FACE_V1_KEYS) == 102
    assert FACE_V1_KEYS[0] == "EyeLookOutRight"
    assert FACE_V1_KEYS[8:10] == ("EyeClosedRight", "EyeClosedLeft")
    assert FACE_V1_KEYS.index("JawOpen") == 36  # the docs' worked example
    assert FACE_V1_KEYS[-1] == "NeckFlexLeft"


def test_neutral_frame_is_open_eyes_and_zeros():
    payload = compute_face_v1(UnifiedTrackingData())
    assert len(payload) == 102
    assert payload == bytes(102)


def test_gaze_splits_into_look_halves_per_eye():
    data = UnifiedTrackingData()
    for eye in (data.eye.left, data.eye.right):
        eye.gaze = (1.0, -0.5)  # right and down
    p = compute_face_v1(data)
    # Looking right: right eye looks out, left eye looks in.
    assert _byte("EyeLookOutRight", p) == 255 and _byte("EyeLookInRight", p) == 0
    assert _byte("EyeLookInLeft", p) == 255 and _byte("EyeLookOutLeft", p) == 0
    assert _byte("EyeLookDownRight", p) == _byte("EyeLookDownLeft", p) == 128
    assert _byte("EyeLookUpRight", p) == _byte("EyeLookUpLeft", p) == 0


def test_openness_and_shapes_map_through():
    data = UnifiedTrackingData()
    data.eye.left.openness = 0.0
    data.eye.right.openness = 0.6
    data.shapes["JawOpen"] = 1.0
    data.shapes["EyeSquintLeft"] = 2.0  # clamped
    data.shapes["BrowInnerUpRight"] = -1.0  # clamped
    p = compute_face_v1(data)
    assert _byte("EyeClosedLeft", p) == 255
    assert _byte("EyeClosedRight", p) == 102
    assert p[36] == 255
    assert _byte("EyeSquintLeft", p) == 255
    assert _byte("BrowInnerUpRight", p) == 0


def test_non_finite_values_become_zero():
    data = UnifiedTrackingData()
    data.eye.right.gaze = (float("nan"), float("inf"))
    p = compute_face_v1(data)
    assert _byte("EyeLookOutRight", p) == 0
    assert _byte("EyeLookUpRight", p) == 0


def test_pupil_drives_dilation_above_midpoint_and_constrict_below():
    data = UnifiedTrackingData()
    # Running max/min (VRCFT updates the min only below the current max).
    for mm in (6.0, 2.0):
        data.eye.left.pupil_diameter_mm = data.eye.right.pupil_diameter_mm = mm
        data.eye.combined()
    data.eye.left.pupil_diameter_mm = data.eye.right.pupil_diameter_mm = 5.0  # 0.75
    p = compute_face_v1(data)
    assert _byte("EyeDilationLeft", p) == _byte("EyeDilationRight", p) == 128
    assert _byte("EyeConstrictLeft", p) == 0
    data.eye.left.pupil_diameter_mm = data.eye.right.pupil_diameter_mm = 3.0  # 0.25
    p = compute_face_v1(data)
    assert _byte("EyeConstrictLeft", p) == _byte("EyeConstrictRight", p) == 128
    assert _byte("EyeDilationLeft", p) == 0


# --------------------------------------------------------------------- gating


@pytest.fixture()
def client(monkeypatch):
    # Resolve every avatar to an empty, flag-less config without touching disk.
    monkeypatch.setattr(pyclient, "load_avatar_config", lambda avatar_id: AvatarInfo(id=avatar_id))
    return VRCFTClient(use_oscquery=False)


def _frame():
    data = UnifiedTrackingData()
    data.shapes["JawOpen"] = 1.0
    return data


def test_face_payload_off_until_avatar_reports_full_face(client):
    client.update_tracking(_frame())
    assert _face_payloads(client) == []

    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    (payload,) = _face_payloads(client)
    assert payload[36] == 255
    # Send-on-change: an identical frame is not resent.
    client.update_tracking(_frame())
    assert _face_payloads(client) == []


def test_avatar_change_closes_gate_and_false_stays_closed(client):
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client._dispatch("/avatar/change", ["avtr_new"])
    client.update_tracking(_frame())
    assert _face_payloads(client) == []

    client._dispatch(FULL_FACE_ADDRESS, [False])
    client.update_tracking(_frame())
    assert _face_payloads(client) == []


def test_reopening_gate_resends_unchanged_payload(client):
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    assert len(_face_payloads(client)) == 1
    client._dispatch(FULL_FACE_ADDRESS, [False])
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    assert len(_face_payloads(client)) == 1


def test_oscquery_flag_used_when_osc_did_not_report(client, monkeypatch):
    monkeypatch.setattr(
        pyclient, "load_avatar_config", lambda avatar_id: AvatarInfo(id=avatar_id, full_face_tracking=True)
    )
    client._dispatch("/avatar/change", ["avtr_ft"])
    client.update_tracking(_frame())
    assert len(_face_payloads(client)) == 1


def test_osc_flag_beats_stale_oscquery_snapshot(client, monkeypatch):
    """EyeTrackVR's receiver path: the flag can land before the resolve thread."""
    resolved = []

    def slow_config(avatar_id):
        resolved.append(avatar_id)
        return AvatarInfo(id=avatar_id, full_face_tracking=True)  # stale: old avatar's value

    monkeypatch.setattr(pyclient, "load_avatar_config", slow_config)
    with mock.patch.object(pyclient.threading, "Thread") as thread:
        client.notify_avatar_change("avtr_plain")
        client.notify_full_face_tracking(False)
        # Now let the deferred resolve run.
        kwargs = thread.call_args.kwargs
        kwargs["target"](*kwargs["args"], **kwargs["kwargs"])
    assert resolved == ["avtr_plain"]
    client.update_tracking(_frame())
    assert _face_payloads(client) == []


def test_native_face_disabled_never_sends(monkeypatch):
    monkeypatch.setattr(pyclient, "load_avatar_config", lambda avatar_id: AvatarInfo(id=avatar_id))
    client = VRCFTClient(use_oscquery=False, native_face=False)
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    assert _face_payloads(client) == []


def test_eye_endpoints_still_sent_alongside_face(client):
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    addresses = {address for address, _ in pyosc.parse(b"".join(_bundle(client)))}
    assert {FACE, "/tracking/eye/LeftRightPitchYaw", "/tracking/eye/EyesClosedAmount"} <= addresses


# ------------------------------------------------------------------- OSCQuery


def _oscquery_tree(full_face):
    contents = {
        "change": {"FULL_PATH": "/avatar/change", "TYPE": "s", "VALUE": ["avtr_x"]},
        "parameters": {"FULL_PATH": "/avatar/parameters", "CONTENTS": {}},
    }
    if full_face is not None:
        contents["avatarfullfacetracking"] = {
            "FULL_PATH": FULL_FACE_ADDRESS,
            "TYPE": "T",
            "VALUE": [full_face],
        }
    return {"FULL_PATH": "/avatar", "CONTENTS": contents}


@pytest.mark.parametrize("full_face", [True, False, None])
def test_fetch_avatar_oscquery_reads_full_face_flag(monkeypatch, full_face):
    body = io.BytesIO(json.dumps(_oscquery_tree(full_face)).encode())
    monkeypatch.setattr(pyavatar.urllib.request, "urlopen", lambda url, timeout: body)
    monkeypatch.setattr(pyavatar, "load_avatar_name", lambda avatar_id: "")
    info = pyavatar.fetch_avatar_oscquery("127.0.0.1", 1)
    assert info.id == "avtr_x"
    assert info.full_face_tracking is full_face


# ------------------------------------------------------- EyeTrackVR receiver


def test_manager_forwards_full_face_to_pyvrcft(main_config):
    manager = OSCManager(queue.Queue(), main_config)
    client = mock.Mock()
    manager.osc_sender = SimpleNamespace(pyvrcft_sender=SimpleNamespace(client=client))
    for listener in manager.listeners[FULL_FACE_ADDRESS]:
        listener(SimpleNamespace(data=True))
    client.notify_full_face_tracking.assert_called_once_with(True)


def test_receiver_advertises_full_face_over_oscquery(main_config):
    manager = OSCManager(queue.Queue(), main_config)
    receiver = OSCReceiver.__new__(OSCReceiver)
    receiver.listeners = manager.listeners
    assert FULL_FACE_ADDRESS in receiver.endpoints()


def test_sender_passes_native_face_setting(main_config):
    from osc import pyvrcft_sender as sender_module

    s = main_config.settings
    s.gui_pyvrcft_native_face = False
    sender = sender_module.PyVRCFTSender()
    with mock.patch.object(sender_module, "VRCFTClient") as fake:
        sender.start(s)
    assert fake.call_args.kwargs["native_face"] is False
    assert "gui_pyvrcft_native_face" in OSCManager.SENDER_TRIGGER_KEYS
