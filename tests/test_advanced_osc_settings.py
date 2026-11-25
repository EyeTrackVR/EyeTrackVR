"""Advanced OSC settings panel: rejects endpoints the OSC sender could not use."""

import pydantic
import pytest

from settings.modules.advanced_osc_settings_module import AdvancedOSCValidationModel


def _adv_model(**overrides):
    values = dict(
        gui_osc_port="9000",
        gui_osc_address="127.0.0.1",
        gui_osc_receiver_port="9001",
        gui_osc_recenter_address="/avatar/parameters/etvr_recenter",
        gui_osc_recalibrate_address="/avatar/parameters/etvr_recalibrate",
    )
    values.update(overrides)
    return AdvancedOSCValidationModel(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"gui_osc_port": "70000"},
        {"gui_osc_port": "0"},
        {"gui_osc_receiver_port": "-1"},
        {"gui_osc_port": "abc"},
        {"gui_osc_address": ""},
        {"gui_osc_address": "bad host"},
    ],
)
def test_advanced_osc_settings_reject_invalid(overrides):
    with pytest.raises(pydantic.ValidationError):
        _adv_model(**overrides)


def test_advanced_osc_settings_accept_valid():
    m = _adv_model(gui_osc_address=" localhost ", gui_osc_port="65535")
    assert m.gui_osc_address == "localhost"
    assert m.gui_osc_port == 65535
