"""The settings file (config.py): saves that never leave a broken file, loads that fall
back to the backup or keep every valid field, the migrations that carry old settings
forward, and how a typed camera address is stored."""

import json
import logging
import threading

import pytest

import config
from config import (
    CURRENT_CONFIG_VERSION,
    EyeId,
    EyeTrackCameraConfig,
    EyeTrackConfig,
    EyeTrackSettingsConfig,
    _migrate_config_dict,
)


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
    # main() saves right after load(): what the user had survives as .corrupt.
    assert (main.parent / "eyetrack_settings.corrupt").read_bytes() == payload


_DEFAULT_PORT = EyeTrackSettingsConfig().gui_osc_port


def _set_path(raw, path, value):
    for key in path[:-1]:
        raw = raw[key]
    raw[path[-1]] = value


@pytest.mark.parametrize(
    "path, value, salvaged",
    [
        (("settings", "gui_osc_port"), "abc", lambda c: c.settings.gui_osc_port == _DEFAULT_PORT),
        (("settings", "gui_NEXT_calib_lids_brows"), None, lambda c: c.settings.gui_NEXT_calib_lids_brows is True),
        (("eye_display_id",), 99, lambda c: c.eye_display_id == EyeTrackConfig().eye_display_id),
        (("left_eye", "calibration_points"), [["x", 1]], lambda c: c.left_eye.calibration_points == []),
        # Several errors on one field (one per item) still drop only that field.
        (("right_eye", "calibration_points_3d"), [["x", "y"]], lambda c: c.right_eye.calibration_points_3d == []),
        (("left_eye", "capture_source"), [1], lambda c: c.left_eye.capture_source is None),
        # A broken sub-model (not a dict at all) takes that sub-model's defaults.
        (("settings",), "garbage", lambda c: c.settings == EyeTrackSettingsConfig()),
    ],
)
def test_one_invalid_field_keeps_the_rest_of_the_config(cfg_paths, path, value, salvaged, caplog):
    main, backup = cfg_paths
    raw = json.loads(_valid_config_text(gui_osc_port=4242))
    raw["right_eye"]["capture_source"] = "http://cam-right"
    raw["right_eye"]["calibration_points"] = [[0.1, 0.2], [0.3, None]]
    _set_path(raw, path, value)
    original = json.dumps(raw).encode()
    main.write_bytes(original)
    backup.write_text(_valid_config_text(gui_osc_port=5555), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="config"):
        loaded = EyeTrackConfig.load()

    assert loaded.right_eye.capture_source == "http://cam-right"
    assert loaded.right_eye.calibration_points == [[0.1, 0.2], [0.3, None]]
    assert salvaged(loaded)
    if path not in (("settings",), ("settings", "gui_osc_port")):
        assert loaded.settings.gui_osc_port == 4242  # the main file, not the backup's 5555
    assert ".".join(path) in caplog.text
    assert (main.parent / "eyetrack_settings.corrupt").read_bytes() == original


def test_clean_load_keeps_no_corrupt_copy(cfg_paths):
    main, _backup = cfg_paths
    main.write_text(_valid_config_text(), encoding="utf-8")
    EyeTrackConfig.load()
    assert not (main.parent / "eyetrack_settings.corrupt").exists()


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


def test_an_invalid_legacy_lid_threshold_falls_back_without_losing_the_rest(cfg_paths, caplog):
    # Before per-eye thresholds there was one; a validator copies it to both eyes on load.
    main, _backup = cfg_paths
    raw = json.loads(_valid_config_text(gui_osc_port=4242))
    del raw["settings"]["leap_lid_close_threshold_left"]
    raw["settings"]["leap_lid_close_threshold"] = "abc"
    raw["right_eye"]["capture_source"] = "http://cam-right"
    main.write_text(json.dumps(raw), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="config"):
        loaded = EyeTrackConfig.load()

    defaults = EyeTrackSettingsConfig()
    assert loaded.settings.leap_lid_close_threshold_left == defaults.leap_lid_close_threshold_left
    assert loaded.settings.gui_osc_port == 4242 and loaded.right_eye.capture_source == "http://cam-right"
    assert "settings.leap_lid_close_threshold" in caplog.text


# --- migrations ----------------------------------------------------------------

V = CURRENT_CONFIG_VERSION
FIT = {"calib_axes": [1.0, 2.0], "calib_evecs": [[1.0, 0.0], [0.0, 1.0]], "calib_XOFF": 3.0}


