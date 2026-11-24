"""SteamVR dashboard panel (ovr/vr_dashboard.py) and its two ends: the companion
process draws it and reports clicks; the DFR controller sends what to show and acts on
the clicks. No SteamVR here: OpenVR is faked."""

import json
import queue
import threading
import types
from types import SimpleNamespace

import pytest

from ovr import dfr, dfr_monitor, vr_dashboard

GAME = "steam.app.823500"  # a Direct3D 11 OpenVR game with no foveation of its own


def state(available=True, enabled=False, mode="balanced"):
    return {
        "type": "state",
        "labels": {},
        "game": "Current game: Half-Life: Alyx",
        "dfr": {"available": available, "enabled": enabled, "mode": mode, "key": GAME},
    }


def center(button):
    left, top, right, bottom = button.rect
    return (left + right) / 2, (top + bottom) / 2


def by_name(buttons, name, value=None):
    return next(b for b in buttons if b.name == name and (value is None or b.value == value))


# ------------------------------------------------------------------ layout and clicks


def test_buttons_follow_the_dfr_state():
    off = vr_dashboard.layout(state())
    assert by_name(off, "recenter").enabled and by_name(off, "recalibrate").enabled
    switch = by_name(off, "dfr_enabled")
    assert switch.enabled and not switch.active and switch.value is True  # a click turns it on
    assert not any(b.enabled for b in off if b.name == "dfr_mode")  # quality only while on

    on = vr_dashboard.layout(state(enabled=True, mode="minimum"))
    assert by_name(on, "dfr_enabled").value is False and by_name(on, "dfr_enabled").active
    assert [b.value for b in on if b.name == "dfr_mode" and b.active] == ["minimum"]

    release = vr_dashboard.layout({**state(enabled=True), "qualities": ["maximum", "balanced", "minimum"]})
    assert [b.value for b in release if b.name == "dfr_mode"] == ["maximum", "balanced", "minimum"]

    no_game = vr_dashboard.layout(state(available=False, enabled=True))
    assert not any(b.enabled for b in no_game if b.name.startswith("dfr_"))
    assert by_name(no_game, "recenter").enabled  # recenter never depends on a game


def test_panel_has_no_foveated_rendering_part_where_injection_is_not_supported():
    pytest.importorskip("PIL")
    linux = dict(state(), dfr_supported=False)
    assert [b.name for b in vr_dashboard.layout(linux)] == ["recenter", "recalibrate", "gaze_marker"]
    assert vr_dashboard.render(linux).tobytes() != vr_dashboard.render(state()).tobytes()


def test_buttons_do_not_overlap_and_stay_on_the_panel():
    buttons = vr_dashboard.layout(state(enabled=True))
    for index, a in enumerate(buttons):
        assert 0 <= a.rect[0] < a.rect[2] <= vr_dashboard.WIDTH and 0 <= a.rect[1] < a.rect[3] <= vr_dashboard.HEIGHT
        for b in buttons[index + 1 :]:
            apart = a.rect[2] <= b.rect[0] or b.rect[2] <= a.rect[0] or a.rect[3] <= b.rect[1] or b.rect[3] <= a.rect[1]
            assert apart, (a, b)


def test_a_click_becomes_the_matching_action():
    current = state(enabled=True)
    buttons = vr_dashboard.layout(current)
    assert vr_dashboard.hit(buttons, 5, 5) is None
    recenter = vr_dashboard.hit(buttons, *center(by_name(buttons, "recenter")))
    assert vr_dashboard.action_for(recenter, current) == {"type": "action", "name": "recenter"}
    maximum = vr_dashboard.hit(buttons, *center(by_name(buttons, "dfr_mode", "maximum")))
    assert vr_dashboard.action_for(maximum, current) == {
        "type": "action",
        "name": "dfr_mode",
        "key": GAME,
        "value": "maximum",
    }
    disabled = vr_dashboard.layout(state(available=False))
    assert vr_dashboard.hit(disabled, *center(by_name(disabled, "dfr_enabled"))) is None


