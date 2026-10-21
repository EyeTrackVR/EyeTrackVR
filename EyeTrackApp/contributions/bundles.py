"""Allowlisted dataset packaging and best-effort log redaction. No auto log discovery."""
import json
import re
import zipfile
from pathlib import Path

CAPTURE = re.compile(r"^v[0-9]+_[A-Za-z0-9]{9}_(?:full_session_(?:Left|Right)\.(?:avi|mp4)|"
                     r"(?:Left|Right)_timestamps\.txt|(?:Left|Right)_[0-9]+_[A-Za-z0-9_.-]+\.png)$", re.I)
MAX_UNPACKED = 2 * 1024**3


def write_member(target, name, data):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    target.writestr(info, data)


def dataset_bundle(source, destination):
    with zipfile.ZipFile(source) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        if not entries or len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_UNPACKED:
            raise ValueError("Capture archive exceeds safe member/expanded-size limits")
        names, manifest = set(), False
        with zipfile.ZipFile(destination, "w") as target:
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
                    value = json.loads(archive.read(entry))
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
                    data = json.dumps(value, sort_keys=True).encode()
                    manifest = True
                elif CAPTURE.fullmatch(name):
                    data = archive.read(entry)
                    if name.endswith("_timestamps.txt"):
                        text = data.decode("utf-8")
                        data = "\n".join(line for line in text.splitlines()
                                         if not line.startswith("# Recorded on:")).encode()
                else:
                    raise ValueError(f"Unrecognized capture member: {name!r}; export a clean capture ZIP")
                write_member(target, name, data)
            if not manifest:
                raise ValueError("Capture manifest is required; legacy import needs separate review")


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


def issue_bundle(description, logs, destination):
    if not description.strip() or len(description) > 20000:
        raise ValueError("Issue description must contain 1–20000 characters")
    if len(logs) > 10:
        raise ValueError("Attach at most 10 explicit text log files")
    total = len(description.encode())
    with zipfile.ZipFile(destination, "w") as archive:
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