@pytest.mark.parametrize(
    "stored, expected",
    [
        pytest.param(
            {
                "left_eye": {
                    "leap_calibrated": True,
                    "leap_calibration_percentile_90": 0.8,
                    "leap_calibration_percentile_2": 0.1,
                }
            },
            {
                "version": V,
                "left_eye": {
                    "leap_calibrated": False,
                    "leap_calibration_percentile_90": 0,
                    "leap_calibration_percentile_2": 0,
                    "leap_lid_metric_version": 0,  # leap.py recalibrates on the next frame
                    "next_classic_calibration_active": False,
                },
            },
            id="v1: lid calibration made with the old metric is reset",
        ),
        pytest.param(
            {"version": "garbage", "bsb2e": {"leap_calibrated": True}},
            {
                "version": V,
                "bsb2e": {
                    "leap_calibrated": False,
                    "leap_calibration_percentile_90": 0,
                    "leap_calibration_percentile_2": 0,
                    "leap_lid_metric_version": 0,
                    "next_classic_calibration_active": False,
                },
            },
            id="unreadable version counts as v1",
        ),
        pytest.param(
            {"version": 2, "settings": {"gui_NEXT_calibration": True}, "left_eye": dict(FIT), "right_eye": {}},
            {
                "version": V,
                "settings": {},
                "left_eye": dict(FIT, next_classic_calibration_active=True),
                "right_eye": {"next_classic_calibration_active": False},  # no fit to keep
            },
            id="v2: an opted-in NEXT calibration keeps its fit",
        ),
        pytest.param(
            {"version": 2, "settings": {}, "left_eye": dict(FIT)},
            {"version": V, "settings": {}, "left_eye": dict(FIT, next_classic_calibration_active=False)},
            id="v2: a classic tracker's fit is not a NEXT calibration",
        ),
        pytest.param(
            {"version": 3, "settings": {"gui_NEXT_BSB": True, "gui_NEXT": False}},
            {"version": V, "settings": {"gui_NEXT_BSB": False, "gui_NEXT": True}},
            id="v3: NEXT BSB becomes NEXT",
        ),
        pytest.param(
            {"version": 3, "settings": {"gui_NEXT_BSB": False, "gui_NEXT": False, "gui_LEAP": True}},
            {"version": V, "settings": {"gui_NEXT_BSB": False, "gui_NEXT": False, "gui_LEAP": True}},
            id="v3: other trackers stay",
        ),
        pytest.param(
            {"version": 4, "settings": {"gui_NEXT_calibration": False, "gui_NEXT": True}},
            {"version": V, "settings": {"gui_NEXT": True}},
            id="v4: the legacy NEXT ellipse switch is dropped",
        ),
        pytest.param(
            {"version": 5, "settings": {"gui_model_variant": "BSB LITE"}},
            {"version": V, "settings": {"gui_model_variant": "BSB", "gui_model_size": "LITE"}},
            id="v5: headset and model size split",
        ),
        pytest.param(
            {"version": 5, "settings": {"gui_model_variant": "TOBII"}},
            {"version": V, "settings": {"gui_model_variant": "PSVR"}},
            id="v5: TOBII folds into PSVR",
        ),
        pytest.param(
            {"version": 5, "settings": {"gui_model_variant": "TOBII LITE"}},
            {"version": V, "settings": {"gui_model_variant": "PSVR", "gui_model_size": "LITE"}},
            id="v5: TOBII LITE is PSVR at size LITE",
        ),
        pytest.param(
            {"version": 6, "settings": {"gui_osc_oscquery": False}},
            {"version": V, "settings": {"gui_osc_oscquery": True}},
            id="v6: automatic receive port becomes the default",
        ),
        pytest.param(
            {
                "version": V,
                "settings": {"gui_osc_oscquery": False, "gui_model_variant": "BSB LITE", "gui_NEXT_BSB": True},
            },
            {
                "version": V,
                "settings": {"gui_osc_oscquery": False, "gui_model_variant": "BSB LITE", "gui_NEXT_BSB": True},
            },
            id="current: a choice made since is never migrated again",
        ),
    ],
)
def test_migration(stored, expected):
    assert _migrate_config_dict(json.loads(json.dumps(stored))) == expected


def test_a_root_that_is_not_an_object_is_left_to_the_loader():
    assert _migrate_config_dict([1, 2]) == [1, 2]


def test_load_migrates_an_old_file(cfg_paths):
    main, _backup = cfg_paths
    raw = json.loads(_valid_config_text())
    raw["version"] = 5
    raw["settings"]["gui_model_variant"] = "BSB LITE"
    main.write_text(json.dumps(raw), encoding="utf-8")
    loaded = EyeTrackConfig.load()
    assert (loaded.version, loaded.settings.gui_model_variant, loaded.settings.gui_model_size) == (V, "BSB", "LITE")


# --- camera addresses ------------------------------------------------------------


@pytest.mark.parametrize(
    "typed, stored",
    [
        ("", None),
        (None, None),
        ("0", 0),  # UVC index
        (" 2 ", 2),
        (3, 3),
        ("COM5", "COM5"),
        ("/dev/ttyUSB0", "/dev/ttyUSB0"),
        ("http://192.168.1.20:81/", "http://192.168.1.20:81/"),
        ("clip.mp4", "clip.mp4"),
        ("192.168.1.20", "http://192.168.1.20/"),  # a bare host becomes the camera's URL
        ("openiristracker.local", "http://openiristracker.local/"),
        ("cam1", "cam1"),  # too short for a host name
    ],
)
def test_a_typed_camera_address_is_stored_as_the_camera_needs_it(typed, stored):
    camera = EyeTrackCameraConfig()
    camera.update_capture_source(typed)
    assert camera.capture_source == stored


@pytest.mark.parametrize("source", [0, "uvc:USB Camera@\\\\?\\usb#1"], ids=["UVC index 0", "UVC by name"])
def test_a_camera_chosen_in_the_camera_widget_is_kept(source):
    cfg = EyeTrackConfig()
    cfg.update_eye_model_config(EyeId.LEFT, {"capture_source": source}, should_save=False, should_notify=False)
    assert cfg.left_eye.capture_source == source


def test_one_camera_cannot_feed_both_eyes():
    cfg = EyeTrackConfig()
    seen = []
    cfg.register_listener_callback(seen.append)
    assert cfg.update_eye_model_config(EyeId.LEFT, {"capture_source": "COM5"}, should_save=False)
    assert cfg.update_eye_model_config(EyeId.RIGHT, {"capture_source": "COM5"}, should_save=False) is False
    assert (cfg.left_eye.capture_source, cfg.right_eye.capture_source) == ("COM5", None)
    assert seen == [{"capture_source": "COM5"}]  # the refused change reached no listener