def test_panel_renders_in_every_state_and_language():
    pytest.importorskip("PIL")
    plain = vr_dashboard.render({})
    assert plain.size == (vr_dashboard.WIDTH, vr_dashboard.HEIGHT) and plain.mode == "RGBA"
    wide = state(enabled=True)
    wide["labels"] = {"recenter": "再センタリング", "calibrate": "キャリブレーション", "dfr_title": "注视点渲染"}
    assert vr_dashboard.render(wide).tobytes() != plain.tobytes()


# ------------------------------------------------------------------ overlay (fake OpenVR)


def fake_openvr(clicks=()):
    vr = types.ModuleType("openvr")
    vr.VREvent_MouseButtonDown = 200
    vr.VROverlayInputMethod_Mouse = 1
    calls = SimpleNamespace(raw=[], pending=list(clicks), destroyed=False)

    class Vector:
        def __init__(self):
            self.v = [0.0, 0.0]

    class Event:
        def __init__(self):
            self.eventType = 0
            self.data = SimpleNamespace(mouse=SimpleNamespace(x=0.0, y=0.0))

    class Overlay:
        def createDashboardOverlay(self, key, name):
            calls.key = key
            return 11, 12

        def setOverlayWidthInMeters(self, handle, width):
            pass

        def setOverlayInputMethod(self, handle, method):
            calls.input = method

        def setOverlayMouseScale(self, handle, scale):
            calls.scale = tuple(scale.v)

        def setOverlayFromFile(self, handle, path):
            calls.icon = path

        def pollNextOverlayEvent(self, handle, event):
            if not calls.pending:
                return False, event
            event.eventType = vr.VREvent_MouseButtonDown
            event.data.mouse.x, event.data.mouse.y = calls.pending.pop(0)
            return True, event

        def setOverlayRaw(self, handle, buffer, width, height, depth):
            if handle == 12:  # the dashboard tab's thumbnail
                calls.icon_raw = (len(buffer), width, height, depth)
                return
            calls.raw.append((handle, len(buffer), width, height, depth))

        def destroyOverlay(self, handle):
            calls.destroyed = True

        def createOverlay(self, key, name):
            calls.marker_key = key
            return 21

        def showOverlay(self, handle):
            calls.shown.append(True)

        def hideOverlay(self, handle):
            calls.shown.append(False)

        def setOverlayTransformTrackedDeviceRelative(self, handle, device, matrix):
            calls.transforms.append((handle, device, [list(row) for row in matrix.m]))

    class Matrix:
        def __init__(self):
            self.m = [[0.0] * 4 for _ in range(3)]

    calls.shown, calls.transforms = [], []
    vr.HmdMatrix34_t = Matrix
    vr.k_unTrackedDeviceIndex_Hmd = 0
    vr.VROverlay = Overlay
    vr.HmdVector2_t = Vector
    vr.VREvent_t = Event
    return vr, calls


def test_overlay_redraws_only_on_change_and_flips_the_mouse_y():
    pytest.importorskip("PIL")
    current = state(enabled=True)
    x, y = center(by_name(vr_dashboard.layout(current), "recenter"))
    # OpenVR's mouse origin is the bottom left; the panel is laid out from the top left.
    vr, calls = fake_openvr(clicks=[(x, vr_dashboard.HEIGHT - y)])
    sent = []
    panel = vr_dashboard.Dashboard(vr, sent.append)
    assert calls.key == vr_dashboard.OVERLAY_KEY and calls.scale == (vr_dashboard.WIDTH, vr_dashboard.HEIGHT)
    # The tab icon: the logo on its rounded tile, uploaded as pixels.
    assert calls.icon_raw == (256 * 256 * 4, 256, 256, 4)
    panel.set_state(current)
    panel.poll()
    assert sent == [{"type": "action", "name": "recenter"}]
    assert calls.raw == [(11, vr_dashboard.WIDTH * vr_dashboard.HEIGHT * 4, vr_dashboard.WIDTH, vr_dashboard.HEIGHT, 4)]
    panel.poll()
    assert len(calls.raw) == 1  # nothing changed: no new texture
    panel.set_state(state(enabled=False))
    panel.poll()
    assert len(calls.raw) == 2
    panel.close()
    assert calls.destroyed


# ------------------------------------------------------------------ gaze marker


