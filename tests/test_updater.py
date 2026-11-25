"""In-app updates (utils/updater.py, update_dialog.py): which release is offered on the
stable and pre-release channels, that an installer is only kept when it is the file
GitHub lists for that release, that it waits while SteamVR holds the install folder,
and what each update check shows."""

import hashlib
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import update_dialog
from utils import updater

INSTALLER = b"MZ installer bytes" * 1000
BASE = updater.DOWNLOAD_PREFIX


def release(name, prerelease=False, draft=False, asset=True, **extra):
    tag = name.replace(" ", "-")
    file_name = f"EyeTrackVR-Setup-{tag.split('-', 1)[1]}.exe"
    assets = [
        {"name": "SHA256SUMS.txt", "browser_download_url": f"{BASE}{tag}/SHA256SUMS.txt", "size": 212},
        {"name": "EyeTrackVR-linux.tar.gz", "browser_download_url": f"{BASE}{tag}/EyeTrackVR-linux.tar.gz", "size": 9},
    ]
    if asset:
        assets.append(
            {
                "name": file_name,
                "browser_download_url": f"{BASE}{tag}/{file_name}",
                "size": len(INSTALLER),
                "digest": "sha256:" + hashlib.sha256(INSTALLER).hexdigest(),
            }
        )
    return dict(
        {"name": name, "tag_name": tag, "prerelease": prerelease, "draft": draft, "assets": assets},
        html_url=f"https://github.com/EyeTrackVR/EyeTrackVR/releases/tag/{tag}",
        body="What's new",
        **extra,
    )


RELEASES = [
    release("EyeTrackApp 0.3.0 BETA 12", prerelease=True),
    release("EyeTrackApp 0.3.0 BETA 13", prerelease=True, draft=True),  # not published yet
    release("EyeTrackApp 0.3.0 BETA 11", prerelease=True),
    release("EyeTrackApp 0.2.5"),
    {"name": "nightly", "assets": []},  # a name that is not a version
    {"name": "v2.0 BETA 14", "tag_name": "v2.0-BETA-14", "prerelease": True, "assets": []},  # the earlier app
    "junk",
]


def test_stable_channel_ignores_prereleases():
    assert updater.pick_update(RELEASES, "EyeTrackApp 0.2.4", prereleases=False).version == "EyeTrackApp 0.2.5"
    assert updater.pick_update(RELEASES, "EyeTrackApp 0.2.5", prereleases=False) is None


def test_beta_channel_offers_the_newest_published_prerelease():
    update = updater.pick_update(RELEASES, "EyeTrackApp 0.3.0 BETA 10", prereleases=True)
    assert (update.version, update.prerelease, update.notes) == ("EyeTrackApp 0.3.0 BETA 12", True, "What's new")
    assert update.installer_name == "EyeTrackVR-Setup-0.3.0-BETA-12.exe"
    assert update.installer_sha256 == hashlib.sha256(INSTALLER).hexdigest()
    assert updater.pick_update(RELEASES, "EyeTrackApp 0.3.0 BETA 12", prereleases=True) is None


def test_someone_on_a_prerelease_keeps_getting_them():
    assert updater.include_prereleases("EyeTrackApp 0.3.0 BETA 11", opted_in=False)
    assert not updater.include_prereleases("EyeTrackApp 0.3.0", opted_in=False)
    assert updater.include_prereleases("EyeTrackApp 0.3.0", opted_in=True)
    update = updater.check("EyeTrackApp 0.3.0 BETA 11", False, fetch=lambda: RELEASES)
    assert update.version == "EyeTrackApp 0.3.0 BETA 12"
    # The final release is newer than its betas, on either channel.
    final = RELEASES + [release("EyeTrackApp 0.3.0")]
    assert updater.check("EyeTrackApp 0.3.0 BETA 12", False, fetch=lambda: final).version == "EyeTrackApp 0.3.0"


def test_skipped_version_is_not_offered_again_but_a_newer_one_is():
    assert updater.pick_update(RELEASES, "EyeTrackApp 0.3.0 BETA 10", True, skipped="EyeTrackApp 0.3.0 BETA 12") is None
    update = updater.pick_update(RELEASES, "EyeTrackApp 0.3.0 BETA 10", True, skipped="EyeTrackApp 0.3.0 BETA 11")
    assert update.version == "EyeTrackApp 0.3.0 BETA 12"


def test_installer_must_come_from_this_repository_with_a_checksum():
    elsewhere = release("EyeTrackApp 0.4.0")
    elsewhere["assets"][-1]["browser_download_url"] = "https://example.com/EyeTrackVR-Setup-0.4.0.exe"
    assert updater.pick_update([elsewhere], "EyeTrackApp 0.3.0", False).installer_url == ""
    no_digest = release("EyeTrackApp 0.4.0")
    del no_digest["assets"][-1]["digest"]
    update = updater.pick_update([no_digest], "EyeTrackApp 0.3.0", False)
    assert update.installer_url == "" and not update.installable  # the release page is offered instead
    assert updater.pick_update([release("EyeTrackApp 0.4.0", asset=False)], "EyeTrackApp 0.3.0", False).page_url


