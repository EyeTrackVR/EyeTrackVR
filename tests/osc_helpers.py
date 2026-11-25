"""Shared helpers for the OSC / pyVRCFT / foveation tests.

Plain functions and context managers rather than fixtures, so test modules can
import them without fixture-shadowing lint noise. Every socket here is on
127.0.0.1 and bound to port 0.
"""

from __future__ import annotations

import contextlib
import gc
import json
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from unittest import mock

from osc.osc import OSCManager
from osc.osc_message import OSCMessage, OSCMessageType
from pyvrcft import osc as pyosc
from tests import EyeInfoMock, SimpleUDPClientMock

LOCALHOST = "127.0.0.1"


def wait_for(predicate, timeout: float = 3.0, interval: float = 0.005) -> bool:
    """Poll ``predicate`` until it is true or ``timeout`` passes; its last value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


def wait_until_sent(msg_queue: Queue, timeout: float = 5.0) -> None:
    """Block until the OSC sender thread has handled every queued message."""
    assert wait_for(lambda: msg_queue.unfinished_tasks == 0, timeout), "sender stopped consuming the queue"


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((LOCALHOST, 0))
        return s.getsockname()[1]


def eye_msg(eye_id=0, **kw) -> OSCMessage:
    fields = dict(x=0.0, y=0.0, blink=1.0, pupil_dilation=0.0, avg_velocity=0.0)
    fields.update(kw)
    return OSCMessage(type=OSCMessageType.EYE_INFO, data=(eye_id, EyeInfoMock(**fields)))


def set_output_mode(settings, mode: str) -> None:
    """Select exactly one VRChat output mode: v1, v2, native or pyvrcft."""
    settings.gui_osc_vrcft_v1 = mode == "v1"
    settings.gui_osc_vrcft_v2 = mode == "v2"
    settings.gui_vrc_native = mode == "native"
    settings.gui_pyvrcft = mode == "pyvrcft"


def use_free_ports(settings) -> None:
    """Point every fixed port in the settings at a free one (conftest uses 8889 /
    9001), so a real client never sends to, or binds, a port another app uses."""
    settings.gui_osc_port = free_udp_port()
    settings.gui_osc_receiver_port = free_udp_port()
    settings.gui_VRCFTModulePort = free_udp_port()


def collect_stray_garbage() -> None:
    """Collect garbage left by earlier test modules, on the main thread.

    Tk tests elsewhere in the suite leave tkinter.Tk objects in reference cycles.
    Whichever thread next triggers a full collection finalises them, and a Tk
    finalised off the main thread aborts the whole process (Tcl_Panic in
    Tcl_AsyncDelete, SIGTRAP on macOS). These modules start socket and sender
    threads, so they clear that garbage first."""
    gc.collect()


def isolate_gaze_outputs(monkeypatch, tmp_path) -> None:
    """Foveation gaze is on by default, so any started OSCManager publishes gaze.
    Keep it off the real shared memory block, Windows mutex and UDP port 9020
    that a running EyeTrackVR / PimaxMagic4All use."""
    from osc import foveation_gaze_sender, gaze_shared_memory
    from osc import osc as osc_module

    tag = uuid.uuid4().hex
    monkeypatch.setattr(gaze_shared_memory, "WIN32_NAME", f"Local\\EyeTrackVR.Gaze.test.{tag}")
    monkeypatch.setattr(gaze_shared_memory, "POSIX_PATH", str(tmp_path / f"eyetrackvr_gaze_test_{tag}"))
    monkeypatch.setattr(foveation_gaze_sender, "FOVEATION_MUTEX", f"Local\\eyetrackvr-osc-gaze-test-{tag}")
    monkeypatch.setattr(osc_module, "FOVEATION_PORT", free_udp_port())


def no_pyvrcft_discovery(monkeypatch) -> None:
    """A started pyVRCFT client must not run a real mDNS query (3 s, not joined on
    stop) or read this machine's VRChat avatar folder."""
    from pyvrcft import client as pyclient

    monkeypatch.setattr(pyclient.mdns, "discover_vrchat_oscquery", lambda timeout=3.0, **_: None)
    monkeypatch.setattr(pyclient, "load_avatar_config", lambda avatar_id: None)


