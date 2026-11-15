"""In-app updates (utils/updater.py): which release is offered on the stable and
pre-release channels, and that an installer is only kept when it is the file GitHub
lists for that release."""

import hashlib
import threading

import pytest

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
