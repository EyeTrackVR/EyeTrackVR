"""Where EyeTrackVR keeps the user's files (utils/user_data.py): an installed Windows
build in %LOCALAPPDATA%, with a one-time copy out of the install folder; a source
checkout or portable copy beside its existing settings; Linux in the XDG config dir.
The rules are plain path functions, exercised with temp folders standing in for the
install dir, the working directory and %LOCALAPPDATA%."""

import os

import pytest

from utils import user_data


@pytest.fixture
def layout(tmp_path):
    install = tmp_path / "install"
    install.mkdir()
    local = tmp_path / "local"
    return install, local, local / "EyeTrackVR"


def _old_files(install):
    (install / "eyetrack_settings.json").write_text('{"settings": {"gui_osc_port": 1}}')
    (install / "eyetrack_settings.backup").write_text('{"backup": true}')
    (install / "RANSAC_BLINK_LEFT.cfg").write_text("ransac")
    (install / "IBO_RIGHT.png").write_bytes(b"ibo")
    (install / "EBPD_LEFT.png").write_bytes(b"ebpd")


def test_installed_build_copies_its_files_out_of_the_install_folder(layout):
    install, local, new = layout
    _old_files(install)
    (install / "unins000.exe").write_bytes(b"")

    chosen = user_data._resolve_windows(True, str(install), str(install), str(local), environ={})

    assert chosen == str(new)
    for name in ("eyetrack_settings.json", "eyetrack_settings.backup", "RANSAC_BLINK_LEFT.cfg", "IBO_RIGHT.png"):
        assert (new / name).read_bytes() == (install / name).read_bytes()
    assert (new / "EBPD_LEFT.png").read_bytes() == b"ebpd"
    assert (install / "eyetrack_settings.json").exists()  # originals are kept
    assert not list(new.glob("*.migrating"))


def test_migration_never_overwrites_the_new_folder(layout):
    install, local, new = layout
    _old_files(install)
    new.mkdir(parents=True)
    (new / "eyetrack_settings.json").write_text("current")
    (new / "IBO_RIGHT.png").write_bytes(b"current")

    # Under Program Files counts as installed even without the uninstaller.
    program_files = {"ProgramFiles": str(install.parent)}
    chosen = user_data._resolve_windows(True, str(install), str(install), str(local), environ=program_files)

    assert chosen == str(new)
    assert (new / "eyetrack_settings.json").read_text() == "current"
    assert (new / "IBO_RIGHT.png").read_bytes() == b"current"


@pytest.mark.parametrize("frozen", [True, False], ids=["portable copy", "source checkout"])
def test_portable_copy_keeps_settings_in_its_folder(layout, frozen):
    install, local, new = layout
    _old_files(install)  # no uninstaller, not under Program Files

    assert user_data._resolve_windows(frozen, str(install), str(install), str(local), environ={}) == ""
    assert not new.exists()


def test_concurrent_start_keeps_the_first_copy(layout, monkeypatch):
    """A second instance finishing its copy later must not replace the first's."""
    install, local, new = layout
    _old_files(install)
    real_link = os.link

    def other_instance_wins(src, dst):
        with open(dst, "w") as f:
            f.write("first instance")
        return real_link(src, dst)

    monkeypatch.setattr(user_data.os, "link", other_instance_wins)
    new.mkdir(parents=True)

    assert user_data.migrate(str(new), [str(install)]) == str(new)
    assert (new / "eyetrack_settings.json").read_text() == "first instance"
    assert not list(new.glob("*.migrating"))


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a POSIX folder the user cannot write")
def test_failed_copy_keeps_using_the_old_folder(layout):
    install, _local, new = layout
    _old_files(install)
    new.mkdir(parents=True)
    new.chmod(0o500)
    try:
        assert user_data.migrate(str(new), [str(install)]) == str(install)
    finally:
        new.chmod(0o700)
    assert not (new / "eyetrack_settings.json").exists()


def test_copy_from_the_working_directory_when_started_from_there(layout, tmp_path):
    install, local, new = layout
    (install / "unins000.exe").write_bytes(b"")
    cwd = tmp_path / "shortcut_start_in"
    cwd.mkdir()
    _old_files(cwd)  # an older version wrote its settings where it was started from

    assert user_data._resolve_windows(True, str(install), str(cwd), str(local), environ={}) == str(new)
    assert (new / "eyetrack_settings.json").read_text() == (cwd / "eyetrack_settings.json").read_text()


@pytest.mark.parametrize("frozen", [False, True])
def test_a_copy_without_settings_beside_it_uses_the_data_home(layout, frozen):
    install, local, new = layout  # no settings in the folder it runs from, no uninstaller
    assert user_data._resolve_windows(frozen, str(install), str(install), str(local), environ={}) == str(new)
    assert new.is_dir() and list(new.iterdir()) == []


def test_nothing_to_migrate_leaves_the_new_folder_alone(layout):
    install, _local, new = layout
    new.mkdir(parents=True)
    assert user_data.migrate(str(new), [str(install)]) == str(new)
    assert list(new.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="the POSIX rules")
def test_linux_keeps_settings_in_the_xdg_config_dir(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(user_data.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert user_data._resolve_user_data_dir() == str(tmp_path / "config" / "EyeTrackVR")
    assert (tmp_path / "config" / "EyeTrackVR").is_dir()
    # A settings file in the working directory (a source checkout) wins.
    (tmp_path / user_data.SETTINGS_NAME).write_text("{}", encoding="utf-8")
    assert user_data._resolve_user_data_dir() == ""
