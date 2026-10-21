"""Embedded webview helper isolated from Tk's main-thread event loop.

Only an ephemeral Turnstile token crosses an authenticated loopback connection.
No JS API exposes native filesystem, receipts, camera state, or app objects.
"""
import hmac
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time

from .client import Paused, origin


def verified_reply(result, nonce):
    """Malformed local IPC is ignored; it must not abort a valid verification."""
    if not isinstance(result, dict):
        return None
    received = result.get("nonce")
    if not isinstance(received, str) or not received.isascii() or not hmac.compare_digest(received, nonce):
        return None
    token = result.get("token")
    return token if isinstance(token, str) and 0 < len(token) <= 2048 else None


def verify_in_app(service, cancel):
    service = origin(service)
    nonce = secrets.token_urlsafe(32)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        listener.settimeout(0.25)
        args = ["--contribution-verification", service, str(listener.getsockname()[1]), nonce]
        if getattr(sys, "frozen", False):
            command = [sys.executable, *args]
        else:
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / "eyetrackapp.py"), *args]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            until = time.monotonic() + 300
            while time.monotonic() < until:
                if cancel.is_set():
                    raise Paused("Verification cancelled. Your encrypted upload is saved.")
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    if process.poll() is not None:
                        raise ValueError("Verification closed or could not start. Ensure the embedded webview runtime is installed.")
                    continue
                with connection:
                    connection.settimeout(1)
                    raw = b""
                    try:
                        while b"\n" not in raw and len(raw) <= 4096:
                            part = connection.recv(4096 - len(raw) + 1)
                            if not part:
                                break
                            raw += part
                        if len(raw) > 4096:
                            continue
                        token = verified_reply(json.loads(raw), nonce)
                        if token is not None:
                            return token
                    except (OSError, ValueError):
                        continue
            raise Paused("Verification timed out. Resume to try again.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def run_helper(service, port, nonce):
    import webview
    service = origin(service)
    expected = service + "/challenge?embedded=1"
    webview.settings.update(OPEN_EXTERNAL_LINKS_IN_BROWSER=False, ALLOW_DOWNLOADS=False,
                            ALLOW_FILE_URLS=False, OPEN_DEVTOOLS_IN_DEBUG=False)
    window = webview.create_window("EyeTrackVR — Verify contribution", expected,
                                   width=620, height=480, min_size=(480, 380),
                                   background_color="#20242b", text_select=False)
    from .native import asset, dark_titlebar
    if sys.platform == "win32":
        def style_native():
            try:
                dark_titlebar(window.native.Handle.ToInt64())
            except (AttributeError, OSError):
                pass
        window.events.shown += style_native
    closed = threading.Event()
    window.events.closed += closed.set

    def collect():
        until = time.monotonic() + 300
        while not closed.wait(0.25) and time.monotonic() < until:
            try:
                url = window.get_current_url()
                if url is None or url == "about:blank":
                    continue
                if url != expected:
                    window.destroy()
                    return
                token = window.evaluate_js("document.getElementById('token')?.value || ''")
                if isinstance(token, str) and 0 < len(token) <= 2048:
                    with socket.create_connection(("127.0.0.1", int(port)), timeout=3) as connection:
                        connection.sendall((json.dumps({"nonce": nonce, "token": token}) + "\n").encode())
                    window.destroy()
                    return
            except Exception:
                # Transient navigation/readiness errors may include page data: never log them.
                continue
        if not closed.is_set():
            window.destroy()

    engine = "edgechromium" if sys.platform == "win32" else "qt" if sys.platform.startswith("linux") else "cocoa"
    webview.start(collect, private_mode=True, debug=False, gui=engine, icon=str(asset("logo.ico")))
