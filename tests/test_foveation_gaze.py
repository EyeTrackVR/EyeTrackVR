"""Foveation gaze output: VRChat-style LeftRightPitchYaw to UDP 9020 for
PimaxMagic4All, sent alongside whichever VRChat output mode is active."""

import math
import socket
import sys
import uuid
from queue import Queue
from time import monotonic, sleep
from unittest import mock

import pytest

from eye import EyeId
from osc import FoveationGazeSender as foveation_module
from osc.osc import OSCManager
from osc.OSCMessage import OSCMessage, OSCMessageType
from pyvrcft import osc as pyosc
from tests import EyeInfoMock, SimpleUDPClientMock

ADDRESS = foveation_module.FOVEATION_ADDRESS


@pytest.fixture(autouse=True)
def private_shm_names(monkeypatch):
    """Never touch the gaze block a running EyeTrackVR publishes."""
    from osc import GazeSharedMemory as shm_module

    tag = uuid.uuid4().hex
    monkeypatch.setattr(shm_module, "WIN32_NAME", f"Local\\EyeTrackVR.Gaze.test.{tag}")
    monkeypatch.setattr(shm_module, "POSIX_PATH", f"/dev/shm/eyetrackvr_gaze_test_{tag}")


def _eye_msg(eye_id=EyeId.RIGHT, **kw):
    fields = dict(x=0.0, y=0.0, blink=1.0, pupil_dilation=0.0, avg_velocity=0.0)
    fields.update(kw)
    return OSCMessage(type=OSCMessageType.EYE_INFO, data=(eye_id, EyeInfoMock(**fields)))


def _wait_until_sent(msg_queue, timeout=5.0):
    deadline = monotonic() + timeout
    while msg_queue.unfinished_tasks and monotonic() < deadline:
        sleep(0.005)
    assert msg_queue.unfinished_tasks == 0, "sender stopped consuming the queue"


def _run(config, messages):
    """Feed messages through a mocked-UDP OSCManager; return (manager, sent)."""
    msg_queue = Queue()
    with mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        manager = OSCManager(config=config, osc_message_in_queue=msg_queue)
        manager.start()
        try:
            for message in messages:
                msg_queue.put(message)
            _wait_until_sent(msg_queue)
            assert manager.osc_sender_thread.is_alive()
        finally:
            manager.shutdown()
    client = manager.osc_sender.foveation_client
    sent = [v for a, v in client.messages if a == ADDRESS] if client is not None else None
    return manager, sent


def _expected(x, y, s):
    """Degrees for normalized gaze, using the configured FOV caps."""
    yaw = math.degrees(math.atan(x * math.tan(math.radians(s.gui_gaze_yaw_max_deg))))
    cap = s.gui_gaze_pitch_up_deg if y >= 0 else s.gui_gaze_pitch_down_deg
    pitch = -math.degrees(math.atan(y * math.tan(math.radians(cap))))
    return pitch, yaw


@pytest.fixture()
def two_eye_config(main_config_v2_params):
    main_config_v2_params.eye_display_id = EyeId.BOTH
    main_config_v2_params.settings.gui_foveation_gaze = True
    return main_config_v2_params


def test_off_by_default(main_config_v2_params):
    assert main_config_v2_params.settings.gui_foveation_gaze is False
    manager, sent = _run(main_config_v2_params, [_eye_msg(x=0.5)])
    assert sent is None
    # VRChat output is untouched.
    assert ("/avatar/parameters/v2/EyeX", 0.5) in manager.osc_sender.vrc_client.messages


def test_sends_to_localhost_9020_alongside_vrchat(main_config_v2_params):
    main_config_v2_params.settings.gui_foveation_gaze = True
    manager, sent = _run(main_config_v2_params, [_eye_msg(x=0.5, y=0.5)])
    client = manager.osc_sender.foveation_client
    assert (client.osc_address, client.port) == ("127.0.0.1", 9020)
    p, y = _expected(0.5, 0.5, main_config_v2_params.settings)
    assert sent == [pytest.approx([p, y, p, y])]
    # Looking up and right: pitch negative (VRChat: positive is down), yaw positive.
    assert p < 0 < y
    assert ("/avatar/parameters/v2/EyeX", 0.5) in manager.osc_sender.vrc_client.messages


@pytest.mark.parametrize("mode", ["gui_pyvrcft", "gui_vrc_native", "gui_osc_vrcft_v2"])
def test_runs_with_every_output_mode(main_config, mode):
    s = main_config.settings
    s.gui_pyvrcft = s.gui_vrc_native = s.gui_osc_vrcft_v1 = s.gui_osc_vrcft_v2 = False
    setattr(s, mode, True)
    s.gui_foveation_gaze = True
    with mock.patch("pyvrcft.client.VRCFTClient.start"), mock.patch("pyvrcft.client.VRCFTClient.stop"):
        _, sent = _run(main_config, [_eye_msg(x=-0.25, y=-0.5)])
    p, y = _expected(-0.25, -0.5, s)
    assert sent == [pytest.approx([p, y, p, y])]


