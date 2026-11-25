"""Camera discovery (camera_enum): the UVC list cache, Linux V4L2 node
filtering, resolving a saved uvc:Name@Address source to a cv2 index, and the
serial Scan probe."""

import os
import sys
import types

import pytest

import camera_enum
from camera_enum import format_uvc_named_source, parse_uvc_named_source, resolve_uvc_address_to_index

# ── uvc:Name@Address sources ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "source, name, address",
    [
        ("uvc:Eye Cam@dev-1", "Eye Cam", "dev-1"),
        # DirectShow names can contain '@': the address is after the last one.
        ("uvc:Cam @ Home@\\\\?\\usb#vid_1234", "Cam @ Home", "\\\\?\\usb#vid_1234"),
        ("uvc:Nameless", "Nameless", ""),
    ],
)
def test_named_sources_round_trip(source, name, address):
    assert camera_enum.is_uvc_named_source(source)
    assert parse_uvc_named_source(source) == (name, address)
    if address:
        assert format_uvc_named_source(name, address) == source


def test_plain_sources_are_not_named_uvc_sources():
    assert not camera_enum.is_uvc_named_source("http://etvr.local/")
    assert not camera_enum.is_uvc_named_source(0)


CAMS = [
    {"index": 0, "name": "Eye Cam", "address": "dev-left"},
    {"index": 1, "name": "Eye Cam", "address": "dev-right"},
    {"index": 2, "name": "Webcam", "address": "dev-web"},
]


@pytest.fixture
def claims(monkeypatch):
    """A claim registry of this test's own."""
    monkeypatch.setattr(camera_enum, "_claimed", {})


def test_a_saved_address_finds_its_camera_after_a_reorder(claims):
    reordered = [dict(c, index=i) for i, c in enumerate(reversed(CAMS))]
    assert resolve_uvc_address_to_index("Eye Cam", "dev-right", reordered) == (1, "dev-right")


def test_an_index_address_is_trusted_only_while_that_index_exists(claims):
    assert resolve_uvc_address_to_index("Webcam", "index:2", CAMS) == (2, "index:2")
    # Gone: falls back to the name instead of opening whatever has index 7.
    assert resolve_uvc_address_to_index("Webcam", "index:7", CAMS) == (2, "dev-web")


def test_a_replugged_camera_is_found_by_name_at_its_new_address(claims):
    assert resolve_uvc_address_to_index("Webcam", "dev-web-old", CAMS) == (2, "dev-web")


def test_an_unplugged_eye_does_not_take_its_siblings_camera(claims):
    only_right = [CAMS[1]]
    camera_enum.claim_uvc_address(1001, "dev-right")  # the right eye's thread
    assert resolve_uvc_address_to_index("Eye Cam", "dev-left", only_right, owner_id=1002) is None
    # Once the sibling lets go, the name match is free to use.
    camera_enum.release_uvc_claim(1001)
    assert resolve_uvc_address_to_index("Eye Cam", "dev-left", only_right, owner_id=1002) == (1, "dev-right")


def test_same_named_cameras_route_to_the_one_no_sibling_claimed(claims):
    moved = [dict(CAMS[0], address="dev-left-new"), CAMS[1]]
    # Ambiguous by name alone...
    assert resolve_uvc_address_to_index("Eye Cam", "dev-left", moved, owner_id=1002) is None
    # ...until the other eye's claim leaves exactly one candidate.
    camera_enum.claim_uvc_address(1001, "dev-right")
    assert resolve_uvc_address_to_index("Eye Cam", "dev-left", moved, owner_id=1002) == (0, "dev-left-new")


# ── list cache ───────────────────────────────────────────────────────────────


