"""Check a frozen Windows bundle and its native verification IPC without Cloudflare.

The loopback page supplies a fixture token only to exercise packaged WebView2 and
nonce IPC. It cannot pass real Siteverify and is never used for an upload.
Run manually with the packaging Python environment and the built executable path.
"""
import argparse
import certifi
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import socket
import subprocess
import threading

from PyInstaller.archive.readers import CArchiveReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    archive = CArchiveReader(str(args.executable))
    names = archive.toc
    required = ["contributions\\notice.json", "pyrage\\pyrage.pyd",
                "webview\\lib\\Microsoft.Web.WebView2.Core.dll",
                "webview\\lib\\runtimes\\win-x64\\native\\WebView2Loader.dll"]
    assert all(name in names for name in required), "Missing packaged contribution runtime"
    pyz = archive.open_embedded_archive("PYZ.pyz")
    for name in ["client", "bundles", "verification", "private_files", "window", "native"]:
        assert "contributions." + name in pyz.toc
    assert archive.extract("certifi\\cacert.pem") == Path(certifi.where()).read_bytes()
    nonce = secrets.token_urlsafe(32)
    fixture = "packaged-verification-fixture-not-a-turnstile-token"

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/challenge?embedded=1":
                self.send_error(404)
                return
            body = ('<!doctype html><title>EyeTrackVR packaging check</title>'
                    '<input id="token" type="hidden" value="' + fixture + '">').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Page) as http:
        threading.Thread(target=http.serve_forever, daemon=True).start()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(120)
            origin = "http://127.0.0.1:" + str(http.server_address[1])
            process = subprocess.Popen([str(args.executable.resolve()), "--contribution-verification",
                                        origin, str(listener.getsockname()[1]), nonce],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(5)
                    raw = b""
                    while b"\n" not in raw and len(raw) < 4096:
                        data = connection.recv(4096 - len(raw))
                        if not data:
                            break
                        raw += data
                assert json.loads(raw) == {"nonce": nonce, "token": fixture}
                assert process.wait(timeout=15) == 0
            finally:
                if process.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                http.shutdown()
    print(json.dumps({"frozen_native_webview": True, "nonce_ipc": True, "offline_notice": True,
                      "age_native_module": True, "updated_ca_bundle": True, "external_browser": False}))


if __name__ == "__main__":
    main()
