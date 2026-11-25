"""A stand-in for the overlay's interactive mode: a small Python script that
answers the commands the way the overlay does and records them.

A shared test helper, not a test module (pytest collects only test_*.py): imported
by test_smartcal_overlay.py and test_gaze_range_check.py through ``install()``."""

import sys

import localization
from utils import logging_utils, overlay_launch


FAKE_OVERLAY = """
import socket, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")
print({range_line!r}, flush=True)
cmd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd.bind(("127.0.0.1", {cmd_port}))
cmd.settimeout(10)
sig = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
def signal(value):
    sig.sendto(struct.pack(">i", value), ("127.0.0.1", {sig_port}))
time.sleep(0.05)
signal(255)
dots = 0
with open({record!r}, "w") as out:
    while True:
        data = cmd.recv(4096)
        code = struct.unpack(">i", data[:4])[0]
        if code == 111:
            out.write("111 %.4f %.4f\\n" % struct.unpack(">ff", data[4:12]))
        elif code == 50:
            out.write("50 " + data[4:].decode("utf-8").replace("\\n", "|") + "\\n")
        else:
            out.write(f"{{code}}\\n")
        out.flush()
        if code == 110:
            signal(10)
        elif code == 111:
            dots += 1
            if sys.argv[1] == "quit-early" and dots == 3:
                break
            time.sleep(0.02)
            signal(20)
        elif code == 119:
            time.sleep(0.02)  # the overlay ends the pass after the last hold
            signal(19)
        elif code == 200:
            break
"""


def install(monkeypatch, tmp_path, range_line):
    """Launch the stand-in instead of the overlay binary. It logs
    ``range_line`` as its gaze range. Returns a setter for its behaviour
    ("quit-early" leaves after the third dot) that returns the file the
    commands go to. The launch arguments are recorded in ``launched``."""
    record = tmp_path / "commands.txt"
    script = tmp_path / "fake_overlay.py"
    script.write_text(
        FAKE_OVERLAY.format(
            range_line=range_line,
            cmd_port=overlay_launch.OVERLAY_CMD_PORT,
            sig_port=overlay_launch.OVERLAY_SIGNAL_PORT,
            record=str(record),
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(logging_utils, "log_directory", lambda: tmp_path)
    behaviour = {"arg": ""}
    launched = []

    def command(*args):
        launched.append(args)
        return [sys.executable, str(script), behaviour["arg"]]

    monkeypatch.setattr(overlay_launch, "overlay_command", command)
    localization.init_localization("en")

    def configure(arg=""):
        behaviour["arg"] = arg
        return record

    configure.launched = launched
    return configure