def _sample(direction, count=1, valid=True):
    from osc.gaze_shared_memory import FLAG_GAZE_VALID, GazeEye

    eye = GazeEye(direction, 1.0, 1.0, FLAG_GAZE_VALID if valid else 0)
    return {"sample_count": count, "eyes": [eye, eye, eye]}


def test_marker_sits_along_the_gaze_and_faces_the_eyes():
    forward = vr_dashboard.marker_transform((0.0, 0.0, -1.0), 2.0)
    assert forward == ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, -2.0))  # straight ahead: unrotated
    s = 0.5**0.5
    right = vr_dashboard.marker_transform((s, 0.0, -s), 1.0)  # 45 degrees to the right
    assert right[0][3] == pytest.approx(s) and right[2][3] == pytest.approx(-s)
    normal = (right[0][2], right[1][2], right[2][2])
    assert normal == pytest.approx((-s, 0.0, s))  # its face points back at the viewer
    for a, b in ((0, 1), (0, 2), (1, 2)):  # an orthonormal frame, so the ring is not skewed
        assert sum(right[r][a] * right[r][b] for r in range(3)) == pytest.approx(0.0)


def test_gaze_direction_uses_only_valid_forward_samples():
    assert vr_dashboard.gaze_direction(None) is None
    assert vr_dashboard.gaze_direction(_sample((0.0, 0.0, -1.0), valid=False)) is None
    assert vr_dashboard.gaze_direction(_sample((0.0, 0.0, 1.0))) is None  # behind the head: nonsense
    assert vr_dashboard.gaze_direction(_sample((0.0, 0.0, -2.0))) == pytest.approx((0.0, 0.0, -1.0))


def test_marker_follows_fresh_gaze_and_hides_when_it_stops():
    pytest.importorskip("PIL")
    vr, calls = fake_openvr()
    samples, now = [_sample((0.0, 0.0, -1.0), count=1)], [0.0]
    marker = vr_dashboard.GazeMarker(vr, read_sample=lambda: samples[0], clock=lambda: now[0])
    assert calls.marker_key == vr_dashboard.MARKER_KEY
    marker.update()
    assert calls.shown == [True] and calls.transforms[-1][1] == vr.k_unTrackedDeviceIndex_Hmd
    assert calls.transforms[-1][2][2][3] == pytest.approx(-vr_dashboard.MARKER_DISTANCE_M)
    now[0] = 0.2
    marker.update()
    assert calls.shown == [True]  # the same sample, still recent: stays where it is
    now[0] = 2.0
    marker.update()
    assert calls.shown == [True, False]  # the app stopped publishing
    samples[0] = _sample((0.0, 0.0, -1.0), count=2, valid=False)
    marker.update()
    assert calls.shown == [True, False]  # eyes closed: stays hidden
    samples[0] = _sample((0.1, 0.0, -1.0), count=3)
    marker.update()
    assert calls.shown == [True, False, True]


def test_gaze_marker_button_toggles_the_marker_without_asking_the_app():
    pytest.importorskip("PIL")
    current = state()
    x, y = center(by_name(vr_dashboard.layout(current), "gaze_marker"))
    click = (x, vr_dashboard.HEIGHT - y)
    vr, calls = fake_openvr(clicks=[click])
    sent = []
    panel = vr_dashboard.Dashboard(vr, sent.append, read_sample=lambda: _sample((0.0, 0.0, -1.0)))
    panel.set_state(current)
    panel.poll()
    assert panel.marker_on and sent == [] and calls.shown == [True]
    assert by_name(vr_dashboard.layout(panel._view()), "gaze_marker").active
    assert len(calls.raw) == 2  # the marker's ring, then the panel with the button lit
    calls.pending.append(click)
    panel.poll()
    assert not panel.marker_on


def _companion_openvr(overlay_vr, fail_overlay=False):
    """The fake overlay API plus the scene/event API the companion loop needs."""
    vr = overlay_vr
    vr.VRApplication_Background = 3
    vr.VREvent_Quit = 700
    vr.VRApplicationProperty_Name_String = 2000
    vr.init = lambda kind: None
    vr.shutdown = lambda: None
    vr.VRApplications = lambda: SimpleNamespace(getCurrentSceneProcessId=lambda: 0)
    vr.VRSystem = lambda: SimpleNamespace(pollNextEvent=lambda event: False)
    if fail_overlay:

        def broken():
            raise RuntimeError("no overlay interface")

        vr.VROverlay = broken
    return vr