def _update():
    return updater.pick_update([release("EyeTrackApp 0.4.0")], "EyeTrackApp 0.3.0", False)


def _chunks(data, size=4096):
    return lambda url: (data[i : i + size] for i in range(0, len(data), size))


def test_download_keeps_only_a_file_that_matches_the_release(tmp_path):
    (tmp_path / "EyeTrackVR-Setup-old.exe").write_bytes(b"earlier download")
    seen = []
    path = updater.download_installer(
        _update(), tmp_path, lambda d, t: seen.append((d, t)), open_stream=_chunks(INSTALLER)
    )
    assert path.read_bytes() == INSTALLER and [p.name for p in tmp_path.iterdir()] == [path.name]
    assert seen[-1] == (len(INSTALLER), len(INSTALLER))

    for bad in (INSTALLER[:-1] + b"!", INSTALLER[:-10], INSTALLER + b"extra"):
        with pytest.raises(updater.UpdateError):
            updater.download_installer(_update(), tmp_path, open_stream=_chunks(bad))
        assert list(tmp_path.iterdir()) == []  # nothing left to run by mistake


def test_download_can_be_cancelled_and_network_errors_are_reported(tmp_path):
    cancel = threading.Event()

    def progress(done, total):
        cancel.set()

    with pytest.raises(updater.Cancelled):
        updater.download_installer(_update(), tmp_path, progress, cancel, open_stream=_chunks(INSTALLER))
    assert list(tmp_path.iterdir()) == []

    def offline(url):
        raise OSError("no network")

    with pytest.raises(updater.UpdateError):
        updater.download_installer(_update(), tmp_path, open_stream=offline)


def test_download_refuses_an_update_without_a_verifiable_installer(tmp_path):
    update = updater.Update("EyeTrackApp 0.4.0", False, "page", installer_url="https://example.com/x.exe")
    with pytest.raises(updater.UpdateError):
        updater.download_installer(update, tmp_path, open_stream=_chunks(INSTALLER))


def test_real_release_list_shape_from_github_parses():
    # Trimmed copy of a real entry: names use spaces, tags dashes, digest is "sha256:<hex>".
    real = {
        "tag_name": "EyeTrackApp-0.3.0-BETA-9",
        "name": "EyeTrackApp 0.3.0 BETA 9",
        "prerelease": True,
        "draft": False,
        "html_url": "https://github.com/EyeTrackVR/EyeTrackVR/releases/tag/EyeTrackApp-0.3.0-BETA-9",
        "assets": [
            {
                "name": "EyeTrackVR-Setup-0.3.0-BETA-9.exe",
                "size": 209654934,
                "digest": "sha256:878d1520cbd8aec303a0e6a42ade995a470410b4f7f86466bdffa5a5a7c7df25",
                "browser_download_url": BASE + "EyeTrackApp-0.3.0-BETA-9/EyeTrackVR-Setup-0.3.0-BETA-9.exe",
            }
        ],
    }
    update = updater.pick_update([real], "EyeTrackApp 0.3.0 BETA 8", prereleases=True)
    assert update.installer_size == 209654934 and len(update.installer_sha256) == 64


def test_a_hotfix_release_is_offered():
    update = updater.pick_update(
        [release("EyeTrackApp 0.3.0 BETA 5.1", prerelease=True)], "EyeTrackApp 0.3.0 BETA 5", True
    )
    assert update is not None and update.version == "EyeTrackApp 0.3.0 BETA 5.1"


@pytest.mark.parametrize("payload", [{"message": "API rate limit exceeded"}, "text", None])
def test_a_release_list_that_is_not_a_list_is_an_error(monkeypatch, payload):
    import requests

    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(requests, "get", lambda *_a, **_kw: response)
    with pytest.raises(ValueError):
        updater.check("EyeTrackApp 0.3.0", False)


# ------------------------------------------------------------------ SteamVR holds the install folder


def test_steamvr_check(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    assert updater.steamvr_running() is False  # Windows only

    # openvr_service imports pyopenvr, which a Mac test run may not have.
    openvr_service = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "ovr.openvr_service", openvr_service)
    monkeypatch.setattr(updater.sys, "platform", "win32")
    seen = []
    openvr_service._windows_process_running = lambda name: seen.append(name) or True
    assert updater.steamvr_running() is True
    assert seen == ["vrserver.exe"]

    def broken(_name):
        raise OSError("no snapshot")

    openvr_service._windows_process_running = broken
    assert updater.steamvr_running() is False  # a failed check never blocks updating


# ------------------------------------------------------------------ the update window


