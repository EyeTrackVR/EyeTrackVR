"""pyVRCFT's OSCQuery discovery: stop() must not wait out mDNS retries (it runs on
the GUI thread when OSC settings change), and a dead endpoint is rediscovered."""

import threading
import time

from pyvrcft import VRCFTClient
from pyvrcft import client as client_module


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_stop_returns_promptly_during_discovery_backoff(monkeypatch):
    queries = []

    def not_found(timeout=3.0, **_):
        queries.append(1)
        return None

    monkeypatch.setattr(client_module.mdns, "discover_vrchat_oscquery", not_found)
    client = VRCFTClient(recv_port=0)
    client.start()
    assert _wait_for(lambda: queries)
    started = time.monotonic()
    client.stop()
    assert time.monotonic() - started < 0.5


def test_stop_does_not_wait_for_an_mdns_query_in_flight(monkeypatch):
    release = threading.Event()
    in_query = threading.Event()

    def slow_query(timeout=3.0, **_):
        in_query.set()
        release.wait(timeout)
        return None

    monkeypatch.setattr(client_module.mdns, "discover_vrchat_oscquery", slow_query)
    client = VRCFTClient(recv_port=0)
    client.start()
    try:
        assert in_query.wait(3.0)
        started = time.monotonic()
        client.stop()
        assert time.monotonic() - started < 0.5
    finally:
        release.set()


def test_failed_avatar_fetch_forgets_the_endpoint_and_discovery_runs_again(monkeypatch):
    queries = []
    monkeypatch.setattr(client_module, "fetch_avatar_oscquery", lambda host, port: None)

    def found(timeout=3.0, **_):
        queries.append(1)
        return ("127.0.0.1", 9100 + len(queries))

    monkeypatch.setattr(client_module.mdns, "discover_vrchat_oscquery", found)
    client = VRCFTClient(recv_port=0, use_oscquery=False)
    client._oscquery_endpoint = ("127.0.0.1", 9100)
    client.avatar = object()  # an avatar is loaded: discovery does not fetch on its own

    stop = threading.Event()
    thread = threading.Thread(target=client._discover_loop, args=(stop,), daemon=True)
    thread.start()
    try:
        time.sleep(0.1)
        assert not queries  # endpoint known: no mDNS traffic
        client._resolve_avatar("")  # e.g. /avatar/change after VRChat restarted
        assert client._oscquery_endpoint is None
        assert _wait_for(lambda: client._oscquery_endpoint == ("127.0.0.1", 9101))
        assert len(queries) == 1
    finally:
        stop.set()
        thread.join(2.0)
    assert not thread.is_alive()
