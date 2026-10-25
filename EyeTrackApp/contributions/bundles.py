"""Allowlisted packaging, untrusted-archive validation and best-effort log redaction.

Shared byte-for-byte by EyeTrackVR (producer) and ETVR-Dataset-Sync (consumer).
Anyone can encrypt to the public recipient, so maintainers run inspect_bundle on
every decrypted archive; the app's own packaging is never trusted. No auto log discovery.
"""
import json
import re
import shutil
import struct
import unicodedata
import zipfile
import zlib
from pathlib import Path

CAPTURE = re.compile(r"^v[0-9]+_[A-Za-z0-9]{9}_(?:full_session_(?P<video_eye>Left|Right)\.(?:avi|mp4)|"
                     r"(?P<eye>Left|Right)_(?:timestamps\.txt|[0-9]+_[A-Za-z0-9_.+-]+\.png))$", re.I)
ISSUE = re.compile(r"^(?:description\.txt|log-(?:[1-9]|10)\.txt)$")
SUBMISSION = "etvr-submission-v1"
MAX_UNPACKED = 2 * 1024**3
MAX_MEMBERS = 10000
MAX_HMD = 160
MAX_FRAME_SIDE = 4096
PNG = b"\x89PNG\r\n\x1a\n"


def clean_hmd(text):
    """One visible line: control/separator characters become spaces; bidi, format and private-use go."""
    if not isinstance(text, str):
        raise ValueError("Enter your HMD")
    kept = []
    for character in unicodedata.normalize("NFC", text):
        category = unicodedata.category(character)
        if category == "Cc" or category.startswith("Z"):
            kept.append(" ")
        elif not category.startswith("C"):
            kept.append(character)
    text = " ".join("".join(kept).split())
    if not text or len(text) > MAX_HMD:
        raise ValueError(f"Enter your HMD in 1–{MAX_HMD} characters")
    return text