def _run_companion(monkeypatch, vr, messages, until):
    import sys

    monkeypatch.setitem(sys.modules, "openvr", vr)
    monkeypatch.setattr(dfr_monitor, "TICK_S", 0.005)
    sent, stop, inbox = [], threading.Event(), queue.Queue()
    for message in messages:
        inbox.put(message)

    def emit(message):
        sent.append(message)
        if until(sent):
            stop.set()

    watchdog = threading.Timer(5, stop.set)
    watchdog.start()
    try:
        assert dfr_monitor._monitor(emit, stop, inbox) == 0
    finally:
        watchdog.cancel()
    return sent


def test_companion_shows_the_panel_after_the_first_state_and_reports_clicks(monkeypatch):
    pytest.importorskip("PIL")
    current = state()
    x, y = center(by_name(vr_dashboard.layout(current), "dfr_enabled"))
    vr, calls = fake_openvr(clicks=[(x, vr_dashboard.HEIGHT - y)])
    sent = _run_companion(monkeypatch, _companion_openvr(vr), [current], lambda s: s[-1].get("type") == "action")
    assert sent[0] == {"type": "scene", "pid": 0}
    assert sent[-1] == {"type": "action", "name": "dfr_enabled", "key": GAME, "value": True}
    assert calls.destroyed  # the overlay goes away with the companion


def test_companion_keeps_reporting_games_when_the_panel_cannot_be_created(monkeypatch):
    vr, _calls = fake_openvr()
    sent = _run_companion(
        monkeypatch, _companion_openvr(vr, fail_overlay=True), [state()], lambda s: s[-1].get("type") == "error"
    )
    assert sent[0] == {"type": "scene", "pid": 0} and "dashboard unavailable" in sent[-1]["message"]


# ------------------------------------------------------------------ controller side


class FakeSocket:
    def __init__(self):
        self.lines = []

    def sendall(self, data):
        self.lines += [json.loads(line) for line in data.decode("utf-8").splitlines()]

    def close(self):
        pass


def controller(tmp_path, dashboard=True, complete=True):
    tool = tmp_path / "tool"
    tool.mkdir(exist_ok=True)
    if complete:
        for name in dfr.TOOL_FILES:
            (tool / name).write_bytes(b"x")
    settings = SimpleNamespace(
        gui_dfr_tool_dir=str(tool), gui_dfr_games={}, gui_foveation_gaze=False, gui_vr_dashboard=dashboard
    )
    config = SimpleNamespace(settings=settings)
    config.update = lambda data, save=False: [setattr(settings, key, value) for key, value in data.items()]

    class Registry:
        values: dict = {}

        def get(self, name):
            return self.values.get(name)

        def set(self, name, value):
            self.values[name] = value

    c = dfr.DfrController(
        config=config,
        registry=Registry(),
        attach=lambda d, pid: True,
        steamvr_running=lambda: True,
        dfr_ui_running=lambda: False,
        system_files_ok=lambda d: True,
        gaze_ready=lambda: False,
        has_module=lambda pid: False,
        tracking=lambda exe: "",
        is_active=lambda pid: True,
        module_loaded=lambda pid, dll: dll in ("d3d11.dll", "openvr_api.dll"),
    )
    c.monitors = []
    c._ensure_monitor = c.monitors.append
    c.PROCESS_CHECK_S = c.TOOL_CHECK_S = c.SYSTEM_CHECK_S = 0.0
    c._monitor_socket = FakeSocket()
    return c


def scene(c, pid=100, key=GAME):
    c.on_monitor_message({"type": "scene", "pid": pid, "key": key, "name": "Half-Life: Alyx", "exe": ""})


def test_controller_sends_the_state_once_per_change(tmp_path):
    c = controller(tmp_path)
    scene(c)
    lines = c._monitor_socket.lines
    assert lines[-1]["dfr"] == {
        "available": True,
        "enabled": False,
        "mode": "balanced",
        "key": GAME,
    }
    count = len(lines)
    c.tick()
    c.tick()
    assert len(lines) == count  # unchanged: nothing sent
    c.set_game(GAME, mode="maximum")
    assert lines[-1]["dfr"]["mode"] == "maximum" and len(lines) == count + 1
    scene(c, pid=0)
    assert lines[-1]["dfr"]["available"] is False


