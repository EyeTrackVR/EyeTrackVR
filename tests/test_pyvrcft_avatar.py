"""pyVRCFT avatar parameter lookup (pyvrcft/avatar.py): VRChat's OSCQuery /avatar
tree (preferred) and the avatar config JSON VRChat writes to disk (fallback)."""

import json
import os
from pathlib import Path

import pytest

from pyvrcft import avatar as pyavatar
from pyvrcft.avatar import AvatarParameter
from tests.osc_helpers import collect_stray_garbage, LOCALHOST, avatar_tree, free_udp_port, vrchat_oscquery


@pytest.fixture(autouse=True, scope="module")
def _main_thread_gc():
    collect_stray_garbage()


@pytest.fixture
def vrchat_osc_dir(tmp_path, monkeypatch):
    """VRChat's OSC folder under a fake home, at this platform's location."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if os.name == "nt":
        osc_dir = tmp_path / "AppData/LocalLow/VRChat/VRChat/OSC"
    else:  # Steam/Proton prefix
        osc_dir = tmp_path / ".local/share/Steam/steamapps/compatdata/438100/pfx/drive_c/users/steamuser"
        osc_dir = osc_dir / "AppData/LocalLow/VRChat/VRChat/OSC"
    osc_dir.mkdir(parents=True)
    return osc_dir


def _write_config(osc_dir, user, avatar_id, text):
    path = osc_dir / user / "Avatars" / f"{avatar_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig")  # VRChat writes a BOM


def _config(avatar_id, name="Fox", parameters=()):
    return json.dumps({"id": avatar_id, "name": name, "parameters": list(parameters)})


def test_disk_config_keeps_typed_input_parameters_only(vrchat_osc_dir):
    _write_config(
        vrchat_osc_dir,
        "usr_1",
        "avtr_1",
        _config(
            "avtr_1",
            parameters=[
                {"name": "JawOpen", "input": {"address": "/avatar/parameters/FT/v2/JawOpen", "type": "Float"}},
                {"name": "EyeLid1", "input": {"address": "/avatar/parameters/v2/EyeLid1", "type": "Bool"}},
                {"name": "Outfit", "input": {"address": "/avatar/parameters/Outfit", "type": "Int"}},
                {"name": "ReadOnly", "output": {"address": "/avatar/parameters/ReadOnly", "type": "Float"}},
                {"name": "Weird", "input": {"address": "/avatar/parameters/Weird", "type": "Vector3"}},
            ],
        ),
    )
    info = pyavatar.load_avatar_config("avtr_1")
    assert (info.id, info.name) == ("avtr_1", "Fox")
    assert info.full_face_tracking is None  # the disk config does not say
    assert info.parameters == [
        AvatarParameter("JawOpen", "/avatar/parameters/FT/v2/JawOpen", float),
        AvatarParameter("EyeLid1", "/avatar/parameters/v2/EyeLid1", bool),
        AvatarParameter("Outfit", "/avatar/parameters/Outfit", int),
    ]
    assert pyavatar.load_avatar_name("avtr_1") == "Fox"


def test_malformed_or_mismatched_configs_are_skipped(vrchat_osc_dir):
    _write_config(vrchat_osc_dir, "usr_a", "avtr_1", '{"id": "avtr_1", "parameters": [')  # truncated write
    _write_config(vrchat_osc_dir, "usr_b", "avtr_1", _config("avtr_other"))  # renamed file
    assert pyavatar.load_avatar_config("avtr_1") is None
    _write_config(vrchat_osc_dir, "usr_c", "avtr_1", _config("avtr_1", name="Good"))
    assert pyavatar.load_avatar_config("avtr_1").name == "Good"
    assert pyavatar.load_avatar_config("avtr_missing") is None
    assert pyavatar.load_avatar_name("avtr_missing") == ""


def test_no_vrchat_folder_means_no_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert pyavatar.vrchat_osc_directories() == []
    assert pyavatar.load_avatar_config("avtr_1") is None


@pytest.mark.parametrize("full_face", [True, False, None])
def test_oscquery_tree_gives_id_parameters_and_full_face_flag(vrchat_osc_dir, full_face):
    _write_config(vrchat_osc_dir, "usr_1", "avtr_x", _config("avtr_x", name="From disk"))
    params = {"FT/v2/JawOpen": "f", "v2/EyeLid1": "T", "Outfit": "i", "Name": "s", "Odd": "r", "NoType": ""}
    with vrchat_oscquery(avatar_tree("avtr_x", params, full_face)) as server:
        info = pyavatar.fetch_avatar_oscquery(LOCALHOST, server.server_address[1])
    assert server.requests == ["/avatar"]
    assert (info.id, info.name) == ("avtr_x", "From disk")  # OSCQuery has no name; the disk config does
    assert info.full_face_tracking is full_face
    assert sorted(info.parameters, key=lambda p: p.name) == [
        AvatarParameter("EyeLid1", "/avatar/parameters/v2/EyeLid1", bool),
        AvatarParameter("JawOpen", "/avatar/parameters/FT/v2/JawOpen", float),
        AvatarParameter("Name", "/avatar/parameters/Name", str),
        AvatarParameter("Outfit", "/avatar/parameters/Outfit", int),
    ]


@pytest.mark.parametrize("body", ["{not json", None], ids=["malformed-json", "http-404"])
def test_bad_oscquery_answer_is_no_avatar(body):
    with vrchat_oscquery(body) as server:
        port = server.server_address[1]
        assert pyavatar.fetch_avatar_oscquery(LOCALHOST, port) is None
        assert pyavatar.fetch_avatar_id_oscquery(LOCALHOST, port) is None


def test_vrchat_not_listening_is_no_avatar():
    port = free_udp_port()  # nothing listens on this TCP port either, in practice
    assert pyavatar.fetch_avatar_oscquery(LOCALHOST, port, timeout=1.0) is None
    assert pyavatar.fetch_avatar_id_oscquery(LOCALHOST, port) is None


@pytest.mark.parametrize(
    "tree, expected",
    [
        (avatar_tree("avtr_x"), "avtr_x"),
        ({"CONTENTS": {"change": {"VALUE": []}}}, ""),  # VRChat reports no avatar
        ({"CONTENTS": {"change": {"VALUE": [3]}}}, ""),
        ([], ""),
    ],
)
def test_avatar_id_poll(tree, expected):
    with vrchat_oscquery(tree) as server:
        assert pyavatar.fetch_avatar_id_oscquery(LOCALHOST, server.server_address[1]) == expected