def test_two_eyes_tracked_separately(two_eye_config):
    s = two_eye_config.settings
    _, sent = _run(
        two_eye_config,
        [_eye_msg(EyeId.LEFT, x=-0.2, y=0.1), _eye_msg(EyeId.RIGHT, x=0.3, y=-0.4)],
    )
    lp, ly = _expected(-0.2, 0.1, s)
    rp, ry = _expected(0.3, -0.4, s)
    # Before the right eye's first sample it borrows the left eye's gaze.
    assert sent == [pytest.approx([lp, ly, lp, ly]), pytest.approx([lp, ly, rp, ry])]


def test_closed_eye_borrows_open_eye_and_blink_sends_nothing(two_eye_config):
    s = two_eye_config.settings
    _, sent = _run(
        two_eye_config,
        [
            _eye_msg(EyeId.LEFT, x=0.4, y=0.0),
            _eye_msg(EyeId.RIGHT, x=-0.9, y=0.9, blink=0.1),  # right lid closed
            _eye_msg(EyeId.LEFT, x=0.4, y=0.0, blink=0.0),  # both closed now
        ],
    )
    p, y = _expected(0.4, 0.0, s)
    assert sent == [pytest.approx([p, y, p, y])] * 2


def test_inverted_eyelid_setting_is_respected(two_eye_config):
    two_eye_config.settings.osc_invert_eye_close = True
    # blink=1.0 means closed under inversion.
    _, sent = _run(two_eye_config, [_eye_msg(EyeId.LEFT, x=0.4, blink=1.0)])
    assert sent == []


def test_non_finite_gaze_is_not_sent(main_config_v2_params):
    main_config_v2_params.settings.gui_foveation_gaze = True
    _, sent = _run(
        main_config_v2_params,
        [_eye_msg(x=float("nan"), y=0.0), _eye_msg(x=0.1, y=float("inf")), _eye_msg(x=0.1, y=0.0)],
    )
    p, y = _expected(0.1, 0.0, main_config_v2_params.settings)
    assert sent == [pytest.approx([p, y, p, y])]


def test_foveation_failure_does_not_cost_vrchat_output(main_config_v2_params):
    main_config_v2_params.settings.gui_foveation_gaze = True
    with mock.patch.object(
        foveation_module.FoveationGazeSender, "output_osc_info", side_effect=RuntimeError("boom")
    ):
        manager, _ = _run(main_config_v2_params, [_eye_msg(x=0.3)])
    assert ("/avatar/parameters/v2/EyeX", 0.3) in manager.osc_sender.vrc_client.messages


def test_toggle_restarts_sender():
    assert "gui_foveation_gaze" in OSCManager.SENDER_TRIGGER_KEYS


def test_real_udp_packet_matches_pimax_parser(main_config_v2_params):
    """On the wire: one message, four float32 args, as vrchat_osc.cpp reads them."""
    main_config_v2_params.settings.gui_foveation_gaze = True
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    try:
        msg_queue = Queue()
        with mock.patch("osc.osc.FOVEATION_PORT", sock.getsockname()[1]):
            manager = OSCManager(config=main_config_v2_params, osc_message_in_queue=msg_queue)
            manager.start()
            try:
                msg_queue.put(_eye_msg(x=0.5, y=-0.5))
                _wait_until_sent(msg_queue)
                data, _ = sock.recvfrom(65535)
            finally:
                manager.shutdown()
    finally:
        sock.close()
    assert data.startswith(ADDRESS.encode() + b"\0")
    assert b",ffff\0" in data
    [(address, args)] = pyosc.parse(data)
    p, y = _expected(0.5, -0.5, main_config_v2_params.settings)
    assert address == ADDRESS
    assert args == pytest.approx([p, y, p, y], abs=1e-4)


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_mutex_held_only_while_running(main_config_v2_params):
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.OpenMutexW.restype = ctypes.c_void_p

    def mutex_exists():
        handle = kernel32.OpenMutexW(0x00100000, False, foveation_module.FOVEATION_MUTEX)  # SYNCHRONIZE
        if handle:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        return bool(handle)

    main_config_v2_params.settings.gui_foveation_gaze = True
    msg_queue = Queue()
    with mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        manager = OSCManager(config=main_config_v2_params, osc_message_in_queue=msg_queue)
        manager.start()
        try:
            msg_queue.put(_eye_msg())
            _wait_until_sent(msg_queue)
            assert mutex_exists()
        finally:
            manager.shutdown()
    assert not mutex_exists()