@pytest.fixture
def window(monkeypatch):
    """An UpdateWindow without Tk: its widgets record what they were set to."""
    update = updater.Update(version="EyeTrackApp 0.3.0 BETA 9", prerelease=True, page_url="")
    window = update_dialog.UpdateWindow(root=Mock(), update=update, config=Mock(), quit_app=Mock())
    window.window = Mock()
    for widget in ("status", "progress", "install_btn", "skip_btn", "later_btn"):
        setattr(window, widget, Mock())
    monkeypatch.setattr(update_dialog, "tr", lambda key, **_kw: key)
    return window


@pytest.fixture
def installer(tmp_path):
    path = tmp_path / "EyeTrackVR-Setup-0.3.0.exe"
    path.write_bytes(b"verified")
    return path


def test_update_waits_for_steamvr_and_retries_without_downloading_again(monkeypatch, window, installer):
    launched = []
    monkeypatch.setattr(updater, "launch_installer", launched.append)
    monkeypatch.setattr(updater, "download_installer", Mock(side_effect=AssertionError("downloaded again")))

    monkeypatch.setattr(updater, "steamvr_running", lambda: True)
    window._busy = True
    window._run_installer(installer)
    assert launched == []
    window.quit_app.assert_not_called()
    window.status.configure.assert_called_with(text="update.close_steamvr")
    assert window._busy is False  # Update now works again

    monkeypatch.setattr(updater, "steamvr_running", lambda: False)
    window._install()
    assert launched == [Path(installer)]
    window.quit_app.assert_called_once()


def test_a_declined_installer_keeps_the_app_and_the_download(monkeypatch, window, installer):
    def declined(_path):
        raise OSError("The operation was canceled by the user")  # UAC "No"

    monkeypatch.setattr(updater, "steamvr_running", lambda: False)
    monkeypatch.setattr(updater, "launch_installer", declined)
    window._busy = True
    window._run_installer(installer)
    window.quit_app.assert_not_called()
    window.status.configure.assert_called_with(text="update.download_failed")
    assert window._busy is False and window._downloaded == installer


def test_skip_remembers_the_version(window):
    window._skip()
    window.config.update.assert_called_once_with({"gui_update_skip_version": "EyeTrackApp 0.3.0 BETA 9"}, save=True)
    assert window.window is None and window._cancel.is_set()


# ------------------------------------------------------------------ the checks that open it


class _Inline:
    def __init__(self, target, **_):
        self.target = target

    def start(self):
        self.target()


@pytest.mark.parametrize(
    "manual, result, shown",
    [
        (False, None, []),  # startup, nothing new: stays quiet
        (False, OSError("offline"), []),  # startup, no network: stays quiet
        (True, None, ["info:update.up_to_date"]),
        (True, OSError("offline"), ["warning:update.check_failed"]),
        (False, "update", ["window"]),
        (True, "update", ["window"]),
    ],
)
def test_what_a_check_shows(monkeypatch, manual, result, shown):
    seen, asked = [], []
    root = SimpleNamespace(after=lambda _ms, fn: fn())
    settings = SimpleNamespace(gui_update_check=True, gui_update_beta=False, gui_update_skip_version="0.3.0 BETA 9")
    monkeypatch.setattr(update_dialog, "_app", {})
    update_dialog.install(root, SimpleNamespace(settings=settings), "EyeTrackApp 0.3.0 BETA 8", quit_app=Mock())
    monkeypatch.setattr(update_dialog.threading, "Thread", _Inline)
    monkeypatch.setattr(update_dialog, "tr", lambda key, **_kw: key)

    def check(version, prereleases, skipped):
        asked.append(skipped)
        if isinstance(result, Exception):
            raise result
        return _update() if result else None

    monkeypatch.setattr(updater, "check", check)
    monkeypatch.setattr(update_dialog.ui_dialog, "show_info", lambda _r, _t, text: seen.append(f"info:{text}"))
    monkeypatch.setattr(update_dialog.ui_dialog, "show_warning", lambda _r, _t, text: seen.append(f"warning:{text}"))
    monkeypatch.setattr(update_dialog, "UpdateWindow", lambda *a: SimpleNamespace(show=lambda: seen.append("window")))

    (update_dialog.check_now if manual else update_dialog.check_at_startup)()
    assert seen == shown
    # Asking again shows a version the user skipped; the startup check does not.
    assert asked == ["" if manual else "0.3.0 BETA 9"]


def test_no_startup_check_when_it_is_turned_off(monkeypatch):
    monkeypatch.setattr(update_dialog, "_app", {})
    settings = SimpleNamespace(gui_update_check=False)
    update_dialog.install(Mock(), SimpleNamespace(settings=settings), "EyeTrackApp 0.3.0", quit_app=Mock())
    asked = []
    monkeypatch.setattr(updater, "check", lambda *a: asked.append(a))
    monkeypatch.setattr(update_dialog.threading, "Thread", _Inline)
    update_dialog.check_at_startup()
    assert asked == []