def check_submission(value):
    """The encrypted binding between a bundle, its submission ID and the consent it was made under."""
    if not isinstance(value, dict) or value.get("kind") not in {"dataset", "issue"}:
        raise ValueError("Invalid submission record")
    keys = {"schema", "id", "kind", "terms_version", "terms_sha256"} | ({"hmd"} if value["kind"] == "dataset" else set())
    if (set(value) != keys or value["schema"] != SUBMISSION
            or not isinstance(value["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", value["id"])
            or not isinstance(value["terms_version"], str) or not 0 < len(value["terms_version"]) <= 100
            or not isinstance(value["terms_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["terms_sha256"])):
        raise ValueError("Invalid submission record")
    if value["kind"] == "dataset" and clean_hmd(value["hmd"]) != value["hmd"]:
        raise ValueError("Invalid HMD description in submission record")
    return value


def submission_record(sid, kind, terms_version, terms_sha256, hmd=None):
    value = {"schema": SUBMISSION, "id": sid, "kind": kind,
             "terms_version": terms_version, "terms_sha256": terms_sha256}
    if kind == "dataset":
        value["hmd"] = clean_hmd(hmd)
    return json.dumps(check_submission(value), sort_keys=True, ensure_ascii=False).encode()


def check_manifest(value):
    allowed = {"schema", "image_coordinate_frame", "eyes", "dilation_reference"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Unexpected capture manifest fields")
    if value.get("schema") != "etvr-capture-v1":
        raise ValueError("Unsupported capture manifest schema")
    if value.get("image_coordinate_frame", "raw_camera") != "raw_camera":
        raise ValueError("Unexpected coordinate frame")
    eyes = value.get("eyes", [])
    if not isinstance(eyes, list) or len(eyes) > 2:
        raise ValueError("Invalid eye metadata")
    for eye in eyes:
        if (not isinstance(eye, dict) or set(eye) - {"eye", "camera_rotation_degrees"}
                or eye.get("eye") not in {"Left", "Right"}
                or type(eye.get("camera_rotation_degrees")) is not int
                or not -360 <= eye["camera_rotation_degrees"] <= 360):
            raise ValueError("Unexpected eye metadata")
    dilation = value.get("dilation_reference")
    if dilation is not None:
        if not isinstance(dilation, dict) or set(dilation) != {
            "target_type", "backdrop_gray_8bit", "adaptation_seconds", "frames_per_phase"
        }:
            raise ValueError("Unexpected dilation metadata")
        gray = dilation["backdrop_gray_8bit"]
        if (dilation["target_type"] != "illumination_phase_only"
                or not isinstance(gray, dict) or set(gray) != {"dim", "bright"}
                or any(type(v) is not int or not 0 <= v <= 255 for v in gray.values())
                or type(dilation["adaptation_seconds"]) not in (int, float)
                or not 0 <= dilation["adaptation_seconds"] <= 60
                or type(dilation["frames_per_phase"]) is not int
                or not 1 <= dilation["frames_per_phase"] <= 1000):
            raise ValueError("Invalid dilation metadata")
    return value


def member_info(name, size=0):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    info.file_size = size
    return info


def write_member(target, name, data):
    target.writestr(member_info(name), data)


def small_json(archive, entry, maximum=65536):
    if entry.file_size > maximum:
        raise ValueError(f"{entry.filename[:80]!r} is too large")
    return json.loads(archive.read(entry).decode("utf-8"))


def dataset_bundle(source, destination, submission=None):
    """Flatten a capture ZIP to allowlisted members. submission is the encrypted binding record."""
    with zipfile.ZipFile(source) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        if not entries or len(entries) > MAX_MEMBERS or sum(e.file_size for e in entries) > MAX_UNPACKED:
            raise ValueError("Capture archive exceeds safe member/expanded-size limits")
        names, manifest = set(), False
        with zipfile.ZipFile(destination, "w") as target:
            if submission is not None:
                check_submission(json.loads(submission))
                write_member(target, "submission.json", submission)
            for entry in entries:
                path = Path(entry.filename.replace("\\", "/"))
                parts = entry.filename.replace("\\", "/").split("/")
                if any(p in {"", ".", ".."} for p in parts) or path.is_absolute() or ":" in entry.filename:
                    raise ValueError("Unsafe archive path")
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Archive symlinks are not accepted")
                name = path.name
                # Flatten known capture files; never preserve workstation paths or arbitrary attachments.
                if name in names:
                    raise ValueError("Duplicate archive member")
                names.add(name)
                if name == "capture_manifest.json":
                    data = json.dumps(check_manifest(small_json(archive, entry)), sort_keys=True).encode()
                    manifest = True
                elif not CAPTURE.fullmatch(name):
                    raise ValueError(f"Unrecognized capture member: {name!r}; export a clean capture ZIP")
                elif name.endswith("_timestamps.txt"):
                    text = archive.read(entry).decode("utf-8")
                    data = "\n".join(line for line in text.splitlines()
                                     if not line.startswith("# Recorded on:")).encode()
                else:
                    # Stream recordings: a capture can be far larger than comfortable memory.
                    with archive.open(entry) as reader, target.open(member_info(name, entry.file_size), "w") as writer:
                        shutil.copyfileobj(reader, writer, 1024 * 1024)
                    continue
                write_member(target, name, data)
            if not manifest:
                raise ValueError("Capture manifest is required; legacy import needs separate review")


def check_text(archive, entry, maximum):
    if entry.file_size > maximum:
        raise ValueError(f"Text member too large: {entry.filename[:80]!r}")
    if "\x00" in archive.read(entry).decode("utf-8"):
        raise ValueError(f"Binary data in text member: {entry.filename[:80]!r}")


def check_capture(archive, entry, match, eyes):
    """Stream one recording member; zipfile verifies its declared size and CRC at EOF."""
    with archive.open(entry) as reader:
        header = reader.read(32)
        while reader.read(1024 * 1024):
            pass
    name = entry.filename.lower()
    eye = eyes.setdefault((match["video_eye"] or match["eye"]).capitalize(),
                          {"frames": 0, "frame_sizes": [], "videos": 0, "video_bytes": 0, "timestamps": False})
    if name.endswith(".png"):
        if len(header) < 24 or header[:8] != PNG or header[12:16] != b"IHDR":
            raise ValueError(f"Invalid PNG frame: {entry.filename[:80]!r}")
        size = list(struct.unpack(">II", header[16:24]))
        if not all(1 <= side <= MAX_FRAME_SIDE for side in size):
            raise ValueError(f"Implausible frame dimensions: {entry.filename[:80]!r}")
        eye["frames"] += 1
        if size not in eye["frame_sizes"]:
            eye["frame_sizes"].append(size)
    elif name.endswith(".txt"):
        check_text(archive, entry, 64 * 1024**2)
        eye["timestamps"] = True
    elif (name.endswith(".avi") and header[:4] == b"RIFF" and header[8:12] == b"AVI "
          or name.endswith(".mp4") and header[4:8] == b"ftyp"):
        eye["videos"] += 1
        eye["video_bytes"] += entry.file_size
    else:
        raise ValueError(f"Invalid video container: {entry.filename[:80]!r}")


def _inspect(path, kind):
    eyes, names = {}, set()
    summary = {"kind": kind, "members": 0, "unpacked": 0, "submission": None, "manifest": None}
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_MEMBERS + 2 or sum(e.file_size for e in entries) > MAX_UNPACKED:
            raise ValueError("Archive exceeds safe member/expanded-size limits")
        for entry in entries:
            name = entry.filename
            if (name in names or entry.is_dir() or any(c in name for c in "/\\:\x00")
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError(f"Unsafe or duplicate archive member: {name[:80]!r}")
            if entry.flag_bits & 0x1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError(f"Unsupported archive member encoding: {name[:80]!r}")
            names.add(name)
            match = CAPTURE.fullmatch(name) if kind == "dataset" else None
            if name == "submission.json":
                summary["submission"] = check_submission(small_json(archive, entry))
            elif kind == "dataset" and name == "capture_manifest.json":
                summary["manifest"] = check_manifest(small_json(archive, entry))
            elif match:
                check_capture(archive, entry, match, eyes)
            elif kind == "issue" and ISSUE.fullmatch(name):
                check_text(archive, entry, 8 * 1024**2)
            else:
                raise ValueError(f"Unexpected archive member: {name[:80]!r}")
            summary["members"] += 1
            summary["unpacked"] += entry.file_size
    if not summary["submission"] or summary["submission"]["kind"] != kind:
        raise ValueError("Missing or mismatched encrypted submission record")
    if kind == "issue" and "description.txt" not in names:
        raise ValueError("Issue description is required")
    if kind == "dataset":
        if summary["manifest"] is None:
            raise ValueError("Capture manifest is required")
        if not any(eye["frames"] or eye["videos"] for eye in eyes.values()):
            raise ValueError("Capture contains no frames or recordings")
        summary["eyes"] = eyes
    return summary


def inspect_bundle(path, kind="dataset"):
    """Validate a decrypted archive as hostile input and summarize it without extracting files."""
    try:
        return _inspect(path, kind)
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError, struct.error) as error:
        raise ValueError("Corrupt or unsupported archive") from error


def redact(text):
    # Deliberately conservative; always inspect the prepared archive before submitting.
    text = re.sub(r"(?i)(?:[A-Z]:[\\/]+Users[\\/]+|/home/|/Users/)[^\\/\s]+", "<HOME>", text)
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <REDACTED>", text)
    text = re.sub(r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*\S+",
                  r"\1=<REDACTED>", text)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<IP>", text)
    text = re.sub(r"(?<!\w)(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:]{0,39}(?!\w)", "<IP>", text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "<EMAIL>", text)
    text = re.sub(r"\bAKIA[A-Z0-9]{16}\b", "<AWS_ACCESS_KEY>", text)
    return text


def issue_bundle(description, logs, destination, submission=None):
    if not description.strip() or len(description) > 20000:
        raise ValueError("Issue description must contain 1–20000 characters")
    if len(logs) > 10:
        raise ValueError("Attach at most 10 explicit text log files")
    total = len(description.encode())
    with zipfile.ZipFile(destination, "w") as archive:
        if submission is not None:
            check_submission(json.loads(submission))
            write_member(archive, "submission.json", submission)
        write_member(archive, "description.txt", redact(description).encode())
        for i, path in enumerate(logs):
            path = Path(path)
            total += path.stat().st_size
            if total > 8 * 1024 * 1024:
                raise ValueError("Issue report exceeds 8 MiB before encryption")
            text = path.read_text(encoding="utf-8")
            if "\x00" in text:
                raise ValueError("Only UTF-8 text logs are accepted")
            write_member(archive, f"log-{i + 1}.txt", redact(text).encode())
