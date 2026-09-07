"""Avatar parameter resolution.

Two paths, same as VRCFT:
  A) VRChat's OSCQuery HTTP endpoint  (GET /avatar) is live and preferred.
  B) VRChat's avatar config JSON on disk is the fallback and uses the avatar id
     from the /avatar/change OSC message.

Both produce a list of AvatarParameter(name, address, py_type).
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AvatarParameter:
    name: str  # last path segment, e.g. "JawOpen4"
    address: str  # full OSC address, e.g. "/avatar/parameters/FT/v2/JawOpen4"
    type: type  # float | int | bool | str


@dataclass
class AvatarInfo:
    id: str = ""
    name: str = ""
    parameters: list = field(default_factory=list)


_JSON_TYPE_MAP = {"Float": float, "Int": int, "Bool": bool, "String": str}
_OSC_TAG_MAP = {"f": float, "d": float, "i": int, "h": int, "T": bool, "F": bool, "s": str}


def vrchat_osc_directories():
    """Candidate VRChat OSC config directories for this platform."""
    dirs = []
    home = Path.home()
    if os.name == "nt":
        dirs.append(home / "AppData" / "LocalLow" / "VRChat" / "VRChat" / "OSC")
    else:
        # Steam/Proton (appid 438100) prefix, default library location
        dirs.append(
            home
            / ".steam/steam/steamapps/compatdata/438100/pfx/drive_c/users/steamuser"
            / "AppData/LocalLow/VRChat/VRChat/OSC"
        )
        dirs.append(
            home
            / ".local/share/Steam/steamapps/compatdata/438100/pfx/drive_c/users/steamuser"
            / "AppData/LocalLow/VRChat/VRChat/OSC"
        )
    return [d for d in dirs if d.is_dir()]


def load_avatar_config(avatar_id: str) -> AvatarInfo | None:
    """Find and parse <osc dir>/<user>/Avatars/<avatar_id>.json.

    Only parameters with an "input" block are addressable (same filter VRCFT
    applies). VRChat writes these files as UTF-8 with a BOM.
    """
    for osc_dir in vrchat_osc_directories():
        for config_path in osc_dir.glob(f"usr_*/Avatars/{avatar_id}.json"):
            try:
                with open(config_path, encoding="utf-8-sig") as f:
                    config = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if config.get("id") != avatar_id:
                continue
            params = []
            for p in config.get("parameters", []):
                inp = p.get("input")
                if not inp:
                    continue
                py_type = _JSON_TYPE_MAP.get(inp.get("type"))
                if py_type is None:
                    continue
                address = inp.get("address", "")
                params.append(
                    AvatarParameter(name=address.rsplit("/", 1)[-1], address=address, type=py_type)
                )
            return AvatarInfo(id=avatar_id, name=config.get("name", ""), parameters=params)
    return None


def load_avatar_name(avatar_id: str) -> str:
    """Best-effort human-readable avatar name from the disk config
    (OSCQuery's tree does not expose it. VRCFT performs the same lookup)."""
    info = load_avatar_config(avatar_id)
    return info.name if info else ""


def fetch_avatar_oscquery(host: str, port: int, timeout: float = 3.0) -> AvatarInfo | None:
    """GET /avatar from VRChat's OSCQuery server and flatten the tree."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/avatar", timeout=timeout) as resp:
            tree = json.load(resp)
    except (OSError, ValueError):
        return None

    info = AvatarInfo()
    change = tree.get("CONTENTS", {}).get("change", {})
    values = change.get("VALUE")
    if isinstance(values, list) and values and isinstance(values[0], str):
        info.id = values[0]
        info.name = load_avatar_name(info.id)

    params_node = tree.get("CONTENTS", {}).get("parameters")
    if params_node:
        _walk_oscquery_node(params_node, info.parameters)
    return info


def _walk_oscquery_node(node: dict, out: list) -> None:
    contents = node.get("CONTENTS")
    if contents:
        for child in contents.values():
            _walk_oscquery_node(child, out)
        return
    address = node.get("FULL_PATH")
    tag = node.get("TYPE") or ""
    py_type = _OSC_TAG_MAP.get(tag[:1])
    if address and py_type:
        out.append(
            AvatarParameter(name=address.rsplit("/", 1)[-1], address=address, type=py_type)
        )
