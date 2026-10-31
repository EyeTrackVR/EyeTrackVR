from types import SimpleNamespace
from unittest import mock

import pytest

from eye import EyeId
from osc.PyVRCFTSender import PyVRCFTSender
from osc.VRChatOSCSender import VRChatOSCSender, brow_expression
from osc_calibrate_filter import next_smartcal_transform_is_sane
from pyvrcft import UnifiedTrackingData
from pyvrcft.expressions import compute_outputs


@pytest.mark.parametrize(
    "brow,expected",
    [(0.0, -1.0), (0.25, -0.5), (0.5, 0.0), (0.75, 0.5), (1.0, 1.0), (-0.2, -1.0), (1.3, 1.0)],
)
def test_brow_expression_centres_tracker_neutral(brow, expected):
    # Tracker brow is 0..1 with 0.5 = rest; VRCFT BrowExpression is -1..+1.
    assert brow_expression(brow) == pytest.approx(expected)


@pytest.mark.parametrize(
    "brow,expr,up,down",
    [(0.0, -1.0, 0.0, 1.0), (0.5, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.0), (0.25, -0.5, 0.0, 0.5)],
)
def test_pyvrcft_brow_reaches_both_ends(brow, expr, up, down):
    sender = PyVRCFTSender.__new__(PyVRCFTSender)
    sender.data = UnifiedTrackingData()
    sender.client = mock.Mock()
    config = SimpleNamespace(eye_display_id=None)
    with mock.patch.object(VRChatOSCSender, "get_is_single_eye", return_value=False):
        sender.output_eyebrow_info(EyeId.LEFT, brow, config)
        sender.output_eyebrow_info(EyeId.RIGHT, brow, config)
    params, _ = compute_outputs(sender.data)
    assert params["v2/BrowExpression"] == pytest.approx(expr)
    assert params["v2/BrowUp"] == pytest.approx(up)
    assert params["v2/BrowDown"] == pytest.approx(down)


def test_v2_mode_sends_centred_brow_expression():
    client = mock.Mock()
    config = SimpleNamespace(eye_display_id=None)
    sender = VRChatOSCSender()
    with mock.patch.object(VRChatOSCSender, "get_is_single_eye", return_value=False):
        sender.output_eyebrow_info(EyeId.LEFT, 0.5, client, config)
    client.send_message.assert_called_once_with("/avatar/parameters/v2/BrowExpressionLeft", 0.0)


def test_smartcal_accepts_under_driven_vertical_gain():
    # Held-out BSB users need ~2.5x on gaze_y; that fit used to be rejected.
    assert next_smartcal_transform_is_sane([1.28, 0.0, 0.0, 2.56], [0.0, 0.05])
    assert next_smartcal_transform_is_sane([1.5, 0.0, 0.0, 1.5], [0.05, 0.05])


@pytest.mark.parametrize(
    "w,b",
    [([10.0, 0.0, 0.0, 10.0], [0.0, 0.0]), ([1.0, 0.0, 0.0, -1.0], [0.0, 0.0]), ([2.0, 0.0, 0.0, 2.0], [0.0, 0.5])],
)
def test_smartcal_still_rejects_degenerate_fits(w, b):
    assert not next_smartcal_transform_is_sane(w, b)
