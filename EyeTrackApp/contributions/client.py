"""Contributor-only client. No Cloudflare credentials or decryption identities."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit

import requests

from .bundles import clean_hmd, dataset_bundle, inspect_bundle, issue_bundle, submission_record
from .private_files import restrict_access

SERVICE = "https://etvr-dataset-sync-staging.beauldb.workers.dev"
# End-to-end encryption: the upload service never chooses the key. Each release pins
# the maintainers' public age recipients per service; rotating them needs a new release.
PINNED_RECIPIENTS = {SERVICE: ("age1nvpq3esls93mpg6q9l7hwtwz050dl9stz99x5sfecdanpa3ftdtqmw7cyj",)}
PROTOCOL = 3
ID = re.compile(r"[a-f0-9]{32}")
SHA = re.compile(r"[a-f0-9]{64}")
TERMINAL = {"pending", "approved", "rejected", "withdrawn"}


class Paused(Exception):
    """The exact ciphertext and receipt remain available for resume."""


SUPPORT = "ping prohurtz on Discord"
# Keyed by the Worker's machine-readable error code; the upload is always kept for Resume.
QUOTA_MESSAGES = {
    "daily_quota": "Today's upload limit for all contributors has been reached. Your encrypted recording is "
                   "saved on this computer: use Your contributions → Resume after midnight UTC, or " + SUPPORT + ".",
    "network_quota": "Your network has reached today's upload limit. Your encrypted recording is saved on this "
                     "computer: use Your contributions → Resume after midnight UTC, or " + SUPPORT + ".",
    "lifetime_quota": "The collection is full for now. Your encrypted recording is saved on this computer; "
                      + SUPPORT + " to get it uploaded.",
    "chunk_attempts": "This upload failed too many times. Withdraw it and record again, or " + SUPPORT + ".",
    "rate_limited": "Too many requests right now. Wait a minute, then use Resume.",
}
# Bug reports have their own quotas on the service; same codes, report wording.
ISSUE_QUOTA_MESSAGES = {
    "daily_quota": "Today's bug report limit for everyone has been reached. Your encrypted report is saved "
                   "and will send when you retry after midnight UTC, or " + SUPPORT + ".",
    "network_quota": "Your network has sent today's maximum number of bug reports. Your encrypted report is "
                     "saved; retry after midnight UTC, or " + SUPPORT + ".",
    "lifetime_quota": "Bug reports are full for now. Please " + SUPPORT + " instead.",
    "chunk_attempts": "This report failed to send too many times. Please " + SUPPORT + ".",
    "rate_limited": "Too many requests right now. Wait a minute, then retry.",
}


class ServiceError(ValueError):
    def __init__(self, status, code=None):
        self.status, self.code = status, code
        messages = {400: "The service rejected this upload's details. Update EyeTrackVR and try again.",
                    401: "The private receipt was not accepted.",
                    403: "Verification was not accepted. Please verify again.",
                    404: "This submission or service is unavailable.",
                    409: "This upload changed or expired. Refresh its status.",
                    413: "This recording exceeds the upload size limit.",
                    429: "The upload limit has been reached. Please try later, or " + SUPPORT + ".",
                    503: "Collection is closed or temporarily unavailable."}
        super().__init__(QUOTA_MESSAGES.get(code) or
                         messages.get(status, f"The contribution service returned HTTP {status}."))


def origin(value):
    parsed = urlsplit(value)
    local = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"}
    if ((parsed.scheme != "https" and not local) or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Invalid contribution service origin")
    return value.rstrip("/")


def outside_git(path):
    path = Path(path).resolve()
    if any((p / ".git").exists() for p in (path, *path.parents)):
        raise ValueError("Private receipts must be stored outside Git checkouts")
    return path


def private_directory(path):
    path = outside_git(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    restrict_access(path, directory=True)
    return path


def _data_home():
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    if __import__("sys").platform == "darwin":
        return Path.home() / "Library/Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def receipt_home():
    return _data_home() / "EyeTrackVR/contributions"


def issue_home():
    """Bug-report receipts live apart from dataset contributions."""
    return _data_home() / "EyeTrackVR/issue-reports"


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def hashes(path, chunk_bytes):
    with Path(path).open("rb") as source:
        return [hashlib.sha256(block).hexdigest() for block in iter(lambda: source.read(chunk_bytes), b"")]


def save(path, value):
    path = outside_git(path)
    if path.is_symlink():
        raise ValueError("Unsafe receipt path")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as stream:
            temporary = Path(stream.name)
            restrict_access(temporary, fd=stream.fileno())
            json.dump(value, stream)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)



class ContributionClient:
    def __init__(self, service=SERVICE, directory=None, recipients=None):
        self.service = origin(service)
        self.recipients = tuple(recipients or PINNED_RECIPIENTS.get(self.service, ()))
        self.directory = private_directory(directory if directory is not None else receipt_home())

    @contextlib.contextmanager
    def exclusive(self):
        """Also prevent two app instances from resuming/withdrawing concurrently."""
        with (self.directory / "operation.lock").open("a+b") as stream:
            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("Another contribution operation is running") from None
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def request(self, method, path, token=None, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if token:
            headers["Authorization"] = "Bearer " + token
        with requests.request(method, self.service + path, headers=headers, timeout=(10, 120),
                              allow_redirects=False, **kwargs) as response:
            if not 200 <= response.status_code < 300:
                try:
                    code = response.json().get("code")
                except (ValueError, AttributeError):
                    code = None
                # Only known codes select a message; service text is never shown verbatim.
                raise ServiceError(response.status_code, code if code in QUOTA_MESSAGES else None)
            return response.json()

    def config(self):
        config = self.request("GET", "/v1/config")
        if (type(config.get("chunk_bytes")) is not int or not 1024 <= config["chunk_bytes"] <= 8 * 1024**2
                or type(config.get("max_bytes", {}).get("dataset")) is not int
                or not 1 <= config["max_bytes"]["dataset"] <= 256 * 1024**2):
            raise ValueError("Invalid contribution service configuration")
        advertised = config.get("recipients")
        if (config.get("protocol") != PROTOCOL or not self.recipients or not isinstance(advertised, list)
                or sorted(advertised) != sorted(self.recipients)):
            # Never encrypt to a key this release cannot vouch for, even if the service offers one.
            raise ValueError("This EyeTrackVR version cannot verify the service's encryption key. "
                             "Update EyeTrackVR to contribute. Saved receipts can still withdraw.")
        if config.get("quota_full") not in QUOTA_MESSAGES:
            config["quota_full"] = None
        if config.get("issue_quota_full") not in ISSUE_QUOTA_MESSAGES:
            config["issue_quota_full"] = None
        return config

    def paths(self, sid):
        if not ID.fullmatch(sid):
            raise ValueError("Invalid submission ID")
        return self.directory / (sid + ".json"), self.directory / (sid + ".payload.age")

    def read(self, sid):
        receipt, _ = self.paths(sid)
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.validate(data)
        if data["id"] != sid:
            raise ValueError("Receipt ID mismatch")
        return data

    def validate(self, data):
        # Schema 2 receipts predate encrypted HMD text; they can still resume or withdraw.
        if (data.get("schema") not in {2, 3} or not ID.fullmatch(data.get("id", ""))
                or data.get("api") != self.service or data.get("kind") not in {"dataset", "issue"}
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", data.get("withdrawal_token", ""))
                or not SHA.fullmatch(data.get("sha256", ""))
                or type(data.get("size")) is not int or not 0 < data["size"] <= 256 * 1024**2
                or type(data.get("chunk_bytes")) is not int or not 1024 <= data["chunk_bytes"] <= 8 * 1024**2
                or not isinstance(data.get("chunks"), list)
                or len(data["chunks"]) != (data["size"] + data["chunk_bytes"] - 1) // data["chunk_bytes"]
                or any(not isinstance(h, str) or not SHA.fullmatch(h) for h in data["chunks"])):
            raise ValueError("Invalid private contribution receipt")

    def receipts(self):
        rows = []
        for path in self.directory.glob("*.json"):
            if not ID.fullmatch(path.stem):
                continue
            try:
                rows.append(self.read(path.stem))
            except (ValueError, OSError, TypeError):
                continue
        return sorted(rows, key=lambda row: (str(row.get("prepared", "")), row["id"]), reverse=True)

    @staticmethod
    def check_pause(cancel):
        if cancel.is_set():
            raise Paused("Paused. Resume will reuse the exact encrypted payload.")

    def prepare(self, source, hmd, agreed_terms, cancel, progress):
        hmd = clean_hmd(hmd)
        if Path(source).stat().st_size > 256 * 1024**2:
            raise ValueError("This archive exceeds the 256 MiB preparation limit")
        # The HMD text and consent binding travel only inside the ciphertext.
        return self._seal("dataset", agreed_terms, cancel, progress, lambda bundle, submission:
                          dataset_bundle(source, bundle, submission), hmd=hmd)

    def prepare_issue(self, description, logs, agreed_terms, cancel, progress):
        """Encrypt a written bug report plus explicitly chosen text logs (redacted by issue_bundle)."""
        return self._seal("issue", agreed_terms, cancel, progress, lambda bundle, submission:
                          issue_bundle(description, logs, bundle, submission))

    def _seal(self, kind, agreed_terms, cancel, progress, build, hmd=None):
        noun = "recording" if kind == "dataset" else "report"
        config = self.config()
        if not config["enabled"]:
            raise ValueError("Collection is currently closed")
        if config["terms"][kind] != agreed_terms:
            raise ValueError("The collection terms changed. Review the updated terms before uploading.")
        limit = config["max_bytes"].get(kind)
        if type(limit) is not int or not 1 <= limit <= 256 * 1024**2:
            raise ValueError("Invalid contribution service configuration")
        sid = uuid.uuid4().hex
        receipt, ciphertext = self.paths(sid)
        terms_sha256 = hashlib.sha256(agreed_terms["text"].encode()).hexdigest()
        self.check_pause(cancel)
        progress("Preparing and encrypting locally…", 0, 0)
        with tempfile.TemporaryDirectory(prefix="prepare-", dir=self.directory) as tmp:
            bundle = Path(tmp) / (kind + ".zip")
            build(bundle, submission_record(sid, kind, agreed_terms["version"], terms_sha256, hmd))
            self.check_pause(cancel)
            # Maintainers reject anything inspect_bundle rejects; fail here, before upload.
            inspect_bundle(bundle, kind)
            self.check_pause(cancel)
            # age-compatible Rust implementation; no external executable or private key.
            from pyrage import encrypt_file, x25519
            if bundle.stat().st_size > limit:
                raise ValueError(f"This {noun} exceeds the upload size limit")
            temporary = Path(tmp) / "payload.age"
            encrypt_file(str(bundle), str(temporary), [x25519.Recipient.from_str(key) for key in self.recipients])
            if temporary.stat().st_size > limit:
                raise ValueError(f"The encrypted {noun} exceeds the upload size limit")
            temporary.chmod(0o600)
            record = {"schema": 3, "api": self.service, "id": sid, "withdrawal_token": secrets.token_urlsafe(32),
                      "kind": kind, "consent": True, "prepared": time.strftime("%Y-%m-%d"),
                      "terms_version": agreed_terms["version"], "terms_sha256": terms_sha256,
                      "size": temporary.stat().st_size, "sha256": digest(temporary),
                      "chunk_bytes": config["chunk_bytes"], "chunks": hashes(temporary, config["chunk_bytes"]),
                      "state": "prepared"}
            if hmd is not None:
                record["hmd"] = hmd
            os.replace(temporary, ciphertext)
            save(receipt, record)
        return sid

    def resume(self, sid, verify, consent, cancel, progress):
        record = self.read(sid)
        noun = "recording" if record["kind"] == "dataset" else "report"
        receipt, ciphertext = self.paths(sid)
        prefix = "/v1/submissions/" + sid
        def call(method, suffix="", **kwargs):
            return self.request(method, prefix + suffix, record["withdrawal_token"], **kwargs)
        self.check_pause(cancel)
        try:
            state = call("GET")
        except ServiceError as error:
            if error.status != 404:
                raise
            state = None
        if state:
            if any(state[key] != record[key] for key in ("size", "sha256", "chunk_bytes")):
                raise ValueError("Server and local upload manifests differ")
            if state["status"] in TERMINAL:
                record["state"] = state["status"]
                save(receipt, record)
                ciphertext.unlink(missing_ok=True)
                return record["state"]
        if (not ciphertext.is_file() or ciphertext.is_symlink() or digest(ciphertext) != record["sha256"]
                or ciphertext.stat().st_size != record["size"]
                or hashes(ciphertext, record["chunk_bytes"]) != record["chunks"]):
            raise ValueError("The exact encrypted upload is missing or modified. Keep the receipt for withdrawal.")
        if state is None:
            if record.get("state") in TERMINAL | {"cancelled"}:
                raise ValueError("This submission is no longer available to resume")
            if record["schema"] < 3:
                raise ValueError("This upload was prepared by an older EyeTrackVR version. Withdraw it and record again.")
            config = self.config()
            if not config["enabled"]:
                raise ValueError("Collection is currently closed; your upload is retained for resume")
            if record["chunk_bytes"] != config["chunk_bytes"]:
                raise ValueError("Upload chunk size changed. Cancel this preparation and start a new contribution.")
            terms = config["terms"][record["kind"]]
            if (record["terms_version"] != terms["version"] or record["terms_sha256"] != hashlib.sha256(terms["text"].encode()).hexdigest()):
                if not consent(terms):
                    raise Paused("Updated terms were not accepted. Upload remains paused.")
                record.update(terms_version=terms["version"], terms_sha256=hashlib.sha256(terms["text"].encode()).hexdigest())
                save(receipt, record)
            progress("Verify in the EyeTrackVR window…", 0, record["size"])
            token = verify(self.service, cancel)
            self.check_pause(cancel)
            if not isinstance(token, str) or not 0 < len(token) <= 2048:
                raise ValueError("In-app verification was not completed")
            fields = ("id", "kind", "consent", "terms_version", "terms_sha256", "size", "sha256", "chunks")
            body = {k: record[k] for k in fields}
            body["challenge"] = token
            try:
                state = self.request("POST", "/v1/submissions", record["withdrawal_token"], json=body)
            except ServiceError as error:
                if record["kind"] == "issue" and error.code in ISSUE_QUOTA_MESSAGES:
                    raise ValueError(ISSUE_QUOTA_MESSAGES[error.code]) from None
                raise
        received = {item["part"]: item["sha256"] for item in state["received"]}
        if any(type(p) is not int or not 0 <= p < len(record["chunks"]) or record["chunks"][p] != h
               for p, h in received.items()):
            raise ValueError("Invalid server upload progress")
        record["state"] = "uploading"
        save(receipt, record)
        done = sum(min(record["chunk_bytes"], record["size"] - p * record["chunk_bytes"]) for p in received)
        progress(f"Uploading encrypted {noun}…", done, record["size"])
        with ciphertext.open("rb") as stream:
            for part, expected in enumerate(record["chunks"]):
                if part in received:
                    continue
                self.check_pause(cancel)
                stream.seek(part * record["chunk_bytes"])
                block = stream.read(record["chunk_bytes"])
                if hashlib.sha256(block).hexdigest() != expected:
                    raise ValueError("Encrypted payload changed")
                for attempt in range(3):
                    self.check_pause(cancel)
                    class Upload(io.BytesIO):
                        def read(inner, count=-1):
                            self.check_pause(cancel)
                            data = super().read(count)
                            progress(f"Sending encrypted {noun}…", done + inner.tell(), record["size"])
                            return data
                    try:
                        call("PUT", "/chunks/" + str(part), data=Upload(block),
                             headers={"Content-Type": "application/octet-stream", "Content-Length": str(len(block))})
                        break
                    except (requests.RequestException, ServiceError) as error:
                        if isinstance(error, ServiceError) and error.status not in {500, 502, 503, 504}:
                            raise
                        if attempt == 2:
                            raise
                        progress("Connection interrupted; retrying…", done, record["size"])
                        if cancel.wait(2**attempt):
                            self.check_pause(cancel)
                done += len(block)
                progress(f"Uploaded encrypted {noun}…", done, record["size"])
        self.check_pause(cancel)
        state = call("POST", "/complete", json={})
        record["state"] = state["status"]
        save(receipt, record)
        ciphertext.unlink(missing_ok=True)
        return record["state"]

    def withdraw(self, sid):
        record = self.read(sid)
        receipt, ciphertext = self.paths(sid)
        try:
            response = self.request("POST", "/v1/submissions/" + sid + "/withdraw",
                                    record["withdrawal_token"], json={})
            record["state"] = response["status"]
        except ServiceError as error:
            if error.status != 404 or record.get("state") not in {"prepared", "cancelled"}:
                raise
            record["state"] = "cancelled"
        save(receipt, record)
        ciphertext.unlink(missing_ok=True)
        return record["state"]
