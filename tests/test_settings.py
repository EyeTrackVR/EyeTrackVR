"""Settings pages (settings/base_settings.py, settings/modules/): what they save and when,
settings changed elsewhere showing in the widgets, Reset to defaults, and the field
validation that keeps values the tracking can't use out of the config."""

import math
import time
from types import SimpleNamespace

import pytest
from pydantic import field_validator

from config import EyeTrackSettingsConfig
from settings.base_settings import BaseSettingsWidget
from settings.modules.advanced_osc_settings_module import AdvancedOSCSettingsModule
from settings.modules.base_module import BaseSettingsModule, BaseValidationModel
from settings.modules.blink_algo_module import BlinkAlgoSettingsModule
from settings.modules.general_settings_module import GeneralSettingsModule
from settings.modules.vrcft_settings_module import VRCFTSettingsModule
from tests.tk_support import tk_module_root, tk_root  # noqa: F401

# ------------------------------------------------------------------ a page of two small modules


class _PortModel(BaseValidationModel):
    port: int

    @field_validator("port")
    @classmethod
    def in_range(cls, value):
        if not 0 < value < 65536:
            raise ValueError("port out of range")
        return value


class _PortModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config, widget_id)
        self.validation_model = _PortModel
        self.port = "-PORT-"


class _ThresholdModel(BaseValidationModel):
    threshold: float


class _ThresholdModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config, widget_id)
        self.validation_model = _ThresholdModel
        self.threshold = "-THRESHOLD-"


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _main_config(listeners=None, **values):
    """EyeTrackConfig's update() and listeners over a plain settings object; ``saved``
    lists each update with its save flag."""
    settings = SimpleNamespace(**values)
    saved = []

    def update(data, save=False):
        for key, value in data.items():
            setattr(settings, key, value)
        saved.append((data, save))
        for listener in listeners or []:
            listener(data)

    config = SimpleNamespace(settings=settings, update=update, saved=saved)
    if listeners is not None:
        config.register_listener_callback = listeners.append
    return config


# ------------------------------------------------------------------ saving


def test_value_written_live_into_the_config_is_still_reported_for_saving():
    config = SimpleNamespace(threshold=0.1)
    module = _ThresholdModule(config, 0)
    assert module.validate({"-THRESHOLD-": 0.1}).changes == {}
    config.threshold = 0.4  # a slider's trace applies it at once...
    module.live_changes["threshold"] = 0.4  # ...and says so
    assert module.validate({"-THRESHOLD-": 0.4}).changes == {"threshold": 0.4}
    assert module.validate({"-THRESHOLD-": 0.4}).changes == {}  # reported once


def test_live_change_survives_a_failed_validation():
    module = _PortModule(SimpleNamespace(port=9000), 0)
    module.live_changes["port"] = 9001
    assert module.validate({"-PORT-": 0}).errors
    assert module.live_changes == {"port": 9001}


def test_invalid_field_does_not_hold_back_the_other_modules(monkeypatch):
    main_config = _main_config(port=9000, threshold=0.1)
    widget = BaseSettingsWidget(0, main_config, [_PortModule, _ThresholdModule])
    widget.frame = object()  # "built"
    monkeypatch.setattr(widget, "_collect_values", lambda: {"-PORT-": 0, "-THRESHOLD-": 0.7})
    widget.flush_pending_save()  # what closing the app does
    assert main_config.saved == [({"threshold": 0.7}, True)]


def test_an_edit_saves_while_the_page_keeps_ticking(tk_root):  # noqa: F811
    import tkinter as tk

    main_config = _main_config(threshold=0.1)
    widget = BaseSettingsWidget(0, main_config, [_ThresholdModule])
    widget.frame = tk.Frame(tk_root)
    widget.initialized_modules[0].tk_vars["-THRESHOLD-"] = tk.StringVar(master=tk_root, value="0.7")
    # The main loop: render_tick every frame, the page open the whole time.
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and not main_config.saved:
        widget.render_tick()
        tk_root.update()
        time.sleep(0.03)
    assert [data for data, _save in main_config.saved] == [{"threshold": 0.7}]
    assert main_config.settings.threshold == 0.7


def test_setting_changed_elsewhere_shows_in_the_widget_instead_of_being_written_back():
    listeners = []
    main_config = _main_config(listeners, port=9000, threshold=0.1)
    widget = BaseSettingsWidget(0, main_config, [_PortModule, _ThresholdModule])
    widget.frame = object()
    port_module = widget.initialized_modules[0]
    port_module.tk_vars["-PORT-"] = _Var(9000)
    widget._pending_validated = {"port": 9000}  # a save of the old value was already queued

    main_config.update({"port": 9100})  # e.g. an OSC command, or another panel
    assert port_module.tk_vars["-PORT-"].get() == 9100
    assert widget._pending_validated == {}
    assert port_module.validate({"-PORT-": 9100, "-THRESHOLD-": 0.1}).changes == {}

    widget._update_and_save_config({"port": 9200})  # its own save is not echoed back into the widget
    assert port_module.tk_vars["-PORT-"].get() == 9100


def test_language_box_follows_a_language_set_elsewhere(tk_root, monkeypatch):  # noqa: F811
    from tkinter import ttk

    import settings.modules.general_settings_module as gsm

    monkeypatch.setattr(
        gsm,
        "available_languages",
        lambda: [{"code": "en", "native_name": "English"}, {"code": "de", "native_name": "Deutsch"}],
    )
    module = gsm.GeneralSettingsModule(config=SimpleNamespace(gui_language="de"), widget_id=0)
    module._build_language_row(ttk.Frame(tk_root), 0)
    assert module._lang_display_var.get() == "Deutsch"
    # What Reset to defaults and the wizard's language step (via the config listener) do.
    module.apply_external_changes({"gui_language": "en"})
    assert module._lang_display_var.get() == "English"


