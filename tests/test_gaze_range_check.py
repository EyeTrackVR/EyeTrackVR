"""The gaze range check steps dots out to the edge of the headset's view and
measures how far out the calibrated gaze still lands on them."""

import math
import threading
import time
from types import SimpleNamespace

import pytest

import gaze_capture
import gaze_range_check as check
import next_smartcal
from calibration_state import var
from eye import EyeId
from gaze_range_report import headset_report, log_report
from next_smartcal import SMARTCAL_SPACE_ANGLE, next_smartcal_dot_tangents, smartcal_tangents_to_gaze
from tests import interactive_overlay
from tests.test_next_smartcal import GAZE_RANGE_LINE

SETTINGS = SimpleNamespace(
    gui_gaze_yaw_max_deg=40.0,
    gui_gaze_pitch_up_deg=15.0,
    gui_gaze_pitch_down_deg=40.0,
    osc_invert_eye_close=False,
)
# The range the overlay logs when it can show the whole configured range.
FULL_RANGE_LINE = GAZE_RANGE_LINE.replace("(±30°)", "(±40°)")
GAZE_RANGE = (40.0, 15.0, -40.0, 0.0)


def _tangents(points, gaze_range=GAZE_RANGE):
    return next_smartcal_dot_tangents(gaze_range, [(nx, ny) for _, _, nx, ny in points])


def _on_target(target, n=10, pitch_off_deg=0.0, openness=1.0):
    pitch = math.atan(target[1]) + math.radians(pitch_off_deg)
    return [(target[0], math.tan(pitch), openness)] * n


def test_dots_step_outward_to_the_edge_of_the_range():
    points = check.check_points()
    assert len(points) == 4 * 4 + 4 * 3
    for name, _, levels in check.RAYS:
        ray = [(level, math.hypot(nx, ny)) for point_name, level, nx, ny in points if point_name == name]
        assert [level for level, _ in ray] == list(levels)
        assert [radius for _, radius in ray] == pytest.approx(list(levels))


def test_the_dots_go_out_to_the_headset_view_not_the_output_limits():
    assert check.overlay_range_args() == ["--coverage=0.9", "--max-deg=89", "--max-deg-up=89", "--max-deg-down=89"]


def test_the_gaze_is_read_through_the_calibration_before_the_limits_clip_it():
    calibrated = SimpleNamespace(
        _next_smartcal_w=[2.0, 0.0, 0.0, 2.0, 0.0, 2.0],
        _next_smartcal_b=[0.0, 0.1],
        _next_smartcal_warp=SMARTCAL_SPACE_ANGLE,
    )
    uncalibrated = SimpleNamespace(_next_smartcal_w=None, _next_smartcal_b=None)
    frames = [(0.0, 0.9, 0.4, 0.8, 0.5)]
    # 2 * 0.9 is far past tan(40 deg): the check sees it, the output would not.
    assert check.gaze_samples([(calibrated, frames)], SETTINGS) == [[pytest.approx((1.8, 0.9, 0.8))]]
    tan40, tan15 = math.tan(math.radians(40.0)), math.tan(math.radians(15.0))
    assert check.gaze_samples([(uncalibrated, frames)], SETTINGS) == [[pytest.approx((0.9 * tan40, 0.4 * tan15, 0.8))]]


def test_a_point_scores_its_error_and_jitter():
    target = (math.tan(math.radians(20.0)), 0.0)
    error, jitter = check.score_point(_on_target(target), target)
    assert error == pytest.approx(0.0, abs=1e-6) and jitter == pytest.approx(0.0, abs=1e-3)
    ahead = (0.0, math.tan(math.radians(10.0)))
    error, _ = check.score_point(_on_target(ahead, pitch_off_deg=2.0), ahead)
    assert error == pytest.approx(2.0, abs=1e-6)
    # Gaze alternating 1 deg either side of the target: no error, 1 deg of jitter.
    wobble = _on_target(ahead, n=5, pitch_off_deg=1.0) + _on_target(ahead, n=5, pitch_off_deg=-1.0)
    error, jitter = check.score_point(wobble, ahead)
    assert error == pytest.approx(0.0, abs=1e-6) and jitter == pytest.approx(1.0, abs=1e-3)
    # Blinks don't count, and too few samples is not tracked.
    assert check.score_point(_on_target(target, openness=0.1), target) is None
    assert check.score_point(_on_target(target, n=4), target) is None


