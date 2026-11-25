"""One EyeTrackVR per user (utils/single_instance.py): a second copy is refused while the
first runs, the OS frees the lock when the first exits, and a lock that can't be taken
never stops the app from starting."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from utils import single_instance

APP_DIR = Path(__file__).resolve().parents[1] / "eyetrackapp"
ACQUIRE = (
    "import sys; sys.path.insert(0, sys.argv[1]); from utils import single_instance; "
    "print(single_instance.acquire(sys.argv[2]), flush=True)"
)


@pytest.fixture(autouse=True)
def no_lock_held(monkeypatch):
    monkeypatch.setattr(single_instance, "_handle", None)
    yield
    single_instance.release()


def _start(lock, hold=False):
    code = ACQUIRE + ("; sys.stdin.read()" if hold else "")  # holds the lock until stdin closes
    return subprocess.Popen(
        [sys.executable, "-c", code, str(APP_DIR), str(lock)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )


def test_second_instance_is_refused_until_the_first_exits(tmp_path):
    lock = tmp_path / "eyetrackapp.lock"
    first = _start(lock, hold=True)
    try:
        assert first.stdout.readline().strip() == "True"
        second = _start(lock)
        assert second.communicate(timeout=30)[0].strip() == "False"
        assert single_instance.acquire(lock) is False  # this process too
    finally:
        first.kill()
        first.communicate()
    # The OS releases the lock with the process, even one that was killed.
    third = _start(lock)
    assert third.communicate(timeout=30)[0].strip() == "True"


def test_the_lock_is_kept_for_life_and_given_back_on_release(tmp_path):
    lock = tmp_path / "eyetrackapp.lock"
    assert single_instance.acquire(lock) is True
    assert single_instance.acquire(lock) is True  # asking again is not "another instance"
    assert _start(lock).communicate(timeout=30)[0].strip() == "False"
    single_instance.release()
    assert _start(lock).communicate(timeout=30)[0].strip() == "True"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a POSIX folder the user cannot write")
def test_a_lock_that_cannot_be_created_never_stops_the_app(tmp_path):
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    readonly.chmod(0o500)
    try:
        assert single_instance.acquire(readonly / "EyeTrackVR" / "eyetrackapp.lock") is True
    finally:
        readonly.chmod(0o700)


@pytest.mark.skipif(os.name == "nt", reason="the POSIX locations")
def test_the_lock_lives_in_the_users_runtime_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(single_instance.sys, "platform", "linux")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    assert single_instance._lock_path() == tmp_path / "run" / "EyeTrackVR" / "eyetrackapp.lock"
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert single_instance._lock_path() == tmp_path / "state" / "EyeTrackVR" / "eyetrackapp.lock"
