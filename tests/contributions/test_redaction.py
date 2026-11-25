"""What a bug report's logs lose before they are encrypted (contributions/bundles.redact):
home folders, credentials, addresses and keys go; timestamps, ratios and the rest of
the line stay."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eyetrackapp"))
from contributions.bundles import redact

KEPT = [
    "2026-11-24 15:56:01,123 INFO started",
    "at 15:56:01.500 the camera",
    "aspect 4:3:2",
    "frame 10:20:30:40",
    "version 1.2.3",  # three parts; a four-part one is taken for an IPv4 address, on purpose
]


@pytest.mark.parametrize("text", KEPT)
def test_times_ratios_and_short_versions_are_kept(text):
    assert redact(text) == text


@pytest.mark.parametrize(
    "text, expected",
    [
        # IPv6, alone and next to colons
        ("peer 2001:0db8:85a3:0000:0000:8a2e:0370:7334 up", "peer <IP> up"),
        ("peer 2001:db8::1 up", "peer <IP> up"),
        ("peer ::1 up", "peer <IP> up"),
        ("peer fe80::1%eth0 up", "peer <IP> up"),
        ("peer ::ffff:192.168.1.5 up", "peer <IP> up"),  # v4-mapped goes as a whole
        ("peer 1:2:3:4:5:6:7:8 up", "peer <IP> up"),
        ("ip:2001:db8::1", "ip:<IP>"),
        ("2001:db8::1:timeout", "<IP>:timeout"),
        # IPv4
        ("camera at 192.168.1.20:80", "camera at <IP>:80"),
        # Home folders: a Windows user name may hold spaces; a POSIX one ends at whitespace
        (r"C:\Users\John Smith\AppData\Local", r"<HOME>\AppData\Local"),
        ("C:/Users/John Smith/AppData", "<HOME>/AppData"),
        ("/home/alice and then text", "<HOME> and then text"),
        ("/Users/alice/Library/Logs", "<HOME>/Library/Logs"),
        # Credentials and keys
        ("Authorization: Bearer abc.def.ghi", "Authorization=<REDACTED> <REDACTED>"),
        ("sent Bearer abc.def.ghi to the service", "sent Bearer <REDACTED> to the service"),
        ("password=hunter2 user=x", "password=<REDACTED> user=x"),
        ("API_KEY: s3cr3t", "API_KEY=<REDACTED>"),
        ("token=abc&next", "token=<REDACTED>"),
        ("mail someone@example.com now", "mail <EMAIL> now"),
        ("key AKIAABCDEFGHIJKLMNOP used", "key <AWS_ACCESS_KEY> used"),
    ],
)
def test_private_details_are_replaced(text, expected):
    assert redact(text) == expected