def test_games_handled_another_way_have_no_switch_and_say_why(tmp_path):
    c = controller(tmp_path)
    scene(c, key="steam.app.546560")  # Half-Life: Alyx has its own foveated rendering
    sent = c._monitor_socket.lines[-1]
    assert sent["dfr"]["available"] is False and sent["note"]
    scene(c, pid=101, key=GAME)
    assert c._monitor_socket.lines[-1]["note"] == ""


def test_other_platforms_get_the_panel_without_foveated_rendering(tmp_path, monkeypatch):
    c = controller(tmp_path)
    c.registry = None  # as on Linux: no FR-Utility registry, so no injection
    monkeypatch.setattr(dfr.sys, "platform", "linux")
    assert c.tick().state == dfr.UNSUPPORTED and c.monitors[-1] is True
    assert c._monitor_socket.lines[-1]["dfr_supported"] is False


def test_no_state_is_sent_with_the_dashboard_off(tmp_path):
    c = controller(tmp_path, dashboard=False)
    scene(c)
    assert c._monitor_socket.lines == []


def test_dashboard_keeps_the_companion_running_before_dfr_is_set_up(tmp_path):
    c = controller(tmp_path, complete=False)
    assert c.tick().state == dfr.TOOL_MISSING and c.monitors[-1] is True
    assert c._monitor_socket.lines[-1]["dfr"]["available"] is False  # recenter and calibrate still work
    off = controller(tmp_path, dashboard=False, complete=False)
    assert off.tick().state == dfr.TOOL_MISSING and off.monitors[-1] is False


def test_dashboard_actions_run_through_the_apps_handlers(tmp_path):
    c = controller(tmp_path)
    done, ui = [], []
    c.actions.update(recenter=lambda: done.append("recenter"), recalibrate=lambda: done.append("recalibrate"))
    c.run_on_ui = lambda action: (ui.append(1), action())
    c.on_monitor_message({"type": "action", "name": "recenter"})
    c.on_monitor_message({"type": "action", "name": "recalibrate"})
    c.on_monitor_message({"type": "action", "name": "format_disk"})  # unknown: ignored
    assert done == ["recenter", "recalibrate"] and len(ui) == 2


def test_dashboard_switch_turns_dfr_and_the_gaze_output_on_for_the_game_in_front(tmp_path):
    c = controller(tmp_path)
    scene(c)
    c.on_monitor_message({"type": "action", "name": "dfr_enabled", "key": "steam.app.999", "value": True})
    assert c.config.settings.gui_dfr_games == {}  # a click for a game that is no longer in front
    c.on_monitor_message({"type": "action", "name": "dfr_enabled", "key": GAME, "value": True})
    assert c.config.settings.gui_dfr_games[GAME]["enabled"] is True
    assert c.config.settings.gui_foveation_gaze is True  # the game needs it before it is attached
    c.on_monitor_message({"type": "action", "name": "dfr_mode", "key": GAME, "value": "minimum"})
    c.on_monitor_message({"type": "action", "name": "dfr_mode", "key": GAME, "value": "ludicrous"})
    assert c.config.settings.gui_dfr_games[GAME]["mode"] == "minimum"


def test_panel_has_no_flip_vertical_button():
    # Flip vertical is set in the app's foveated rendering settings only.
    names = [b.name for b in vr_dashboard.layout(state(enabled=True))]
    assert names[:4] == ["recenter", "recalibrate", "gaze_marker", "dfr_enabled"]
    assert set(names[4:]) == {"dfr_mode"}
    assert "flip_vertical" not in vr_dashboard.DEFAULT_LABELS


def test_a_failing_handler_does_not_stop_the_reader(tmp_path):
    c = controller(tmp_path)

    def broken():
        raise RuntimeError("boom")

    c.actions["recenter"] = broken
    c.on_monitor_message({"type": "action", "name": "recenter"})  # logged, not raised
