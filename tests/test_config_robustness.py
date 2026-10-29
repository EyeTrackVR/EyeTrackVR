import json
import logging
import threading
from unittest.mock import Mock

import pytest

import config
from config import EyeTrackConfig, EyeTrackSettingsConfig


@pytest.fixture
def cfg_paths(tmp_path, monkeypatch):
    main = tmp_path / "eyetrack_settings.json"
    backup = tmp_path / "eyetrack_settings.backup"
    monkeypatch.setattr(config, "CONFIG_FILE_NAME", str(main))
    monkeypatch.setattr(config, "BACKUP_CONFIG_FILE_NAME", str(backup))
    return main, backup


def _valid_config_text(**settings):
    cfg = EyeTrackConfig()
    for key, value in settings.items():
        setattr(cfg.settings, key, value)
    return json.dumps(cfg.model_dump(warnings=False))


# --- save() ------------------------------------------------------------------


def test_concurrent_saves_never_leave_invalid_json(cfg_paths):
    main, backup = cfg_paths
    cfg = EyeTrackConfig()
    cfg.save()
    errors = []
    start = threading.Barrier(8)

    def worker():
        start.wait()
        for _ in range(25):
            try:
                cfg.save()
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    for path in (main, backup):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
    assert not list(main.parent.glob("*.tmp"))


def test_corrupt_main_file_does_not_overwrite_good_backup(cfg_paths):
    main, backup = cfg_paths
    good = _valid_config_text(gui_osc_port=1234)
    backup.write_text(good, encoding="utf-8")
    main.write_text('{"settings": {', encoding="utf-8")

    EyeTrackConfig().save()

    assert backup.read_text(encoding="utf-8") == good
    assert isinstance(json.loads(main.read_text(encoding="utf-8")), dict)


def test_save_refreshes_backup_from_valid_main(cfg_paths):
    main, backup = cfg_paths
    previous = _valid_config_text(gui_osc_port=4321)
    main.write_text(previous, encoding="utf-8")

    EyeTrackConfig().save()

    assert backup.read_text(encoding="utf-8") == previous


def test_save_keeps_log_line(cfg_paths, caplog):
    with caplog.at_level(logging.INFO, logger="config"):
        EyeTrackConfig().save()
    assert "Config saved successfully" in caplog.text


# --- load() ------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [b"null", b"[]", b"42", b'"text"', b"\xff\xfe\x00garbage", b'{"settings": {'],
)
def test_load_falls_back_to_backup(cfg_paths, payload):
    main, backup = cfg_paths
    main.write_bytes(payload)
    backup.write_text(_valid_config_text(gui_osc_port=5555), encoding="utf-8")

    loaded = EyeTrackConfig.load()

    assert loaded.settings.gui_osc_port == 5555


@pytest.mark.parametrize("payload", [b"null", b"[]", b"\xff\xfe\x00garbage"])
def test_load_falls_back_to_defaults_when_backup_also_bad(cfg_paths, payload):
    main, backup = cfg_paths
    main.write_bytes(payload)
    backup.write_bytes(payload)

    loaded = EyeTrackConfig.load()

    assert loaded.settings == EyeTrackSettingsConfig()


def test_load_reads_utf8(cfg_paths):
    main, _backup = cfg_paths
    raw = json.loads(_valid_config_text())
    raw["right_eye"]["capture_source"] = "caméra-ü"
    main.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    loaded = EyeTrackConfig.load()

    assert loaded.right_eye.capture_source == "caméra-ü"


def test_save_round_trips_non_ascii(cfg_paths):
    cfg = EyeTrackConfig()
    cfg.right_eye.capture_source = "caméra-ü"
    cfg.save()
    assert EyeTrackConfig.load().right_eye.capture_source == "caméra-ü"


# --- reset hooks -------------------------------------------------------------


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_reset_hooks_restore_osc_mode_and_algorithm():
    from settings.BaseSettings import BaseSettingsWidget
    from settings.modules.OSCSettingsModule import OSCSettingsModule
    from settings.modules.TrackingAlgorithmModule import TrackingAlgorithmModule

    user = EyeTrackSettingsConfig(gui_vrc_native=True, gui_pyvrcft=False, gui_LEAP=True, gui_NEXT=False)
    defaults = EyeTrackSettingsConfig()

    osc = OSCSettingsModule(config=user, widget_id="t")
    osc.tk_vars = {getattr(osc, field): _Var(getattr(user, field)) for field in osc.validation_model.model_fields}
    osc.tk_vars[osc.gui_osc_output_mode] = _Var("native")

    algo = TrackingAlgorithmModule(config=user, widget_id="t")
    algo.tk_vars = {getattr(algo, field): _Var(getattr(user, field)) for field in algo.validation_model.model_fields}
    algo.selected_algo = _Var("leap")

    widget = Mock()
    widget.initialized_modules = [osc, algo]
    BaseSettingsWidget.reset_config(widget)

    osc_values = osc.get_values_map()
    assert osc_values[osc.gui_vrc_native] == defaults.gui_vrc_native
    assert osc_values[osc.gui_pyvrcft] == defaults.gui_pyvrcft
    assert osc_values[osc.gui_osc_vrcft_v2] == defaults.gui_osc_vrcft_v2

    algo_values = algo.get_values_map()
    assert algo_values[algo.gui_NEXT] == defaults.gui_NEXT
    assert algo_values[algo.gui_LEAP] == defaults.gui_LEAP

    saved = widget._update_and_save_config.call_args.args[0]
    assert saved["gui_vrc_native"] == defaults.gui_vrc_native
    assert saved["gui_LEAP"] == defaults.gui_LEAP


# --- OpenVR ------------------------------------------------------------------


def _openvr_module():
    from tests.test_openvr_service import _load_openvr_service_module

    return _load_openvr_service_module()


def _service_with_unwritable_manifest(module):
    service = module.OpenVRService()
    service.initialize = Mock(return_value=True)
    service.app = Mock()
    service.write_manifest = Mock(side_effect=PermissionError("read-only dir"))
    return service


def test_ensure_registered_survives_oserror():
    module = _openvr_module()
    service = _service_with_unwritable_manifest(module)
    service.autostart_enabled = True

    service.ensure_registered()  # must not raise


def test_on_config_update_survives_oserror(monkeypatch):
    module = _openvr_module()
    service = _service_with_unwritable_manifest(module)
    service.window = Mock()
    shown = Mock()
    monkeypatch.setattr(module, "_show_warning", shown)

    service.on_config_update({"gui_openvr_autostart": True})

    assert service.autostart_enabled is False
    service.window.set_openvr_autostart.assert_called_once_with(False)
    shown.assert_called_once()


def test_show_warning_reuses_existing_root(monkeypatch):
    module = _openvr_module()
    root = object()
    monkeypatch.setattr(module.tk, "_default_root", root, raising=False)
    new_root = Mock(side_effect=AssertionError("second Tk root created"))
    monkeypatch.setattr(module.tk, "Tk", new_root)
    showwarning = Mock()
    monkeypatch.setattr(module.messagebox, "showwarning", showwarning)

    module._show_warning("title", "msg")

    assert showwarning.call_args.kwargs["parent"] is root
    new_root.assert_not_called()