def test_forced_invalidate_bypasses_the_rate_limit(monkeypatch):
    calls = []

    def enumerate_now():
        calls.append(1)
        return [{"index": len(calls), "name": "cam", "address": "index:0"}]

    monkeypatch.setattr(camera_enum, "_list_uvc_cameras_uncached", enumerate_now)
    monkeypatch.setattr(camera_enum, "_uvc_list_cache", None)
    monkeypatch.setattr(camera_enum, "_uvc_list_cache_last_invalidated", -999.0)

    camera_enum.list_uvc_cameras()
    camera_enum.invalidate_uvc_camera_cache()  # e.g. after a resolve miss
    camera_enum.list_uvc_cameras()
    assert len(calls) == 2

    camera_enum.invalidate_uvc_camera_cache()  # rate-limited: cache kept
    camera_enum.list_uvc_cameras()
    assert len(calls) == 2

    camera_enum.invalidate_uvc_camera_cache(force=True)  # Scan button
    assert camera_enum.list_uvc_cameras()[0]["index"] == 3


def test_cameras_without_os_metadata_get_index_addresses(monkeypatch):
    monkeypatch.setattr(camera_enum, "_platform_metadata", lambda: [])
    monkeypatch.setattr(camera_enum, "_probe_cv2_indices", lambda: [0, 3])
    assert camera_enum._list_uvc_cameras_uncached() == [
        {"index": 0, "name": "Camera 0", "address": "index:0"},
        {"index": 3, "name": "Camera 3", "address": "index:3"},
    ]


# ── Linux V4L2 nodes ─────────────────────────────────────────────────────────


def _fake_linux_dev(monkeypatch, tmp_path, entries, sysfs):
    sysroot = tmp_path / "sysfs"
    sysroot.mkdir()
    for dev, attrs in sysfs.items():
        d = sysroot / dev
        d.mkdir()
        for k, v in attrs.items():
            (d / k).write_text(v)
    monkeypatch.setattr(camera_enum, "_V4L2_SYSFS_DIR", str(sysroot))

    real_listdir = os.listdir
    real_isdir = os.path.isdir
    monkeypatch.setattr(
        camera_enum.os,
        "listdir",
        lambda p: list(entries) if p == "/dev" else real_listdir(p),
    )
    monkeypatch.setattr(
        camera_enum.os.path,
        "isdir",
        lambda p: False if p == "/dev/v4l/by-id" else real_isdir(p),
    )


def test_linux_listing_drops_uvc_metadata_nodes(monkeypatch, tmp_path):
    _fake_linux_dev(
        monkeypatch,
        tmp_path,
        ["null", "video0", "video1", "video2", "video3", "video4"],
        {
            "video0": {"index": "0\n", "name": "Cam\n"},
            "video1": {"index": "1\n", "name": "Cam\n"},  # metadata node
            "video2": {"index": "0\n", "name": "Cam\n"},
            "video3": {"index": "1\n", "name": "Cam\n"},  # metadata node
            # video4: no sysfs entry at all -> kept
        },
    )
    assert camera_enum._linux_camera_metadata() == [
        (0, "Cam", "/dev/video0"),
        (2, "Cam", "/dev/video2"),
        (4, "Camera", "/dev/video4"),
    ]

    monkeypatch.setattr(camera_enum.sys, "platform", "linux")
    cams = camera_enum._list_uvc_cameras_uncached()
    # The cv2 index is the node number, not the list position.
    assert [c["index"] for c in cams] == [0, 2, 4]


def test_linux_listing_keeps_nodes_when_sysfs_missing(monkeypatch, tmp_path):
    _fake_linux_dev(monkeypatch, tmp_path, ["video0", "video1"], {})
    monkeypatch.setattr(camera_enum, "_V4L2_SYSFS_DIR", str(tmp_path / "nope"))
    assert [i for i, _, _ in camera_enum._linux_camera_metadata()] == [0, 1]


# ── serial Scan ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "platform, a, b, same",
    [
        ("win32", "com5", "COM5", True),
        ("win32", "COM5", "COM6", False),
        ("linux", "/dev/ttyUSB0", "/dev/ttyUSB0/", True),
        ("linux", "", "  ", True),
    ],
)
def test_serial_port_keys_compare_the_way_the_os_names_ports(monkeypatch, platform, a, b, same):
    monkeypatch.setattr(camera_enum.sys, "platform", platform)
    assert (camera_enum.serial_port_key(a) == camera_enum.serial_port_key(b)) is same


