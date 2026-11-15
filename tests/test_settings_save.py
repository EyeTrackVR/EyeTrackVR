"""Settings pages save what the user changed: values a widget already wrote into the
config for instant effect, and the valid fields of a page that also has an invalid one."""

from types import SimpleNamespace

from pydantic import field_validator

from settings.base_settings import BaseSettingsWidget
from settings.modules.base_module import BaseSettingsModule, BaseValidationModel


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
    saved = []
    settings = SimpleNamespace(port=9000, threshold=0.1)
    main_config = SimpleNamespace(settings=settings, update=lambda data, save=False: saved.append((data, save)))
    widget = BaseSettingsWidget(0, main_config, [_PortModule, _ThresholdModule])
    widget.frame = object()  # "built"
    monkeypatch.setattr(widget, "_collect_values", lambda: {"-PORT-": 0, "-THRESHOLD-": 0.7})
    widget.flush_pending_save()  # what closing the app does
    assert saved == [({"threshold": 0.7}, True)]


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_setting_changed_elsewhere_shows_in_the_widget_instead_of_being_written_back():
    listeners, saved = [], []
    settings = SimpleNamespace(port=9000, threshold=0.1)

    def update(data, save=False):
        for key, value in data.items():
            setattr(settings, key, value)
        saved.append(data)
        for listener in listeners:
            listener(data)

    main_config = SimpleNamespace(settings=settings, update=update, register_listener_callback=listeners.append)
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