def test_each_eye_is_scored_on_its_own():
    target = (0.0, math.tan(math.radians(10.0)))
    # The eyes sit 2 deg either side of the dot: steady, each 2 deg off.
    eyes = [_on_target(target, pitch_off_deg=2.0), _on_target(target, pitch_off_deg=-2.0)]
    error, jitter = check.score_dot(eyes, target)
    assert error == pytest.approx(2.0, abs=1e-6) and jitter == pytest.approx(0.0, abs=1e-3)
    # The worse eye decides, and an eye that lost the dot does not hide the other.
    assert check.score_dot([_on_target(target), _on_target(target, pitch_off_deg=3.0)], target)[0] == pytest.approx(3.0)
    assert check.score_dot([_on_target(target), []], target)[0] == pytest.approx(0.0, abs=1e-6)
    assert check.score_dot([[], _on_target(target, n=4)], target) is None


def test_only_eyes_with_a_gaze_fit_are_scored():
    def eye(eye_id, fitted=True):
        fit = ([1.0, 0.0, 0.0, 1.0, 0.0, 1.0], [0.0, 0.0]) if fitted else (None, None)
        return SimpleNamespace(eye_id=eye_id, _next_smartcal_w=fit[0], _next_smartcal_b=fit[1])

    left, right, raw = eye(EyeId.LEFT), eye(EyeId.RIGHT), eye(EyeId.RIGHT, fitted=False)
    assert check.scored_eyes([left, right], SETTINGS) == [left, right]
    assert check.scored_eyes([left, raw], SETTINGS) == [left]
    assert check.scored_eyes([raw], SETTINGS) == [raw]
    # The per-eye gaze modes fit the dominant eye and hand the fit to both.
    independent = SimpleNamespace(gui_NEXT_gaze_mode="independent", gui_NEXT_dominant_eye="right")
    assert check.scored_eyes([left, right], independent) == [right]


def test_a_direction_is_verified_out_to_its_first_miss():
    points = check.check_points()
    tangents = _tangents(points)
    samples = {}
    for i, (name, level, _, _) in enumerate(points):
        off = 0.0
        if name == "up" and level == 1.0:
            off = 5.0  # the edge reads 5 deg low
        if name == "left" and level == 0.5:
            off = 5.0  # a miss part way out ends the verified range there
        if name == "down" and level >= 0.75:
            continue  # the lids hide the pupil
        samples[i] = [_on_target(tangents[i], pitch_off_deg=off)]
    result = check.score(points, samples, GAZE_RANGE, SETTINGS)
    rays = {ray.name: ray for ray in result.rays}
    assert rays["up"].verified_deg == pytest.approx(math.degrees(math.atan(0.75 * math.tan(math.radians(15.0)))))
    assert rays["up"].shown_deg == pytest.approx(15.0)
    assert rays["left"].verified_deg == pytest.approx(math.degrees(math.atan(0.25 * math.tan(math.radians(40.0)))))
    assert rays["down"].verified_deg == pytest.approx(math.degrees(math.atan(0.5 * math.tan(math.radians(40.0)))))
    assert rays["right"].verified_deg == pytest.approx(40.0)
    assert result.tracked and result.limits == (40.0, 15.0, 40.0)


def _verified(offsets):
    """Verified angle per ray when each dot reads ``offsets(name, level)``
    degrees low."""
    points = check.check_points()
    tangents = _tangents(points)
    samples = {
        i: [_on_target(tangents[i], pitch_off_deg=offsets(name, level))] for i, (name, level, _, _) in enumerate(points)
    }
    result = check.score(points, samples, GAZE_RANGE, SETTINGS)
    return result, {ray.name: ray.verified_deg for ray in result.rays}


def test_a_less_accurate_setup_is_judged_against_its_own_centre():
    # 3 deg off everywhere: worse than a good insert, but just as good at the
    # edges as in the middle, so the whole range counts as usable.
    # 2x the 3 deg centre error would be 6 deg, but the limit never goes past
    # MAX_ERROR_DEG, so a frozen or badly calibrated gaze cannot pass everywhere.
    result, verified = _verified(lambda name, level: 3.0)
    assert result.max_error_deg == pytest.approx(check.MAX_ERROR_DEG, abs=0.1)
    assert verified["up"] == pytest.approx(15.0) and verified["down"] == pytest.approx(40.0)