def no_multicast(monkeypatch) -> None:
    """OSCQuery receivers advertise without binding the shared mDNS port."""
    from osc.oscquery import MDNSResponder

    monkeypatch.setattr(MDNSResponder, "start", lambda self: None)
    monkeypatch.setattr(MDNSResponder, "stop", lambda self: None)


def fast_server_shutdown(monkeypatch) -> None:
    """socketserver's serve_forever polls for shutdown every 0.5 s, so every OSC
    receiver / OSCQuery HTTP stop costs up to that much. Poll faster in tests."""
    import socketserver

    real = socketserver.BaseServer.serve_forever
    monkeypatch.setattr(socketserver.BaseServer, "serve_forever", lambda self, poll_interval=0.5: real(self, 0.01))


@contextlib.contextmanager
def running_manager(config, *, mock_udp: bool = True):
    """A started OSCManager fed through its queue; always shut down on exit.
    Yields (manager, msg_queue). With mock_udp, VRChat / module / foveation
    clients record into SimpleUDPClientMock.messages instead of sending."""
    msg_queue = Queue()
    patch = mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock) if mock_udp else None
    if patch is not None:
        patch.start()
    manager = OSCManager(config=config, osc_message_in_queue=msg_queue)
    try:
        manager.start()
        yield manager, msg_queue
    finally:
        manager.shutdown()
        if patch is not None:
            patch.stop()


def run_messages(config, messages):
    """Feed messages through a mocked-UDP OSCManager and shut it down; the manager."""
    with running_manager(config) as (manager, msg_queue):
        for message in messages:
            msg_queue.put(message)
        wait_until_sent(msg_queue)
        assert manager.osc_sender_thread.is_alive()
    return manager


@contextlib.contextmanager
def udp_listener(timeout: float = 0.2):
    """A local UDP socket standing in for VRChat's OSC input."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LOCALHOST, 0))
        sock.settimeout(timeout)
        yield sock
    finally:
        sock.close()


def drain(sock, settle: float = 0.3) -> list:
    """Every (address, args) received on sock until it stays quiet for ``settle``."""
    out = []
    deadline = time.monotonic() + settle
    while time.monotonic() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        out.extend(pyosc.parse(data))
        deadline = time.monotonic() + settle
    return out


def receive_until(sock, done, timeout: float = 3.0) -> list:
    """(address, args) received on sock until ``done(received)`` holds; for senders
    that send from their own thread, where a fixed quiet window would race them."""
    out = []
    deadline = time.monotonic() + timeout
    while not done(out) and time.monotonic() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        out.extend(pyosc.parse(data))
    assert done(out), f"expected messages never arrived: {out}"
    return out


def wire(client) -> dict:
    """address -> args of what a pyVRCFT client's next send tick puts on the wire.
    Each bundle is parsed on its own: joined bundles parse as the first only."""
    return {a: v for bundle in pyosc.pack_bundles(client._collect_messages()) for a, v in pyosc.parse(bundle)}


class _OSCQueryHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        self.server.requests.append(self.path)
        body = self.server.body
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def vrchat_oscquery(body):
    """A loopback HTTP server standing in for VRChat's OSCQuery: GET anything
    returns ``body`` (a JSON-able tree, a raw string, or None for 404). Yields
    the server; set ``server.body`` to change the answer, read ``server.requests``."""
    server = ThreadingHTTPServer((LOCALHOST, 0), _OSCQueryHandler)
    server.daemon_threads = True
    server.body = body
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2.0)


def avatar_tree(avatar_id="avtr_x", params=None, full_face=None) -> dict:
    """VRChat's GET /avatar tree: the current id, optional full-face flag and
    {name: OSC type tag} parameters under /avatar/parameters."""
    contents = {
        "change": {"FULL_PATH": "/avatar/change", "TYPE": "s", "VALUE": [avatar_id]},
        "parameters": {
            "FULL_PATH": "/avatar/parameters",
            "CONTENTS": {
                name: {"FULL_PATH": f"/avatar/parameters/{name}", "TYPE": tag} for name, tag in (params or {}).items()
            },
        },
    }
    if full_face is not None:
        contents["avatarfullfacetracking"] = {
            "FULL_PATH": "/avatar/avatarfullfacetracking",
            "TYPE": "T",
            "VALUE": [full_face],
        }
    return {"FULL_PATH": "/avatar", "CONTENTS": contents}