# ------------------------------------------------------------------ Reset to defaults


def test_reset_restores_the_defaults_and_saves_them():
    from settings.modules.osc_settings_module import OSCSettingsModule
    from settings.modules.tracking_algorithm_module import TrackingAlgorithmModule

    user = EyeTrackSettingsConfig(
        gui_vrc_native=True, gui_pyvrcft=False, gui_LEAP=True, gui_NEXT=False, gui_osc_vrcft_v2=True
    )
    defaults = EyeTrackSettingsConfig()
    main_config = _main_config(**user.model_dump())
    widget = BaseSettingsWidget(0, main_config, [OSCSettingsModule, TrackingAlgorithmModule])
    osc, algo = widget.initialized_modules
    for module in (osc, algo):
        module.tk_vars = {getattr(module, f): _Var(getattr(user, f)) for f in module.validation_model.model_fields}
    # The radio groups the reset hooks put back (or the old choice is written back next tick).
    osc.tk_vars[osc.gui_osc_output_mode] = _Var("native")
    algo.selected_algo = _Var("leap")

    widget.reset_config()

    for module in (osc, algo):
        values = module.get_values_map()
        for field in module.validation_model.model_fields:
            assert values[getattr(module, field)] == getattr(defaults, field), field
    ((saved, save),) = main_config.saved
    assert save is True
    assert saved["gui_vrc_native"] == defaults.gui_vrc_native and saved["gui_LEAP"] == defaults.gui_LEAP
    assert saved["gui_NEXT"] == defaults.gui_NEXT and saved["gui_osc_vrcft_v2"] == defaults.gui_osc_vrcft_v2


# ------------------------------------------------------------------ validation of the real fields


def _values(module, **typed):
    """What the page's widgets hold: the config's values, with ``typed`` in some fields."""
    values = {getattr(module, f): getattr(module.config, f) for f in module.validation_model.model_fields}
    values.update({getattr(module, field): value for field, value in typed.items()})
    return values


FLOAT_FIELDS = [
    (GeneralSettingsModule, "gui_eye_dominant_diff_thresh"),
    (VRCFTSettingsModule, "gui_OutputMultiplier"),
    (BlinkAlgoSettingsModule, "leap_lid_close_threshold_left"),
    (BlinkAlgoSettingsModule, "leap_lid_widen_threshold_right"),
    (BlinkAlgoSettingsModule, "leap_lid_min_calibration_span"),
]
NOT_A_NUMBER = ["nan", "NaN", "inf", "-inf", "Infinity", " inf ", float("nan"), float("inf"), "", "abc"]


@pytest.mark.parametrize("typed", NOT_A_NUMBER)
@pytest.mark.parametrize("module_class, field", FLOAT_FIELDS)
def test_a_float_field_rejects_what_is_not_a_finite_number(module_class, field, typed):
    # NaN never equals itself: accepted, the page would see a change on every tick and
    # the value would reach the tracking maths and the saved config.
    module = module_class(EyeTrackSettingsConfig(), 0)
    result = module.validate(_values(module, **{field: typed}))
    assert result.changes is None and [e["loc"] for e in result.errors] == [(field,)]
    assert module.validate(_values(module)).changes == {}  # nothing left "changing"


@pytest.mark.parametrize("module_class, field", FLOAT_FIELDS)
def test_a_float_field_still_takes_a_number(module_class, field):
    module = module_class(EyeTrackSettingsConfig(), 0)
    assert module.validate(_values(module, **{field: " 0.25 "})).changes == {field: 0.25}


def test_a_typed_lid_threshold_never_puts_nan_in_the_config(tk_root):  # noqa: F811
    from tkinter import ttk

    config = EyeTrackSettingsConfig()
    module = BlinkAlgoSettingsModule(config, 0)
    module.build(ttk.Frame(tk_root))
    var = module.tk_vars[module.leap_lid_close_threshold_left]
    var.set("0.25")  # applied as it is typed
    assert config.leap_lid_close_threshold_left == 0.25
    assert module.live_changes == {"leap_lid_close_threshold_left": 0.25}
    for typed in ("nan", "inf", "-Infinity"):
        var.set(typed)
        assert config.leap_lid_close_threshold_left == 0.25
        assert module.live_changes == {"leap_lid_close_threshold_left": 0.25}
    assert math.isfinite(config.leap_lid_close_threshold_left)


@pytest.mark.parametrize("port, ok", [(0, False), (1, True), (8889, True), (65535, True), (65536, False), (-1, False)])
@pytest.mark.parametrize(
    "module_class, field",
    [
        (VRCFTSettingsModule, "gui_VRCFTModulePort"),
        (AdvancedOSCSettingsModule, "gui_osc_port"),
        (AdvancedOSCSettingsModule, "gui_osc_receiver_port"),
    ],
)
def test_a_port_field_takes_1_to_65535(module_class, field, port, ok):
    module = module_class(EyeTrackSettingsConfig(), 0)
    result = module.validate(_values(module, **{field: port}))
    if ok:
        assert not result.errors and result.changes in ({}, {field: port})
    else:
        assert result.changes is None and [e["loc"] for e in result.errors] == [(field,)]