def test_degrading_edges_fail_however_good_the_centre_is():
    # 0.5 deg off near the centre, 4 deg at the edge of the range.
    result, verified = _verified(lambda name, level: 4.0 if level == 1.0 else 0.5)
    assert result.max_error_deg == pytest.approx(check.MIN_ERROR_DEG)
    assert verified["right"] == pytest.approx(math.degrees(math.atan(0.75 * math.tan(math.radians(40.0)))))


def test_limits_fall_back_to_the_floors_without_a_tracked_centre():
    assert check.limits_from_centre([None, None]) == (check.MIN_ERROR_DEG, check.MIN_JITTER_DEG)
    assert check.limits_from_centre([(1.5, 0.4), (2.5, 0.2), None]) == pytest.approx((4.0, 0.6))


def test_the_report_lists_every_direction(english):
    points = check.check_points()
    tangents = _tangents(points)
    result = check.score(points, {i: [_on_target(t)] for i, t in enumerate(tangents)}, GAZE_RANGE, SETTINGS)
    assert log_report(result).splitlines() == [
        "Gaze range check",
        "Gaze stays within 2.0° of the dot out to:",
        "up 15° of 15°, down 40° of 40°, left 40° of 40°, right 40° of 40°",
        "up left 32° of 32°, up right 32° of 32°, down left 40° of 40°, down right 40° of 40°",
        "Your gaze limits are 40° sideways, 15° up and 40° down.",
    ]
    assert len(headset_report(result)) <= 400
    assert headset_report(None) == "The check stopped before it finished."
    assert "No tracked gaze" in headset_report(check.score(points, {}, GAZE_RANGE, SETTINGS))


@pytest.fixture
def english():
    import localization

    localization.init_localization("en")


class _Eye:
    """Looks at whichever dot the overlay was last told to show and feeds the
    raw gaze an uncalibrated model reads there to the trace."""

    def __init__(self, record):
        self.processor = SimpleNamespace(eye_id=EyeId.LEFT, _next_smartcal_w=None, _next_smartcal_b=None)
        self.record = record
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._feed, daemon=True)
        self._thread.start()

    def _feed(self):
        while not self._stop.is_set():
            try:
                dots = [line.split()[1:] for line in self.record.read_text().splitlines() if line.startswith("111 ")]
            except OSError:
                dots = []
            trace = getattr(self.processor, "_next_smartcal_trace", None)
            if dots and trace is not None:
                target = next_smartcal_dot_tangents(GAZE_RANGE, [tuple(map(float, dots[-1]))])[0]
                trace.append((time.monotonic(), *smartcal_tangents_to_gaze(*target, SETTINGS), 0.8, 0.5))
            time.sleep(0.002)

    def stop(self):
        self._stop.set()
        self._thread.join()


def test_the_check_runs_in_the_headset_and_reports(monkeypatch, tmp_path):
    record = interactive_overlay.install(monkeypatch, tmp_path, FULL_RANGE_LINE)()
    launched = []
    real_command = check.OverlaySession
    monkeypatch.setattr(check, "OverlaySession", lambda *args, **kw: launched.append(args) or real_command(*args, **kw))
    for module, name, value in (
        (check, "SUMMARY_S", 0.0),
        (next_smartcal, "READY_REST_S", 0.05),
        (next_smartcal, "REACTION_S", 0.0),
        (next_smartcal, "NEXT_SMARTCAL_CAPTURE_WINDOW_S", 0.04),
        (gaze_capture, "SETTLE_S", 0.03),
    ):
        monkeypatch.setattr(module, name, value)
    eye = _Eye(record)

    check.gaze_range_check_overlay([eye.processor], SETTINGS).wait(timeout=60)
    eye.stop()

    assert launched == [("interactive", *check.overlay_range_args())]
    commands = record.read_text().splitlines()
    assert commands[0].startswith("50 Look at the dot|")
    assert commands[1:4] == ["110", "111 0.0000 0.0000", "98"]
    assert commands[4:-3] == [f"111 {nx:.4f} {ny:.4f}" for _, _, nx, ny in check.check_points()]
    assert commands[-3] == "119"
    assert commands[-2].startswith("50 Gaze range check|Gaze stays within 2.0° of the dot out to:|up 15° of 15°")
    assert commands[-1] == "200"
    assert not var.overlay_active
    assert eye.processor._next_smartcal_trace is None