def test_serial_scan_skips_configured_ports(monkeypatch):
    list_ports = pytest.importorskip("serial.tools.list_ports")
    live = "COM5" if sys.platform.startswith("win") else "/dev/ttyUSB0"
    spare = "COM7" if sys.platform.startswith("win") else "/dev/ttyUSB1"
    ports = [
        types.SimpleNamespace(device=live, description="ETVR", vid=0x303A),
        types.SimpleNamespace(device=spare, description="ETVR", vid=0x303A),
    ]
    monkeypatch.setattr(list_ports, "comports", lambda: ports)
    probed = []

    def fake_probe(device, baud, timeout_s):
        probed.append(device)
        return True

    monkeypatch.setattr(camera_enum, "_probe_serial_for_jpeg", fake_probe)
    found = camera_enum.discover_etvr_serial_cameras(
        timeout_s=0.01,
        skip_devices=(live, 0, None, ""),
    )
    assert probed == [spare]
    assert found == [(f"ETVR ({spare})", spare)]


def test_serial_scan_never_opens_bluetooth_ports_and_labels_what_streams(monkeypatch):
    list_ports = pytest.importorskip("serial.tools.list_ports")
    ports = [
        types.SimpleNamespace(device="/dev/cu.Bluetooth-Incoming-Port", description="n/a", vid=None),
        types.SimpleNamespace(device="/dev/cu.usbmodem2", description="/dev/cu.usbmodem2", vid=0x303A),
        types.SimpleNamespace(device="/dev/cu.usbmodem1", description="n/a", vid=0x303A),
        types.SimpleNamespace(device="/dev/cu.usbserial", description="CP2102", vid=0x10C4),
    ]
    monkeypatch.setattr(list_ports, "comports", lambda: ports)
    probed = []

    def fake_probe(device, baud, timeout_s):
        probed.append(device)
        return device != "/dev/cu.usbserial"  # not streaming JPEG

    monkeypatch.setattr(camera_enum, "_probe_serial_for_jpeg", fake_probe)

    found = camera_enum.discover_etvr_serial_cameras(timeout_s=0.01)

    assert "/dev/cu.Bluetooth-Incoming-Port" not in probed and len(probed) == 3
    # Sorted by device; a description that only repeats the path is not a label.
    assert found == [("/dev/cu.usbmodem1", "/dev/cu.usbmodem1"), ("/dev/cu.usbmodem2", "/dev/cu.usbmodem2")]


class _ProbeSerial:
    opened = {}
    chunks = []

    def __init__(self, **kw):
        _ProbeSerial.opened = kw

    def reset_input_buffer(self):
        pass

    def read(self, _n):
        return _ProbeSerial.chunks.pop(0) if _ProbeSerial.chunks else b""

    def close(self):
        pass


def test_serial_probe_opens_exclusively(monkeypatch):
    serial = pytest.importorskip("serial")
    monkeypatch.setattr(serial, "Serial", _ProbeSerial)
    monkeypatch.setattr(_ProbeSerial, "chunks", [b"\x00\xff\xd8\xff"])
    assert camera_enum._probe_serial_for_jpeg("COM9", 115200, 0.5)
    assert _ProbeSerial.opened.get("exclusive") is True


def test_serial_probe_finds_a_jpeg_start_split_across_reads(monkeypatch):
    serial = pytest.importorskip("serial")
    monkeypatch.setattr(serial, "Serial", _ProbeSerial)
    monkeypatch.setattr(_ProbeSerial, "chunks", [b"boot noise \xff", b"\xd8\xff\xe0"])
    assert camera_enum._probe_serial_for_jpeg("COM9", 115200, 0.5)


def test_serial_probe_treats_a_busy_or_silent_port_as_no_camera(monkeypatch):
    serial = pytest.importorskip("serial")

    def busy(**kw):
        raise serial.SerialException("access denied")

    monkeypatch.setattr(serial, "Serial", busy)
    assert not camera_enum._probe_serial_for_jpeg("COM9", 115200, 0.5)

    monkeypatch.setattr(serial, "Serial", _ProbeSerial)
    monkeypatch.setattr(_ProbeSerial, "chunks", [])
    assert not camera_enum._probe_serial_for_jpeg("COM9", 115200, 0.05)
