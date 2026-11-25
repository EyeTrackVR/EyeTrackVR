"""Log files (utils/logging_utils.py): the per-frame tracking CSV that a sentinel file
switches on and off, and the pruning that keeps the last few sessions' logs."""

import csv
import os
import time

import pytest

from utils import logging_utils
from utils.logging_utils import TrackingLogger


@pytest.fixture
def folders(monkeypatch, tmp_path):
    """Separate install, user data and log folders; no logger left from another test."""
    app_root, data, logs = tmp_path / "install", tmp_path / "data", tmp_path / "logs"
    for folder in (app_root, data, logs):
        folder.mkdir()
    monkeypatch.setattr(logging_utils, "_app_root", lambda: app_root)
    monkeypatch.setattr(logging_utils, "user_data_path", lambda name: str(data / name))
    monkeypatch.setattr(logging_utils, "log_directory", lambda: logs)
    monkeypatch.setattr(TrackingLogger, "_instance", None)
    monkeypatch.setattr(TrackingLogger, "_next_check", 0.0)
    yield app_root, data, logs
    if TrackingLogger._instance is not None:
        TrackingLogger._instance._file.close()


def _check_now():
    TrackingLogger._next_check = 0.0  # the once-a-second disk check is due
    return TrackingLogger.get()


@pytest.mark.parametrize("where", ["install", "data"])
def test_the_sentinel_switches_the_tracking_csv_on_and_off(folders, where):
    app_root, data, logs = folders
    assert _check_now() is None
    sentinel = (app_root if where == "install" else data) / TrackingLogger.SENTINEL
    sentinel.touch()
    logger = _check_now()
    assert logger is not None and _check_now() is logger  # one file per switch-on
    logger.record(1.5, "L", 10.0, 20.0, 0.1, -0.2, 0.15, -0.25, True, 3, 0.5, 0.01, 0.2, "R")

    sentinel.unlink()
    assert _check_now() is None
    (csv_file,) = logs.glob("tracking-*.csv")
    with open(csv_file, newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))
    assert rows[0] == TrackingLogger.COLUMNS
    assert rows[1] == [
        "1.5000",
        "L",
        "10.00",
        "20.00",
        "0.1000",
        "-0.2000",
        "0.1500",
        "-0.2500",
        "1",
        "3",
        "0.500",
        "0.0100",
        "0.2000",
        "R",
    ]


def test_the_sentinel_is_checked_at_most_once_a_second(folders):
    _app_root, data, _logs = folders
    assert TrackingLogger.get() is None
    (data / TrackingLogger.SENTINEL).touch()
    assert TrackingLogger.get() is None  # per-frame calls don't touch the disk
    assert _check_now() is not None


def test_only_the_newest_sessions_logs_are_kept(tmp_path):
    now = time.time()
    names = [f"{logging_utils.LOG_NAME_PREFIX}-2026010{i}-000000.log" for i in range(5)]
    for age, name in enumerate(reversed(names)):  # names[-1] is the newest
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        os.utime(path, (now - age * 60, now - age * 60))
    (tmp_path / f"{names[0]}.1").write_text("rotated", encoding="utf-8")  # the oldest session's rollover
    (tmp_path / "tracking-20260101-000000.csv").write_text("csv", encoding="utf-8")  # not a session log

    logging_utils._prune_old_logs(tmp_path)

    kept = sorted(p.name for p in tmp_path.iterdir())
    assert kept == sorted(names[-logging_utils.LOG_RETENTION_COUNT :] + ["tracking-20260101-000000.csv"])
